# MultiscribeAgent

🗞️ AI-Powered Daily Newsletter — aggregate RSS / GitHub Trending / AI Search into a personalized daily digest and push to Feishu, WeCom, WeChat Official Account, Xiaohongshu, and DingTalk.

> Rebuilt from TypeScript (PrismFlowAgent) into Python with FastAPI + LangChain + SQLite.

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-GPL--3.0-green.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/yourusername/MultiscribeAgent?style=social)](https://github.com/yourusername/MultiscribeAgent/stargazers)

---

**🌐 Languages**: [English](./README.md) · [简体中文](./README_zh.md)

---

## 🔥 Key Features

| Feature | Description |
|---|---|
| 🗞️ **Multi-Source Ingestion** | RSS · GitHub Trending · AI Search (Perplexity / Phind) · Follow OPML Import |
| 🤖 **AI-Powered Curation** | LLM scoring + Loop self-reflection → Top-N selection from hundreds of items |
| 📡 **Multi-Platform Publishing** | Feishu · WeCom · WeChat Official · Xiaohongshu · DingTalk |
| 🧩 **Plugin Architecture** | Four plugin types: Adapter × Publisher × Tool × Skill — hot-swappable |
| ⚙️ **Zero-Code Setup** | Configure everything in `.env`, no code required |
| 🐳 **One-Command Deploy** | Docker Compose, spins up in one line |
| 🧠 **Knowledge + Memory** | RAG dedup · User preference memory · Cross-task context reuse |
| 📊 **Evaluation Framework** | LLM-as-Judge: summary quality / recommendation relevance / pipeline stability |
| 🔗 **MCP Integration** | External MCP clients (Claude Desktop / Cursor) can invoke collection & publishing |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- At least one LLM API key (OpenAI / Anthropic / Google)
- At least one publisher webhook (Feishu / WeCom / WeChat / Xiaohongshu / DingTalk)

### Installation

```bash
# Clone the repo
git clone https://github.com/yourusername/MultiscribeAgent.git
cd MultiscribeAgent

# Install dependencies
uv sync --extra dev

# Create env file and data dir
cp .env.example .env
mkdir data
```

### Configure `.env`

```dotenv
# ========== LLM Configuration ==========
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_BASE_URL=https://your-relay.com/v1   # Fill when using a relay API

# Proxy (optional, required when using relay)
HTTP_PROXY=http://127.0.0.1:7892

# ========== Publisher Configuration ==========
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your-hook-id
FEISHU_SECRET=your-signing-secret               # Optional, Feishu HMAC signing secret
WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key
```

### Run Your First Digest

```bash
uv run python -m multiscribe_agent digest
```

The default source is BBC News RSS. It curates Top-5 items and pushes to configured Feishu and WeCom bots.

---

## 📖 Advanced Usage

### Specify RSS Source and Push Targets

```bash
uv run python -m multiscribe_agent digest \
  --adapter rss \
  --rss-url https://hnews.dev/rss \
  --top-n 5 \
  --target feishu_bot,wecom_bot
```

### Start API Service (Web Console)

```bash
uv run python -m multiscribe_agent serve --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` to access the admin dashboard.

### Docker Deployment

```bash
docker compose up --build
```

API is available at `http://localhost:8000`.

### API Authentication

```bash
# Get JWT
curl -X POST http://127.0.0.1:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"password":"your-password"}'

# Call protected endpoints
curl http://127.0.0.1:8000/api/dashboard/stats \
  -H "Authorization: Bearer <access_token>"
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      ingestion layer                          │
│   RSS Adapter  ·  GitHub Trending  ·  AI Search  ·  ...    │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                        core layer                            │
│     SQLite (WAL)  ·  FTS5  ·  aiosqlite  ·  KV Repository │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                         llm layer                           │
│          OpenAI  ·  Anthropic  ·  Google  ·  Ollama         │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       agents layer                          │
│   Agent Harness (ReAct)  ·  Daily Digest Pipeline  ·  DAG  │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     publishing layer                         │
│   Feishu  ·  WeCom  ·  WeChat Official  ·  Xiaohongshu  ·  DingTalk  ·  RSS   │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                         api layer                            │
│            FastAPI  ·  SSE  ·  JWT  ·  structlog             │
└─────────────────────────────────────────────────────────────┘
```

**Stack**: Python 3.12+ · FastAPI · LangChain · LangGraph · SQLite WAL + FTS5 · sqlite-vec · structlog · pytest · ruff · mypy

---

## 📦 Roadmap

### MVP — Completed ✅

| Feature | Description |
|---|---|
| ✅ RSS Ingestion | Hacker News / BBC News and standard RSS / Atom feeds |
| ✅ AI Curation | LLM scoring + Loop self-reflection Top-N selection |
| ✅ Feishu Publishing | Markdown card + HMAC signing |
| ✅ WeCom Publishing | Markdown card |
| ✅ DAG Workflow Engine | Topological sort + parallel execution + cycle detection |
| ✅ Scheduler | APScheduler hot-reload + task_logs |
| ✅ API + CLI | FastAPI + JWT + structlog |
| ✅ Docker Deploy | `docker compose up` in one line |

### Stage 1 — In Progress 🚧

| Feature | Status |
|---|---|
| 🟡 GitHub Trending Adapter | In progress |
| 🟡 AI Search (Perplexity / Phind) | In progress |
| 🟡 WeChat Official Account Publishing | In progress |
| 🟡 Xiaohongshu Note Publishing | In progress |
| 🟡 DingTalk Bot Publishing | In progress |
| 🟡 Frontend Dashboard (Knowledge + Memory) | In progress |

### Stage 2+ — Planned 📋

| Feature | Planned Version |
|---|---|
| 📋 RAG Knowledge Base (sqlite-vec + FTS5 + RRF) | v0.2 |
| 📋 User Preference Memory | v0.2 |
| 📋 MCP External Interface | v0.3 |
| 📋 Built-in Skills (Tech Weekly / Multi-Source / Smart Rec) | v0.3 |
| 📋 LLM-as-Judge Evaluation | v0.4 |
| 📋 Full-Stack OTel Observability | v0.4 |
| 📋 Multi-Round Loop Self-Reflection | v0.5 |

---

## 📁 Project Structure

```
MultiscribeAgent/
├── src/multiscribe_agent/          # Python source
│   ├── agents/                      # Agent Harness · DAG · Pipeline
│   ├── core/                        # DB · Repository · FTS5
│   ├── domain/models.py            # Core domain models
│   ├── llm/                         # LLM Providers (OpenAI / Anthropic / ...)
│   ├── plugins/                     # Four plugin types
│   ├── adapters/                    # Ingestion adapters (RSS · GitHub · AI Search)
│   ├── publishers/                  # Publishers (Feishu · WeCom · WeChat · DingTalk)
│   ├── scheduler/                  # APScheduler
│   ├── api/routes/                  # FastAPI routes
│   └── observability/              # structlog · OTel
├── frontend/                        # React admin dashboard
│   ├── src/
│   │   ├── pages/                  # Dashboard · Knowledge · Memory · Settings ...
│   │   ├── services/               # API client layer
│   │   └── components/             # Layout components
│   └── dist/                        # Build output (Docker mount)
├── tests/                          # pytest suite
├── scripts/                        # Convenience entry scripts
├── docs/                           # Architecture docs · MVP spec · Phase board
├── .env.example                    # Config template
├── docker-compose.yml             # Docker deployment
├── Dockerfile                      # Python container image
└── pyproject.toml                  # uv project config
```

---

## ⚙️ Configuration Reference

| Variable | Required | Description |
|---|:---:|---|
| `OPENAI_API_KEY` | ✅* | OpenAI API key |
| `ANTHROPIC_API_KEY` | ✅* | Anthropic API key |
| `GOOGLE_API_KEY` | ✅* | Google API key |
| `OPENAI_API_BASE_URL` | - | Relay API endpoint (e.g. `https://your-relay.com/v1`) |
| `ANTHROPIC_API_BASE_URL` | - | Anthropic relay endpoint |
| `HTTP_PROXY` | - | HTTP proxy (e.g. `http://127.0.0.1:7892`) |
| `FEISHU_WEBHOOK` | ✅* | Feishu bot Webhook URL |
| `FEISHU_SECRET` | - | Feishu HMAC signing secret |
| `WECOM_WEBHOOK` | ✅* | WeCom bot Webhook URL |
| `DEFAULT_CURATION_PROVIDER_ID` | - | Default provider ID (default: `default-openai`) |
| `DEFAULT_CURATION_MODEL` | - | Default model (e.g. `gpt-5.4-mini`) |
| `DEFAULT_DIGEST_TARGETS` | - | Default push targets (comma-separated) |
| `DEFAULT_DIGEST_TOP_N` | - | Default curation count (default: 5) |
| `SYSTEM_PASSWORD` | - | API admin password (dev default: `admin123`) |
| `JWT_SECRET` | - | JWT signing secret |
| `DB_PATH` | - | SQLite path (default: `data/database.sqlite`) |
| `LOG_LEVEL` | - | Log level (default: `INFO`) |

> `✅*` At least one LLM key and one publisher webhook are required.

---

## 🌐 Languages

- [English](README.md)
- [简体中文](README_zh.md)

---

## 🤝 Contributing

Issues and Pull Requests are welcome!

```bash
# Clone and install dev dependencies
git clone https://github.com/yourusername/MultiscribeAgent.git
cd MultiscribeAgent
uv sync --extra dev

# Quality gates
uv run ruff check .
uv run mypy src
uv run pytest -q
```

---

## 📄 License

GPL-3.0-only — see [LICENSE](LICENSE)

---

## 🙏 Acknowledgements & Lineage

| Project | Role |
|---|---|
| [PrismFlowAgent](https://github.com/yourusername/PrismFlowAgent) | TypeScript original, refactoring base |
| [LangChain](https://github.com/langchain-ai/langchain) | LLM orchestration framework |
| [FastAPI](https://github.com/tiangolo/fastapi) | API framework |
| [SQLite](https://www.sqlite.org/) | Embedded database |
| [Tailwind CSS](https://tailwindcss.com/) | Frontend styling |

---

*⭐ If MultiscribeAgent saves you time, please give us a Star!*
