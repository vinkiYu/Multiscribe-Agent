# Configuration Reference

MultiscribeAgent loads configuration in this order: built-in defaults, `.env`,
process environment, and persisted settings overrides stored by
`ConfigService`. Environment variable names without a `MULTISCRIBE_` prefix are
supported for backwards compatibility; deployments may use either spelling.
Never commit `.env`, API keys, webhook URLs, or database credentials.

## Authentication

| Variable | Type | Default | Description |
|---|---|---|---|
| `SYSTEM_PASSWORD` | string | empty | Local console password. Empty enables the development password path; set it in production. |
| `JWT_SECRET` | string | empty | JWT signing secret. Set a long random value in production. |
| `CONSOLE_SESSION_HOURS` | integer | `168` | Login token lifetime. Range: 1-8760 hours. |

## AI providers

| Variable | Type | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | string | empty | OpenAI or OpenAI-compatible provider credential. |
| `OPENAI_API_BASE_URL` | URL string | empty | Optional OpenAI-compatible `/v1` relay endpoint. |
| `ANTHROPIC_API_KEY` | string | empty | Anthropic provider credential. |
| `ANTHROPIC_API_BASE_URL` | URL string | empty | Optional Anthropic-compatible relay endpoint. |
| `GOOGLE_API_KEY` | string | empty | Google provider credential. |
| `OLLAMA_BASE_URL` | URL string | empty | Optional Ollama endpoint; built-in provider defaults to `http://localhost:11434`. |
| `ACTIVE_AI_PROVIDER_ID` | string | empty | Optional active provider selection used by clients. |
| `HTTP_PROXY` | URL string | empty | Outbound proxy for OpenAI and Anthropic calls. |
| `PROVIDER_CONTEXT_WINDOWS` | JSON object | `{}` | Per-model input context override, for example `{"custom-model":32000}`. |
| `PROVIDER_OUTPUT_TOKENS` | JSON object | `{}` | Per-model output reserve override, for example `{"custom-model":2048}`. |
| `DEFAULT_CURATION_PROVIDER_ID` | string | `default-openai` | Provider used by the default daily-digest curator. |
| `DEFAULT_CURATION_MODEL` | string | `gpt-4o-mini` | Model used by the default curator. Custom model names are accepted. |
| `DEFAULT_CURATION_TEMPERATURE` | number | `0.3` | Curator sampling temperature. |

Provider credentials are copied into the structured provider definitions during
settings validation. A non-empty `FEISHU_WEBHOOK` or `WECOM_WEBHOOK` also
enables its publisher definition. Empty environment values do not overwrite an
explicit structured setting.

## Daily digest defaults

| Variable | Type | Default | Description |
|---|---|---|---|
| `DEFAULT_DIGEST_TARGETS` | CSV | `feishu_bot,wecom_bot` | Publisher ids used by a default digest task. |
| `DEFAULT_DIGEST_TOP_N` | integer | `12` | Number of curated items. |
| `DEFAULT_DIGEST_FETCH_DAYS` | integer | `2` | Lookback days for candidate ingestion. |
| `DEFAULT_DIGEST_ADAPTER_IDS` | CSV | `rss-adapter` | Adapters used by the default digest. |
| `DAILY_AI_NEWS_CRON` | cron string | `0 9 * * *` | Archive task schedule in `Asia/Shanghai`. |
| `DAILY_AI_NEWS_RSS_URLS` | CSV URLs | built-in AI feeds | RSS/Atom feeds for the archive task. |
| `DAILY_AI_NEWS_FOLLOW_OPML_PATH` | path | empty | Optional Follow OPML export to add feeds. |
| `DAILY_AI_NEWS_SEARCH_QUERY` | string | AI/LLM/Agent/RAG query | Query for the injected AI Search adapter. |
| `MEMORY_IMPORTANCE_THRESHOLD` | integer | `5` | Minimum memory importance for retrieval. Range: 0-10. |
| `MEMORY_DEFAULT_PUSH_TIME` | `HH:MM` string | `09:00` | User preference default push time. |

CSV values are comma-separated and whitespace is trimmed. The two preview
fields are schedule JSON fields, not environment variables:
`preview_mode` (usually `preview_first`) and `preview_targets`.

## Publishers and notifications

