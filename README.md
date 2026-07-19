# MultiscribeAgent

🗞️ AI 驱动的每日资讯采集与智能推送平台 — 将 RSS / GitHub Trending / AI 搜索汇聚为个性化日报，推送至飞书、企微、公众号、小红书、钉钉等平台。

> 本项目由 TypeScript（PrismFlowAgent）重构为 Python，基于 FastAPI + LangChain + SQLite 构建。

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-GPL--3.0-green.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/vinkiYu/Multiscribe-Agent?style=social)](https://github.com/vinkiYu/Multiscribe-Agent/stargazers)

---

**🌐 语言**: [简体中文](./README.md) · [English](./README.en.md)

---

## 🔥 核心特性

| 特性 | 说明 |
|---|---|
| 🗞️ **多源采集** | RSS / GitHub Trending / AI 搜索（Perplexity / Phind）/ Follow OPML 导入 |
| 🤖 **AI 智能精选** | 基于 LLM 评分 + Loop 自评，自动从海量条目中选出最有价值的 Top-N |
| 📡 **多端推送** | 飞书机器人 · 企微机器人 · 微信公众号 · 小红书 · 钉钉 |
| 🧩 **插件化架构** | 适配器（Adapter）× 发布器（Publisher）× 工具（Tool）× 技能（Skill）四类插件热插拔 |
| ⚙️ **声明式配置** | 零代码，`.env` 配置即可驱动完整流水线 |
| 🐳 **一键部署** | Docker Compose，一行命令起服务 |
| 🧠 **知识库 + 记忆** | 历史内容去重（RAG） · 用户偏好记忆 · 跨任务上下文复用 |
| 📊 **评估框架** | LLM-as-Judge，量化摘要质量 / 推荐相关性 / 流程稳定性 |
| 🔗 **MCP 扩展** | 外部 MCP 客户端（Claude Desktop / Cursor）可直接调用采集与推送能力 |

---

## 🚀 快速上手

### 前置要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- 至少 1 个 LLM API Key（OpenAI / Anthropic / Google）
- 至少 1 个推送端 Webhook（飞书 / 企微 / 公众号 / 小红书 / 钉钉）

### 安装

```bash
# 克隆项目
git clone https://github.com/vinkiYu/Multiscribe-Agent.git
cd Multiscribe-Agent

# 安装依赖
uv sync --extra dev

# 创建环境配置
cp .env.example .env
mkdir data
```

### 配置 `.env`

```dotenv
# ========== LLM 配置 ==========
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_BASE_URL=https://your-relay.com/v1   # 使用中转 API 时填写

# 代理（可选，使用中转时填写）
HTTP_PROXY=http://127.0.0.1:7892

# ========== 推送端配置 ==========
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your-hook-id
FEISHU_SECRET=your-signing-secret               # 可选，飞书加签密钥
WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key
```

### 运行首次采集推送

```bash
uv run python -m multiscribe_agent digest
```

默认使用 BBC News RSS 源，精选 Top-5 条目推送到飞书和企微机器人（取决于 `.env` 配置）。

---

## 📖 进阶用法

### 指定 RSS 源与推送目标

```bash
uv run python -m multiscribe_agent digest \
  --adapter rss \
  --rss-url https://hnews.dev/rss \
  --top-n 5 \
  --target feishu_bot,wecom_bot
```

### 启动 API 服务（Web 控制台）

```bash
uv run python -m multiscribe_agent serve --host 0.0.0.0 --port 8000
```

访问 `http://localhost:8000` 进入管理后台。

### Docker 部署

```bash
docker compose up --build
```

API 服务在 `http://localhost:8000` 可用。

### API 认证

```bash
# 获取 JWT
curl -X POST http://127.0.0.1:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"password":"your-password"}'

# 调用受保护接口
curl http://127.0.0.1:8000/api/dashboard/stats \
  -H "Authorization: Bearer <access_token>"
```

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      ingestion 层                           │
│   RSS Adapter  ·  GitHub Trending  ·  AI Search  ·  ...    │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       core 层                                │
│     SQLite (WAL)  ·  FTS5  ·  aiosqlite  ·  KV Repository  │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       llm 层                                │
│         OpenAI  ·  Anthropic  ·  Google  ·  Ollama          │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     agents 层                               │
│   Agent Harness (ReAct)  ·  Daily Digest Pipeline  ·  DAG   │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    publishing 层                            │
│   飞书  ·  企微  ·  公众号  ·  小红书  ·  钉钉  ·  RSS     │
└──────────────────────────────┬──────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      api 层                                 │
│          FastAPI  ·  SSE  ·  JWT  ·  structlog              │
└─────────────────────────────────────────────────────────────┘
```

**技术栈**：Python 3.12+ · FastAPI · LangChain · LangGraph · SQLite WAL + FTS5 · sqlite-vec · structlog · pytest · ruff · mypy

---

## 📦 功能路线图

### MVP 已完成 ✅

| 功能 | 说明 |
|---|---|
| ✅ RSS 采集 | Hacker News / BBC News 等标准 RSS / Atom 源 |
| ✅ AI 精选 | 基于 LLM 打分 + Loop 自评的 Top-N 精选 |
| ✅ 飞书推送 | Markdown 卡片 + 签名验证 |
| ✅ 企微推送 | Markdown 卡片 |
| ✅ DAG 工作流 | 拓扑排序 + 并行执行 + 环检测 |
| ✅ 调度器 | APScheduler 热重载 + task_logs |
| ✅ API + CLI | FastAPI + JWT + structlog |
| ✅ Docker 部署 | `docker compose up` 一键起服务 |

### 阶段一开发中 🚧

| 功能 | 状态 |
|---|---|
| ✅ GitHub Trending 采集 | 已完成 |
| ✅ AI 搜索（Perplexity / Phind） | 已完成 |
| ✅ 微信公众号图文发布 | 已完成 |
| ✅ 小红书笔记发布 | 已完成 |
| ✅ 钉钉机器人推送 | 已完成 |
| 🟡 前端管理后台（Knowledge + Memory） | 开发中 |

### 阶段二及后续规划 📋

| 功能 | 计划版本 |
|---|---|
| ✅ 知识库 RAG（sqlite-vec + FTS5 + RRF） | 已完成 |
| ✅ 用户偏好记忆系统 | 已完成 |
| ✅ MCP 外部调用接口 | 已完成 |
| ✅ 预置 Skill（技术周报 / 多源对比 / 智能推荐） | 已完成 |
| 📋 LLM-as-Judge 评估框架 | v0.4 |
| 📋 全链路 OTel 可观测性 | v0.4 |
| 📋 多轮 Loop 自评迭代 | v0.5 |

---

## 📁 项目结构

```
MultiscribeAgent/
├── src/multiscribe_agent/          # Python 源码
│   ├── agents/                      # Agent Harness · DAG · Pipeline
│   ├── core/                        # DB · Repository · FTS5
│   ├── domain/models.py             # 核心领域模型
│   ├── llm/                         # LLM Provider（OpenAI / Anthropic / ...）
│   ├── plugins/                     # 四类插件（Adapter / Publisher / Tool / Skill）
│   ├── adapters/                    # 采集适配器（RSS · GitHub · AI Search）
│   ├── publishers/                  # 发布器（飞书 · 企微 · 公众号 · 钉钉）
│   ├── scheduler/                  # APScheduler 调度器
│   ├── api/routes/                  # FastAPI 路由
│   └── observability/              # structlog · OTel
├── frontend/                        # React 管理后台
│   ├── src/
│   │   ├── pages/                  # Dashboard · Knowledge · Memory · Settings ...
│   │   ├── services/               # API 调用层
│   │   └── components/             # 布局组件
│   └── dist/                        # 构建产物（Docker 挂载）
├── tests/                          # pytest 测试套件
├── scripts/                        # 便捷入口脚本
├── docs/                           # 架构文档 · MVP 定义 · 阶段看板
├── .env.example                    # 配置模板
├── docker-compose.yml             # Docker 部署
├── Dockerfile                      # Python 容器镜像
└── pyproject.toml                  # uv 项目配置
```

---

## ⚙️ 配置参考

| 变量 | 必填 | 说明 |
|---|:---:|---|
| `OPENAI_API_KEY` | ✅* | OpenAI API Key（使用 OpenAI 时必填） |
| `ANTHROPIC_API_KEY` | ✅* | Anthropic API Key（使用 Anthropic 时必填） |
| `GOOGLE_API_KEY` | ✅* | Google API Key（使用 Gemini 时必填） |
| `OPENAI_API_BASE_URL` | - | 中转 API 端点（如 `https://your-relay.com/v1`） |
| `ANTHROPIC_API_BASE_URL` | - | Anthropic 中转端点 |
| `HTTP_PROXY` | - | HTTP 代理（如 `http://127.0.0.1:7892`） |
| `FEISHU_WEBHOOK` | ✅* | 飞书机器人 Webhook URL |
| `FEISHU_SECRET` | - | 飞书加签密钥 |
| `WECOM_WEBHOOK` | ✅* | 企微机器人 Webhook URL |
| `DEFAULT_CURATION_PROVIDER_ID` | - | 默认 Provider ID（默认 `default-openai`） |
| `DEFAULT_CURATION_MODEL` | - | 默认模型名（如 `gpt-5.4-mini`） |
| `DEFAULT_DIGEST_TARGETS` | - | 默认推送目标（逗号分隔，如 `feishu_bot,wecom_bot`） |
| `DEFAULT_DIGEST_TOP_N` | - | 每次精选条数（默认 5） |
| `SYSTEM_PASSWORD` | - | API 管理密码（开发默认 `admin123`） |
| `JWT_SECRET` | - | JWT 签名密钥（建议生产环境随机生成） |
| `DB_PATH` | - | SQLite 数据库路径（默认 `data/database.sqlite`） |
| `LOG_LEVEL` | - | 日志级别（默认 `INFO`） |

> `✅*` 至少填写一个 LLM Key 和一个推送端 Webhook

---

## 🌐 多语言

- [简体中文](README.md)
- [English](README.en.md)

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

```bash
# 克隆并安装开发依赖
git clone https://github.com/vinkiYu/Multiscribe-Agent.git
cd Multiscribe-Agent
uv sync --extra dev

# 质量门检查
uv run ruff check .
uv run mypy src
uv run pytest -q
```

---

## 📄 许可证

GPL-3.0-only — 详见 [LICENSE](LICENSE)

---

## 🙏 致谢与谱系

| 项目 | 作用 |
|---|---|
| [PrismFlowAgent](https://github.com/vinkiYu/PrismFlowAgent) | TypeScript 原始实现，本项目的重构起点 |
| [LangChain](https://github.com/langchain-ai/langchain) | LLM 编排框架 |
| [FastAPI](https://github.com/tiangolo/fastapi) | API 框架 |
| [SQLite](https://www.sqlite.org/) | 嵌入式数据库 |
| [Tailwind CSS](https://tailwindcss.com/) | 前端样式框架 |

---

*⭐ 如果这个项目对你有帮助，请给我们一个 Star！*
