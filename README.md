# MultiscribeAgent

MultiscribeAgent is a Python reconstruction of PrismFlowAgent that turns RSS feeds into
AI-curated daily digests and delivers them to Feishu and Enterprise WeCom through a declarative
agent, workflow, plugin, and scheduler architecture.

## Quick Start

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), one OpenAI or Anthropic API key,
and configured Feishu and/or Enterprise WeCom group-bot webhooks.

```bash
uv sync --extra dev
cp .env.example .env
mkdir data
```

Edit `.env` with at least one LLM key and your configured publisher webhooks:

```dotenv
OPENAI_API_KEY=...
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/...
WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...
```

For Anthropic, set `ANTHROPIC_API_KEY` and change `DEFAULT_CURATION_PROVIDER_ID` and
`DEFAULT_CURATION_MODEL` to an Anthropic provider/model pair. The first digest startup creates
the default curation agent automatically. Run a digest without starting the HTTP service:

```bash
uv run python -m multiscribe_agent digest
```

The default source is the public Hacker News RSS feed. Choose another feed or a subset of targets
when needed:

```bash
uv run python -m multiscribe_agent digest --adapter rss --rss-url https://feeds.bbci.co.uk/news/rss.xml --top-n 5 --target feishu_bot,wecom_bot
```

The command records a `task_logs` lifecycle and prints a delivery summary. The equivalent
convenience entry point is:

```bash
uv run python scripts/run_digest.py
```

## API Mode

Start the authenticated API service:

```bash
uv run python -m multiscribe_agent serve --host 0.0.0.0 --port 8000
```

Use the development password from `.env` (or the documented development default) to obtain a JWT,
then call protected routes:

```bash
curl -X POST http://127.0.0.1:8000/api/login -H "Content-Type: application/json" -d '{"password":"admin123"}'
curl http://127.0.0.1:8000/api/dashboard/stats -H "Authorization: Bearer <access_token>"
```

## Docker

Copy and configure `.env` first, then build and run the API. The Compose service mounts `data/`
so SQLite data and task logs persist across container restarts.

```bash
docker compose up --build
```

The API is available at `http://127.0.0.1:8000`.

## Configuration

| Variable | Purpose |
| :--- | :--- |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Provider credential for the default curation agent |
| `FEISHU_WEBHOOK`, `FEISHU_SECRET` | Feishu group-bot delivery, with optional signing secret |
| `WECOM_WEBHOOK` | Enterprise WeCom group-bot delivery |
| `DEFAULT_CURATION_PROVIDER_ID`, `DEFAULT_CURATION_MODEL` | Select the default AgentDefinition provider and model |
| `DEFAULT_DIGEST_TARGETS`, `DEFAULT_DIGEST_TOP_N` | Comma-separated target IDs and curation count |
| `DB_PATH`, `LOG_LEVEL` | SQLite location and structured-log level |
| `SYSTEM_PASSWORD`, `JWT_SECRET` | API authentication configuration |

See [`.env.example`](.env.example) for all variables. Do not commit `.env`, webhook URLs, or API
keys.

## Architecture And Progress

The component boundaries and dependency direction are described in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). The MVP scope is in
[`docs/MVP.md`](docs/MVP.md), and the phase board is
[`docs/phases/README.md`](docs/phases/README.md).

## License

GPL-3.0-only.