| Variable | Type | Default | Description |
|---|---|---|---|
| `FEISHU_WEBHOOK` | URL string | empty | Feishu bot webhook. Enables `feishu_bot` when non-empty. |
| `FEISHU_SECRET` | string | empty | Optional Feishu HMAC signing secret. |
| `WECOM_WEBHOOK` | URL string | empty | WeCom bot webhook. Enables `wecom_bot` when non-empty. |
| `ADAPTER_HEALTH_FAILURE_THRESHOLD` | integer | `3` | Consecutive adapter failures before automatic disablement. |
| `ADAPTER_HEALTH_ALERT_TARGETS` | CSV ids | empty | Publishers notified when an adapter is auto-disabled. |
| `ALERT_TARGETS` | CSV ids | empty | Publishers notified for system metric alerts. |

Publisher webhook values are secrets. They are redacted by settings APIs and
structured logging.

## Scheduler and distributed lock

| Variable | Type | Default | Description |
|---|---|---|---|
| `REDIS_URL` | URL string | `redis://localhost:6379/0` | Redis endpoint for the scheduler lock. |
| `SCHEDULER_LOCK_TTL_SECONDS` | integer | `7200` | Lock lease duration; must be positive. |
| `SCHEDULER_LOCK_STRICT_MODE` | boolean | `true` | If true, skip a task when Redis is unavailable; if false, warn and run without a lock. |

Strict mode is recommended whenever more than one scheduler process can run.
Non-strict mode can produce duplicate publishes during a Redis outage.

## Database

| Variable | Type | Default | Description |
|---|---|---|---|
| `DB_DRIVER` | `sqlite` or `postgres` | `sqlite` | Selects the database backend. |
| `DB_PATH` | path | `data/database.sqlite` | SQLite file when `DB_DRIVER=sqlite`. |
| `DATABASE_URL` / `DB_DSN` | PostgreSQL DSN | empty | PostgreSQL connection string when `DB_DRIVER=postgres`. |
| `DB_POOL_SIZE` | integer | `5` | PostgreSQL connection pool size. |
| `DB_POOL_TIMEOUT` | number | `30.0` | Seconds to wait for a pool connection. |
| `SLOW_QUERY_THRESHOLD_SECONDS` | number | `1.0` | Query duration threshold for slow-query metrics. |
| `ENABLE_SQL_AUDIT` | boolean | `true` | Record SQL timing metadata; SQL values are never logged. |

SQLite uses WAL mode and creates parent directories during initialization.
PostgreSQL requires the `postgres` optional dependency (`uv sync --extra
postgres`) and a reachable server.

## Logging and runtime safety

| Variable | Type | Default | Description |
|---|---|---|---|
| `LOG_LEVEL` | string | `INFO` | Structlog level (`DEBUG`, `INFO`, `WARNING`, or `ERROR`). |
| `LOG_FILE` | path | `logs/multiscribe-agent.log` | Rotating runtime log file (10 MB, five backups). |
| `CSRF_ENABLED` | boolean | `true` | Enable CSRF middleware for state-changing browser requests. |
| `CLOSED_PLUGINS` | CSV | empty | Disable selected plugin ids at bootstrap. |

Access logs contain method, path, status, and trace id. Sensitive keys such as
`token`, `secret`, `password`, `key`, `cookie`, and `webhook` are redacted.

## MCP and rate limiting

| Variable | Type | Default | Description |
|---|---|---|---|
| `MCP_API_KEY` | string | empty | Optional key for external MCP transport. |
| `MCP_DEFAULT_HOST` | host | `127.0.0.1` | MCP server bind host. |
| `MCP_DEFAULT_PORT` | integer | `8765` | MCP server port, range 1-65535. |
| `MCP_TRANSPORT` | `stdio` or `sse` | `stdio` | MCP transport mode. |

The human-facing rate limiter is enabled by default. Its built-in rules are:

| Path | Limit |
|---|---:|
| `/api/auth/login` | 10 requests / 60 seconds |
| `/api/agents/run` | 20 requests / 60 seconds |
| `/api/digest/run` | 5 requests / 60 seconds |

`/healthz`, `/metrics`, and `/api/ai/v1/` are exempt. Rate-limit rules can be
provided through persisted settings as a mapping of path to `[limit, window]`.

## Structured configuration examples

### Minimal local `.env`

```dotenv
SYSTEM_PASSWORD=change-me
JWT_SECRET=replace-with-a-random-secret
OPENAI_API_KEY=replace-me
DB_DRIVER=sqlite
LOG_FILE=logs/multiscribe-agent.log
```

### Relay endpoint and custom model

