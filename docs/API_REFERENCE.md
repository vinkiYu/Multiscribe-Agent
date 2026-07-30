# MultiscribeAgent API Reference

This document describes the HTTP API exposed by the FastAPI application. The
default base URL is `http://localhost:8000`. OpenAPI is available at `/docs`
and `/openapi.json` while the application is running.

## Conventions

- JSON request and response bodies use UTF-8.
- Protected endpoints require `Authorization: Bearer <access_token>`.
- The login endpoint returns a short-lived administrator token for the local
  console. The token lifetime is controlled by `CONSOLE_SESSION_HOURS`.
- Every response includes `X-Trace-Id`. Include that value in support tickets.
- Dates are ISO-8601 dates (`YYYY-MM-DD`); timestamps are ISO-8601 UTC values.
- List endpoints enforce a bounded `limit` to protect the database and LLM
  budget. The exact bounds are shown below.

## Authentication

### POST `/api/login`

Authenticate the local console password.

Request:

```json
{"password": "your-console-password"}
```

Response `200`:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "must_change_password": false
}
```

Errors: `401` for invalid credentials, `429` when the login rate limit is
exceeded.

## Health and observability

### GET `/healthz`

Unauthenticated process probe. Returns `{"status":"ok"}`. This endpoint is
intended for Docker or load-balancer health checks and does not verify the
database, provider, or publisher.

### GET `/metrics`

Returns Prometheus text when the optional observability dependencies are
installed. It is intentionally excluded from the OpenAPI schema. The endpoint
is exempt from the application rate limiter.

## Dashboard

All dashboard endpoints require authentication.

### GET `/api/dashboard/stats`

Returns lightweight counts:

```json
{"source_count": 120, "scheduled_tasks": 2}
```

### GET `/api/dashboard/logs?limit=20`

Returns recent `task_logs` rows, newest first. `limit` is an integer from 1 to
100. The row shape follows the persisted task-log schema (`id`, task identity,
status, timestamps, and error details).

### GET `/api/dashboard/overview`

Returns the operations dashboard aggregate in one request:

```json
{
  "usage": {"date":"2026-07-30", "input_tokens":0,
    "output_tokens":0, "total_tokens":0, "llm_calls":0, "task_count":0},
  "publish": {"total":0, "success":0, "failed":0},
  "iterations": [],
  "evaluation": {"today_summary": {}, "recent": []},
  "task_logs": []
}
```

The exact aggregate keys can grow as observability data is added; clients
should ignore unknown keys.

### POST `/api/dashboard/ingest`

Run one adapter or a batch without creating a schedule.

Single adapter request:

```json
{"adapter_id":"rss-adapter", "config":{"urls":["https://example/feed.xml"]}}
```

Response: `{"result_count": 8}`.

Batch request:

```json
{"adapter_configs":[
  {"adapter_id":"rss-adapter", "config":{"urls":[]}},
  {"adapter_id":"github-trending", "config":{}}
]}
```

Response: `{"results": {"rss-adapter": 8, "github-trending": 12}}` (the
values are adapter-specific). A malformed configuration returns `400`; an
unavailable ingestion service returns `503`.

## Daily news archive

### GET `/api/daily-news?date=2026-07-30&limit=31`

Public read-only endpoint. Without `date`, the newest complete digest is
selected. `limit` is 1-366 and controls archive navigation.

Response:

```json
{
  "archives": [{"date":"2026-07-30", "title":"AI Daily News",
    "item_count":12, "updated_at":"2026-07-30T01:00:00+00:00"}],
  "digest": {
    "date":"2026-07-30", "title":"AI Daily News", "summary":"...",
    "items":[{"title":"...", "summary":"...", "url":"https://...",
      "source":"rss", "score":0.9, "image_url":null, "video_url":null,
      "published_at":"2026-07-29T08:00:00+00:00", "section":"AI",
      "tags":["agent"]}],
    "total_scanned":120, "updated_at":"2026-07-30T01:00:00+00:00"
  }
}
```

`404` means the requested date has no published digest.

## Source data search

### GET `/api/source-data/search?q=agent&limit=20`

Authenticated FTS5 search over collected source data. `q` is required and is
limited to 200 characters; blank input returns `400`. `limit` is 1-100.
Malformed SQLite FTS expressions are treated as no matches and return `[]`.

Each result contains `id`, `title`, `url`, `description`, `source`, `category`,
`published_date`, `ingestion_date`, and `adapter_name`.

## Curation quality

### GET `/api/curation-evaluations?from_date=2026-07-01&to_date=2026-07-30&limit=50`

List persisted curation evaluation records, newest first. Dates are optional
inclusive filters and `limit` is 1-200. Each record includes
`workflow_run_id`, `date`, `recorded_at`, `rounds`, `converged`, `exit_reason`,
`final_score`, `score_delta`, `avg_iter_score`, `result_count`, and `usage`.

### GET `/api/curation-evaluations/summary?from_date=...&to_date=...`

Returns aggregate score, convergence, average rounds, and exit-reason counts
for the optional inclusive date range.

### GET `/api/curation-stats/by-period?from_date=2026-07-01&to_date=2026-07-30`

Returns one typed data point per day. If omitted, the range is the last 30 days
ending today. `from_date` must not be after `to_date`; invalid ranges return
`422`. Fields are `date`, `final_score`, `result_count`, `total_scanned`,
`efficiency`, `converged`, `exit_reason`, and `rounds`.

## Digest execution and approval

### POST `/api/digest/run`

Run the daily digest immediately with a schedule-compatible JSON configuration.
The payload may include `adapters`, `targets`, `top_n`, `fetch_days`, provider
settings, and preview fields. The response is the pipeline result, including
ingestion, deduplication, curation, archive, and per-target publishing data.

Invalid adapter or target configuration returns `400`; unavailable services
return `503`.

### POST `/api/digest/{date}/approve`

Approve a pending preview archive and publish it to the remaining targets.
Optional body:

```json
{"targets":["feishu_bot"], "preview_targets":["feishu_bot"]}
```

The archive must exist and have `approval_status=pending`. Success returns
`{"status":"approved", "targets":{...}}`. `404` means no archive, `409`
means it is not pending or another approval holds the lock.

### POST `/api/digest/{date}/reject`

Reject a pending preview without sending it. Returns
`{"status":"rejected", "date":"2026-07-30"}`. The same `404` and `409`
state checks as approval apply.

## Publishing history

### GET `/api/publish-history?publisher_id=feishu_bot&from_date=...&to_date=...&limit=50&offset=0`

Returns a paginated delivery history response:

```json
{"records":[{"id":"...", "publisher_id":"feishu_bot", "status":"success",
  "title":"...", "content_preview":"...", "result_data":{},
  "error_message":null, "published_at":"...", "adapter_name":"..."}],
 "total":120, "limit":50, "offset":0, "has_more":true}
