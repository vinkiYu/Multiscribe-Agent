# Troubleshooting Guide

Start with the trace id from the response header (`X-Trace-Id`) and the
corresponding structured log line. Do not paste API keys, webhook URLs,
cookies, or full prompts into an issue.

## Quick checks

```bash
curl http://localhost:8000/healthz
docker compose ps
uv run pytest -q
uv run ruff check .
```

The process probe only confirms that FastAPI is alive. A `503` from a business
endpoint usually means a dependency was not initialized or is unavailable.

## Frequently asked questions

### 1. `ModuleNotFoundError: No module named 'uv'`

**Cause:** The command was run with a system Python that does not have the
project environment.

**Fix:** Install uv, run `uv sync`, and use `uv run ...`. In an existing virtual
environment, use `.venv/Scripts/python.exe` on Windows or `.venv/bin/python`
on Linux/macOS.

### 2. The API starts but `/healthz` is unreachable

**Cause:** The process is bound to another host/port, exited during startup,
or a firewall/proxy blocks the port.

**Fix:** Check the startup log, confirm the command includes
`--host 0.0.0.0 --port 8000` for containers, and run `docker compose ps`.

### 3. Login returns `401 invalid credentials`

**Cause:** `SYSTEM_PASSWORD` does not match, or the development password path
is being used unexpectedly.

**Fix:** Set `SYSTEM_PASSWORD` in `.env`, restart the API, and send exactly
`{"password":"..."}` to `/api/login`. Do not include a password in logs.

### 4. Protected endpoints return `401` after login

**Cause:** The bearer token is missing, malformed, expired, or signed with a
different `JWT_SECRET`.

**Fix:** Send `Authorization: Bearer <access_token>` on every protected request.
If the secret or session lifetime changed, log in again.

### 5. Requests return `403` after a frontend form submission

**Cause:** CSRF protection is enabled and the request did not include the
expected browser context.

**Fix:** Use the frontend origin and its normal fetch flow, or configure
`CSRF_EXEMPT_PATHS` only for a deliberately isolated integration. Do not disable
CSRF on a public production deployment without an equivalent control.

### 6. LLM calls fail with `502` or an empty digest

**Cause:** The provider key, base URL, model name, proxy, or output budget is
wrong; all adapters may also have returned zero candidates.

**Fix:** Check `GET /api/settings` for redacted provider state, verify
`OPENAI_API_KEY`/`ANTHROPIC_API_KEY` and the compatible `*_API_BASE_URL`, then
run the provider test endpoint. Check task logs and adapter health before
retrying the digest.

### 7. A relay API key is rejected by the provider

**Cause:** The relay endpoint is not configured, or its path is missing the
OpenAI-compatible `/v1` suffix.

**Fix:** Set `OPENAI_API_BASE_URL` (or `ANTHROPIC_API_BASE_URL`) to the relay
endpoint, keep the key in the corresponding provider variable, and use the
relay's exact model name in `DEFAULT_CURATION_MODEL`. Custom names are passed
through without the built-in catalog acting as an allow-list.

### 8. The daily digest runs twice

**Cause:** Multiple scheduler instances ran without a shared Redis lock, or
strict locking was disabled during a Redis outage.

**Fix:** Set the same `REDIS_URL` for all instances and keep
`SCHEDULER_LOCK_STRICT_MODE=true`. Check `SCHEDULER_LOCK_TTL_SECONDS` covers the
longest digest run. Inspect publish history before manually retrying.

### 9. A scheduled task is not firing

**Cause:** The cron expression is invalid, the scheduler is not initialized,
or a distributed lock is unavailable in strict mode.

**Fix:** Validate the task through `POST /api/schedules`, check task logs, and
inspect Redis connectivity. Trigger it once with `POST /api/schedules/{id}/run`
after correcting the configuration.

### 10. Feishu or WeCom receives no message

**Cause:** The webhook is empty or malformed, the publisher is disabled, or a
provider returned a non-zero business error code.

