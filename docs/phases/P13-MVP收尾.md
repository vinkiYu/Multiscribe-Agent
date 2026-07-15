# P13 — MVP 收尾（e2e + 打包 + 文档）

> **状态**：未开始 · **依赖**：P0-P12 全部 · **MVP 交付包**

## 目标

跑通 MVP 端到端真实场景（真实 RSS + 真实 LLM + 真实飞书/企微推送），完善 README/Docker/.env.example，使新用户 10 分钟内跑通。MVP 正式交付。

## 前置依赖

P0-P12 全部通过 review。

## 可改范围（白名单）

- `README.md`（完整化）
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`（核对完整）
- `.dockerignore`
- `src/multiscribe_agent/cli.py`（补 `digest` 子命令：CLI 直接触发流水线，不走 HTTP）
- `scripts/run_digest.py`（便捷脚本：一次性触发每日推送）
- `src/multiscribe_agent/resources/prompts/digest.md`（确认 prompt 完整，P4/P11 已建）
- `tests/e2e/test_daily_digest_e2e.py`（`@pytest.mark.e2e`，默认跳过）
- `AGENTS.md`（更新阶段记录区：P0-P13 全通过）
- `docs/phases/README.md`（看板状态更新）

## 禁止改动（黑名单）

- 不重构已通过 review 的业务代码（除非 e2e 暴露 bug，此时停下报告，不擅改）。
- 不加新 MVP 功能（超出范围的新需求进后置包）。

## 详细任务

### T1. e2e 测试（标记 e2e，默认跳过）

`tests/e2e/test_daily_digest_e2e.py`：
- 用真实配置（从 `.env` 读 webhook/key）。
- 真实抓取一个公开 RSS（如 Hacker News `https://hnews.dev/rss` 或 `https://feeds.bbci.co.uk/news/rss.xml`）。
- 真实 LLM 精选（需配 OPENAI/ANTHROPIC key）。
- 真实推送到飞书 + 企微。
- 断言：流水线返回 success；fanout 各端 status=success（或至少一个成功）。
- **默认跳过**（addopts `-m "not e2e"`），需 `uv run pytest -m e2e` 显式跑。
- 缺 key/webhook 时 `pytest.skip`。

### T2. CLI digest 子命令

`multiscribe-agent digest`：读 `.env` + 默认 DailyDigestConfig → 调流水线 → 打印结果摘要。方便不用启 HTTP 服务也能跑一次推送。
- 支持 `--adapter rss --top-n 5 --target feishu_bot,wecom_bot` 等参数。

### T3. `scripts/run_digest.py`

便捷入口：`uv run python scripts/run_digest.py`，等价 CLI digest，给不熟悉 CLI 的用户。

### T4. Dockerfile + docker-compose

- `Dockerfile`：基于 `python:3.12-slim`，`uv` 安装，复制 src，`CMD uvicorn` 或 `python -m multiscribe_agent serve`。
- `docker-compose.yml`：服务 `app`，挂载 `data/` 卷，`env_file: .env`，端口 8000。
- `.dockerignore`：`.git`, `data/`, `__pycache__`, `.venv`, `tests/`, `docs/`。

### T5. README 完整化

结构：
- 项目简介（一段话）+ 定位（Python 重构版 + 新增推送）。
- 快速开始：`uv sync --extra dev` → `cp .env.example .env` → 填 key/webhook → `uv run python -m multiscribe_agent digest`（10 分钟跑通）。
- API 模式：`uv run python -m multiscribe_agent serve` + curl 示例。
- Docker：`docker compose up`。
- 架构一览（链接 docs/ARCHITECTURE.md）。
- 阶段进度（链接 docs/phases/README.md）。
- 配置说明（关键 .env 项）。
- 许可证 GPL-3.0。

### T6. .env.example 核对

确保所有 MVP 用到的 key 都列出且有注释（飞书 webhook+secret、企微 webhook、OPENAI/ANTHROPIC key、SYSTEM_PASSWORD、JWT_SECRET、DB_PATH、LOG_LEVEL、ACTIVE_AI_PROVIDER_ID）。

### T7. AGENTS.md / 看板更新

- AGENTS.md §8 阶段记录区：P0-P13 全标「已通过」+ 通过日期。
- `docs/phases/README.md`：状态更新。

## 验收条件

1. **e2e 真实场景跑通**（核心）：配好 .env 后 `uv run pytest tests/e2e -m e2e` 成功，飞书/企微群真实收到推送（贴截图）。或手动 `uv run python -m multiscribe_agent digest` 成功（贴终端输出 + 推送截图）。
2. CLI `digest` / `serve` 子命令工作。
3. `docker compose up` 能起服务（贴启动日志）。
4. README 指引可让新用户 10 分钟跑通（自检命令清单齐全）。
5. .env.example 完整无遗漏。
6. AGENTS.md 阶段记录更新。

## 测试方式

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest -q                    # 全套（不含 e2e）
uv run pytest -m e2e -q             # 真实 e2e（需配 key/webhook）
uv run python -m multiscribe_agent digest   # 手动跑一次推送
docker compose up --build           # 容器验证
```
**e2e 真实推送截图必须附 review**（飞书卡片 + 企微消息各一张，或至少一张）。

## 完成定义

- 上述 6 条全满足，**尤其 e2e 真实推送截图**。
- 全套 pytest（含 e2e）绿。
- README 可用。
- **MVP 正式交付**：`docs/phases/README.md` MVP 部分全绿。

## MVP 交付判据（供规划 review 用）

P13 通过 = MVP 完成。判据：
1. 一条命令（CLI/API/定时）触发，飞书 + 企微真实收到当日 AI 精选推送。
2. task_logs 完整记录全链路。
3. structlog 无 ERROR。
4. 质量门全绿。
5. 文档可让新人上手。
满足则放行进入后置包（P14+）阶段。
