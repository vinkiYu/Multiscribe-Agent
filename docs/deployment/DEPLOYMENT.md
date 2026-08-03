# Deployment Guide

This guide covers a local development installation, a Docker Compose
deployment, and a PostgreSQL production-style deployment. The API listens on
port `8000` by default. The React console is served by FastAPI when
`frontend/dist` exists; otherwise run Vite separately during development.

## 1. Requirements

### Required

- Python 3.12 or newer.
- `uv` for backend dependency management.
- Node.js 20 or newer and npm for the console.
- Git and a writable `data/` and `logs/` directory.

### Optional

- Docker Engine and Docker Compose v2 for container deployment.
- PostgreSQL 16 and Redis 7 for a multi-process deployment.
- `uv sync --extra postgres` for the async PostgreSQL driver.
- `uv sync --extra observability` for OpenTelemetry and Prometheus exporters.

SQLite is the default and is suitable for a single-process installation. Use
PostgreSQL and Redis when several workers or scheduler instances will run.

## 2. Local backend

From the repository root:

```bash
uv sync
cp .env.example .env
```

On PowerShell, use `Copy-Item .env.example .env` instead of `cp`. Edit `.env`
with a password, a random JWT secret, and at least one provider credential.
Webhook values are optional until publishing is enabled.

Initialize and start the API:

```bash
uv run python -m multiscribe_agent serve --host 127.0.0.1 --port 8000
```

Verify the process:

```bash
curl http://127.0.0.1:8000/healthz
```

Expected response: `{"status":"ok"}`. Open `http://127.0.0.1:8000/docs`
to inspect the generated OpenAPI schema.

## 3. Frontend development

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite normally serves the console on `http://localhost:5173`. Configure the
frontend API base URL according to the checked-in Vite environment settings if
the backend is not on the default origin. Run the production checks before a
release:

```bash
npm run lint
npm run build
```

To let FastAPI serve the console, build it from `frontend/` and restart the
backend. The API routes retain precedence over the static-file mount.

## 4. Docker Compose

The repository includes an application image plus PostgreSQL and Redis services:

```bash
Copy-Item .env.example .env       # PowerShell
docker compose up -d --build
docker compose ps
```

The Compose app waits for PostgreSQL health, but the default `.env.example`
selects SQLite. For the included PostgreSQL service, set:

```dotenv
DB_DRIVER=postgres
DATABASE_URL=postgresql://postgres:password@postgres:5432/multiscribe
```

The app exposes port `8000`; PostgreSQL is exposed on `5432` for local
administration. The Compose file persists SQLite data under `./data` and
PostgreSQL data in the named `postgres-data` volume.

Useful operations:

```bash
docker compose logs -f app
docker compose exec app uv run python -m multiscribe_agent --version
docker compose down
```

Do not use `docker compose down -v` unless deleting the PostgreSQL volume is
intentional.

## 5. PostgreSQL cutover

The controlled migration tool leaves the SQLite source unchanged:

```bash
docker compose up -d postgres
uv sync --extra postgres
uv run python -m scripts.migrate_sqlite_to_postgres \
  --sqlite-path data/database.sqlite --dry-run
uv run python -m scripts.migrate_sqlite_to_postgres \
  --sqlite-path data/database.sqlite \
  --pg-dsn postgresql://postgres:password@localhost:5432/multiscribe \
  --batch-size 500
```

Review `logs/migration-*.json` and confirm every table has zero drift. After
the repository SQL compatibility checklist is complete, set `DB_DRIVER` and
`DATABASE_URL`, then restart the API. See
[`postgres-migration-guide.md`](../postgres-migration-guide.md) for rollback
and retention rules.

## 6. Production checklist

- [ ] Set a strong `SYSTEM_PASSWORD` and `JWT_SECRET` outside source control.
- [ ] Use a provider endpoint and model that have been tested in this network.
- [ ] Configure only the publisher webhooks that should receive content.
- [ ] Set `DB_DRIVER=postgres` and a secret-managed `DATABASE_URL` for scale.
- [ ] Run Redis and keep `SCHEDULER_LOCK_STRICT_MODE=true` for multiple workers.
- [ ] Restrict the reverse proxy to HTTPS and forward `X-Forwarded-Proto`.
- [ ] Set `LOG_LEVEL=INFO` and keep `LOG_FILE` on persistent storage.
- [ ] Keep `ENABLE_SQL_AUDIT` aligned with the organization's audit policy.
- [ ] Build the console with `npm run build` and verify `/docs` and `/healthz`.
- [ ] Configure backups for PostgreSQL and retain the original SQLite file
      during a migration rollback window.
- [ ] Verify adapter health, daily digest preview, approval, and publishing
      with non-production targets before enabling the schedule.
- [ ] Monitor `/metrics`, task logs, provider errors, and alert history.

## 7. Reverse proxy example

Terminate TLS at the proxy and forward `/api/`, `/docs`, and the static
console to port `8000`. Preserve the `Authorization` and `X-Trace-Id` headers.
Do not cache authenticated API responses. A minimal Nginx-style arrangement is:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Trace-Id $request_id;
}
```

Add the organization's TLS, request-size, timeout, and IP allow-list policies
around this example.

## 8. Upgrade and rollback

1. Take a database backup and record the current Git revision.
2. Pull the release, run `uv sync --frozen`, and build the frontend.
3. Run the quality gate (`ruff`, `mypy`, and non-e2e tests).
4. Restart one application instance and check `/healthz`, `/metrics`, and the
   dashboard before restarting additional instances.
5. If the release is unhealthy, stop the new process, restore the previous
   revision and database backup, and set `DB_DRIVER=sqlite` only when the
   rollback target is the SQLite deployment.

Never delete migration sources or volumes as part of an automated rollback.