```dotenv
OPENAI_API_KEY=relay-key
OPENAI_API_BASE_URL=https://relay.example.com/v1
DEFAULT_CURATION_MODEL=my-compatible-model
PROVIDER_CONTEXT_WINDOWS={"my-compatible-model":64000}
PROVIDER_OUTPUT_TOKENS={"my-compatible-model":4096}
```

### PostgreSQL and strict scheduler

```dotenv
DB_DRIVER=postgres
DATABASE_URL=postgresql://postgres:password@localhost:5432/multiscribe
REDIS_URL=redis://localhost:6379/0
SCHEDULER_LOCK_STRICT_MODE=true
```

After changing environment values, restart the API process. Persisted settings
overrides are applied by `ConfigService` after environment loading and should
be reviewed through `GET /api/settings`.

## Provider defaults and model windows

The built-in provider catalog is intentionally conservative. It is a UI
catalog, not a runtime allow-list: a compatible relay may accept a model name
that is not listed here.

| Provider id | Type | Default model | Context window | Output reserve |
|---|---|---|---:|---:|
| `default-openai` | openai | `gpt-4o` | 128000 | 16384 |
| `default-anthropic` | anthropic | `claude-sonnet-4-5` | 200000 | 8192 |
| `default-google` | google | `gemini-2.0-flash` | 1048576 | 4096 |
| `default-ollama` | ollama | `qwen2.5` | 32768 | 4096 |

When a model has no explicit entry in `PROVIDER_CONTEXT_WINDOWS`, the runtime
uses a compatibility window of 128000 tokens. When no output override exists,
the output reserve is 4096 tokens. The harness subtracts this reserve, tool
schema tokens, and a safety margin before calling a provider.

Positive integer overrides are accepted; malformed JSON, non-object JSON,
boolean values, and non-positive numbers are ignored. This makes a typo
fail-safe without preventing the service from starting. The provider itself
still decides whether a custom model exists at the configured endpoint.

## Variable aliases and precedence

Every operational variable supports the legacy unprefixed name and the
namespaced `MULTISCRIBE_` form where shown in `SystemSettings`. For example,
`OPENAI_API_KEY` and `MULTISCRIBE_OPENAI_API_KEY` are equivalent. If both are
present, the explicit validation alias order in `SystemSettings` determines
which value wins; use one spelling per deployment to avoid ambiguity.

The effective value is calculated as follows:

1. The Pydantic built-in default is loaded.
2. `.env` and process environment values are parsed and validated.
3. Flat credentials are bound to the matching provider or publisher object.
4. Persisted `ConfigService` overrides are merged when the database is ready.
5. API clients receive a redacted representation of the effective settings.

Changing a provider key, database DSN, scheduler lock, or webhook requires a
process restart. Changing a persisted non-secret setting through the settings
API takes effect after the service reload path is invoked.

## Validation and safe values

- Session hours, pool size, lock TTL, MCP port, and all token limits must be
  positive and within their documented bounds.
- Database driver must be exactly `sqlite` or `postgres`.
- `MCP_TRANSPORT` must be `stdio` or `sse`.
- Rate-limit paths must begin with `/`; each limit and window must be positive.
- Cron values are validated when a schedule is created or reloaded.
- CSV lists drop blank entries and preserve item order after trimming.
- Webhook and secret values are never emitted in structured logs or settings
  responses.

## Environment-specific recommendations

### Development

Use SQLite, a local log file, one scheduler process, and a mock or relay
provider. Keep `CSRF_ENABLED=true` so browser behavior matches production.

### Staging

Use a separate PostgreSQL database, Redis lock, non-production publisher
webhooks, and a short session lifetime. Enable observability extras and test a
preview/approve/reject cycle before enabling scheduled delivery.

### Production

Load secrets from the deployment secret manager rather than committing a
dotenv file. Use PostgreSQL with backups, Redis with persistence, HTTPS at the
reverse proxy, strict scheduler locking, and `LOG_LEVEL=INFO`. Configure
`ALERT_TARGETS` so provider and query failures reach an operator.

## Configuration change checklist

Before deploying a configuration change:

1. Validate JSON values with a JSON parser before placing them in `.env`.
2. Confirm the selected provider id and model are compatible with the endpoint.
3. Confirm every target id exists and its webhook is reachable in staging.
4. Restart the process and inspect the redacted settings response.
5. Run `/healthz`, the provider test, and a dry-run or preview digest.
6. Record the change without recording secret values.