```

`limit` is 1-200 and `offset` must be non-negative. Date filters are ISO
timestamps.

### GET `/api/publish-history/summary?from_date=...&to_date=...`

Returns aggregate delivery counts for the optional timestamp range.

## Alerts and adapter health

### GET `/api/alerts?limit=50&acknowledged=false`

Returns recent alert history. `limit` is 1-200; `acknowledged` can filter by
boolean state. Rows include `id`, `rule_name`, `metric`, `threshold`, `value`,
`description`, `fired_at`, and acknowledgement information.

### GET `/api/adapter-health`

Lists persisted health state for adapters that have run. A row contains the
adapter id, failure streak, disabled flag, last error, and timestamps.

### POST `/api/adapter-health/{adapter_id}/enable`

Clears the failure streak and re-enables an adapter. Returns the updated health
row or `404` if it has never run.

### POST `/api/adapter-health/{adapter_id}/disable`

Manually disables an adapter until an operator enables it. Returns the updated
health row or `404`.

## Agents

All agent endpoints require authentication.

### GET `/api/agents`

List configured agent definitions.

### POST `/api/agents`

Create an agent definition. The JSON body follows the `AgentDefinition` model,
including `id`, `name`, `system_prompt`, provider/model selection, tools, and
runtime budget fields. Duplicate or invalid definitions return `400`.

### POST `/api/agents/tools/approve`

Approve a tool for an agent. The body contains the agent and tool identifiers;
the response confirms the persisted approval.

### DELETE `/api/agents/{agent_id}`

Delete an agent definition. Missing agents return `404`.

### POST `/api/agents/{agent_id}/run`

Run an agent with a JSON input object. The response contains the final content
and run metadata. The endpoint is rate-limited by default to 20 requests per
minute and returns `503` when the provider is unavailable.

## Workflows and iterations

### GET `/api/workflows`

List saved declarative DAG workflow definitions.

### POST `/api/workflows`

Create or replace a workflow from its JSON `WorkflowSpec` (nodes, edges,
input mappings, and optional loop specification). Invalid DAGs return `400`.

### DELETE `/api/workflows/{workflow_id}`

Delete a workflow definition; missing ids return `404`.

### POST `/api/workflows/{workflow_id}/run`

Run a saved workflow. The optional JSON body is the input map for the first
layer. The response includes node outputs, run id, and loop summary.

### GET `/api/workflow-iterations?workflow_run_id=...&step_id=...&limit=50`

Read persisted loop iterations for operations and resume diagnostics. Filters
are optional; `limit` is bounded by the route. Each row includes run id, step,
round, score, convergence, reason, and recorded timestamp.

## Schedules

### GET `/api/schedules`

List configured scheduler tasks.

### POST `/api/schedules`

Create a schedule. The JSON body includes `id`, `name`, `task_type`, a five-part
`cron` expression, and task `config`. Invalid cron or duplicate ids return
`400`.

### DELETE `/api/schedules/{task_id}`

Delete a schedule and remove it from the running scheduler.

### POST `/api/schedules/{task_id}/run`

Trigger one existing schedule immediately. The distributed lock policy still
applies to daily digest tasks.

## Sources and knowledge

### GET `/api/sources`

List configured adapters and their enabled state.

### POST `/api/sources`

Create an adapter configuration with `id`, `type`, `enabled`, and `config`.

### PUT `/api/sources/{source_id}`

Update an adapter configuration. Unknown ids return `404`.

### GET `/api/kb/capabilities`

Return available knowledge backends and search capabilities.

### GET `/api/kb/categories`

List knowledge categories.

### POST `/api/kb/categories`

Create a category from a JSON object containing its name and optional metadata.

### GET `/api/kb/documents`

List knowledge documents.

### POST `/api/kb/documents`

Create a document with title, category, content, tags, and metadata.

### POST `/api/kb/documents/text`

Create a plain-text document from a JSON body. The service extracts searchable
text and metadata.

### DELETE `/api/kb/documents/{document_id}`

Delete a knowledge document.

### GET `/api/kb/search?q=agent&limit=20`

Search knowledge using the configured full-text/vector capabilities.

### POST `/api/kb/documents/{document_id}/move-to-memory`

Promote a document into a durable memory entry for later agent retrieval.

## Memory

### GET `/api/memory/preferences`

Read the current user preference profile.

### PUT `/api/memory/preferences`

Replace preference fields such as preferred tags, blocked sources, push time,
and importance threshold.

### GET `/api/memory/entries/search?q=agent&limit=20`

Search durable memory entries using FTS. The response is a list of matching
entries with content, importance, tags, and metadata.

### GET `/api/memory/entries`

List persisted memory entries.

### POST `/api/memory/entries`

Create a memory entry. The body includes `content`, optional `importance`,
`tags`, `agent_id`, and `metadata`.

### DELETE `/api/memory/entries/{entry_id}`

Delete one memory entry.

### POST `/api/memory/extract`

Extract preference signals from recent publish history. Deterministic extraction
is used when an LLM is unavailable.

## Settings and skills

### GET `/api/settings`

Read the merged runtime settings. Secret values are redacted.

### PUT `/api/settings`

Persist allowed settings overrides through the KV repository. Invalid fields
return `400`.

### POST `/api/settings/providers/{provider_id}/models`

Add a selectable model name to a provider catalog.

### POST `/api/settings/providers/{provider_id}/test`

Perform a provider connectivity test and return the normalized result.

### GET `/api/skills`

List loaded builtin and custom skills.

### POST `/api/skills/reload`

Rescan bundled and custom skill files; returns the loaded count.

### GET `/api/skills/{skill_id}`

Return one skill and its instructions.

### POST `/api/skills`

Create a custom skill below the configured runtime root. Required fields are
`id`, `frontmatter`, and `instructions`.

### DELETE `/api/skills/{skill_id}`

Delete a custom skill. Bundled skills are immutable.

## MCP and external AI interoperability

### GET `/api/mcp/tools`

List JWT-protected MCP tools and their JSON input schemas.

### POST `/api/mcp/tools/{tool_name}/call`

Validate and call an MCP tool. Validation errors return `400`; unknown tools
return `404`.

### POST `/api/ai/v1/register`

Create an external AI interoperability key. The plaintext key is returned only
once. Body: `{"description":"automation", "auto_approve":true}`.

### PUT `/api/ai/v1/keys/{key_id}/approve`

Approve a key created with `auto_approve=false`.

### GET `/api/ai/v1/tools`

Return OpenAI Function Calling schemas for registered tools.

### POST `/api/ai/v1/execute`

Execute one external tool call. Send the key in `X-API-Key` and a body such as
`{"name":"list_sources", "arguments":{}}`. Responses are
`{"ok":true,"tool":"...","output":...}`. Missing/invalid keys return
`401`, rate exhaustion returns `429`, unknown tools return `404`, and invalid
arguments return `400`.

## Click tracking

### GET `/api/track-click?url=https%3A%2F%2Fexample.com&tags=agent,rag`

Public redirect endpoint used by published digest links. Only `http` and
`https` URLs are accepted. The endpoint records click tags and returns a `302`
redirect; unsafe schemes such as `javascript:` and `file:` are rejected.

## Error format

Domain errors use a stable JSON shape:

```json
{"detail":"human-readable message"}
```

Typical status codes are `400` validation, `401` authentication, `403` CSRF or
authorization, `404` missing resource, `409` state or lock conflict, `422`
query validation, `429` rate limiting, `502` provider failure, and `503`
unavailable service. Unexpected failures are `500` and should be correlated by
`X-Trace-Id`.