**Fix:** Set `FEISHU_WEBHOOK`/`WECOM_WEBHOOK`, restart the API, confirm the
publisher is enabled, and inspect publish history for `error_message` and
`result_data`. Feishu signing also requires `FEISHU_SECRET` when configured.

### 11. An adapter becomes disabled automatically

**Cause:** Consecutive adapter failures reached
`ADAPTER_HEALTH_FAILURE_THRESHOLD`.

**Fix:** Read `GET /api/adapter-health`, correct the source URL or provider
limit, then call `POST /api/adapter-health/{adapter_id}/enable`. Do not simply
raise the threshold while the source is returning persistent errors.

### 12. Source-data search returns no results or `400`

**Cause:** The query is blank, exceeds 200 characters, uses invalid FTS syntax,
or the source has not been ingested.

**Fix:** Send a non-empty query under the length limit. Invalid FTS expressions
return an empty list by design; simplify phrase/operator syntax and check
`POST /api/dashboard/ingest` plus source counts.

### 13. `sqlite3.OperationalError: database is locked`

**Cause:** Several processes are writing the same SQLite file, a long
transaction is open, or the filesystem does not support WAL correctly.

**Fix:** Run one application process for SQLite, close abandoned processes, and
keep `data/` on a local writable filesystem. For multi-process deployment,
migrate to PostgreSQL and set a pool size appropriate for the worker count.

### 14. PostgreSQL connection or migration fails

**Cause:** Wrong DSN, an unhealthy container, missing `asyncpg`, or repository
SQL that has not completed the dialect migration.

**Fix:** Run `docker compose ps`, verify `DATABASE_URL`, install
`uv sync --extra postgres`, and inspect `logs/migration-*.json` for count drift.
Keep `DB_DRIVER=sqlite` until the migration checklist is complete.

### 15. The frontend shows a blank page or stale assets

**Cause:** `frontend/dist` was not built, Node is too old, or the browser cached
an older bundle.

**Fix:** Use Node 20+, run `npm install && npm run build`, restart FastAPI, and
hard-refresh the browser. For development, run `npm run dev` separately.

### 16. `npm run build` fails with `EBADENGINE` or TypeScript errors

**Cause:** Node/npm versions are below the frontend toolchain requirement or
dependencies are stale.

**Fix:** Upgrade to Node 20+, remove only the local `node_modules` directory,
run `npm install`, then repeat `npm run lint` and `npm run build`.

### 17. A workflow stops with a cycle or budget error

**Cause:** The declarative graph contains a dependency cycle, the loop reaches
its maximum rounds, or the context/output budget cannot fit the next call.

**Fix:** Validate workflow edges, reduce unnecessary input/tool results, lower
`max_rounds`, or configure a model with a larger context window. Inspect the
loop iteration records and the `context_budget_exhausted` event before retrying.

### 18. No Prometheus metrics are returned

**Cause:** The optional observability dependencies are not installed.

**Fix:** Run `uv sync --extra observability`, restart the API, and request
`/metrics`. The application continues to run with a no-op telemetry fallback
when those packages are absent.

### 19. Runtime log file is missing

**Cause:** `LOG_FILE` points to a non-writable directory or logging was started
before the directory existed.

**Fix:** Create the parent directory, set `LOG_FILE=logs/multiscribe-agent.log`,
restart the process, and check permissions. Logs rotate at 10 MB with five
backups.

### 20. A click-tracking link is rejected

**Cause:** The target URL is not `http` or `https`, or the query string was not
URL-encoded.

**Fix:** URL-encode the target and use a safe absolute URL. `javascript:`,
`file:`, and other schemes are intentionally blocked.

## Escalation bundle

When opening an issue, include:

1. The UTC timestamp and `X-Trace-Id`.
2. The endpoint, HTTP method, and status code.
3. Redacted task/adapter/publisher ids and the relevant task-log row.
4. Output from `docker compose ps` or the process command.
5. The exact configuration variable *names* involved, never their values.

For provider or webhook incidents, first reproduce with mocked tests or a
non-production target. Never paste credentials or full external tool output.
