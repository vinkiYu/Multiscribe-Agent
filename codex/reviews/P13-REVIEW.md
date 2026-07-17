# Review: `P13-MVP收尾`

**执行包：** `docs/phases/P13-MVP收尾.md`

**执行日期：** 2026-07-17

**执行者：** Codex

## 1. 执行结论

**BLOCKED，未完成 MVP 正式交付。**

P13 的代码、测试、CLI、Docker 工件和文档已实现，所有本地质量门均通过。真实 e2e 仍需要本机 `.env` 中的有效 LLM API key 与至少一个飞书或企微 Webhook；这些受控凭据当前不存在。Docker Compose 配置可解析，但 Docker Desktop Linux daemon 未启动，无法完成镜像构建和 `compose up` 运行验证。

## 2. 范围核对

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `README.md` | 修改 | 10 分钟上手、CLI/API/Docker/配置/许可证说明 |
| `Dockerfile` | 新增 | Python 3.12 + uv 的 API 容器镜像 |
| `docker-compose.yml` | 新增 | app 服务、8000 端口、`.env`、`data/` 挂载 |
| `.env.example` | 修改 | Anthropic 默认 provider/model 配置提示 |
| `.dockerignore` | 新增 | 排除密钥、数据、缓存和测试文档 |
| `src/multiscribe_agent/cli.py` | 修改 | `digest` 入口、RSS/目标参数、task-log 生命周期与结果摘要 |
| `scripts/run_digest.py` | 新增 | `digest` 的快捷入口 |
| `tests/e2e/test_daily_digest_e2e.py` | 新增 | 真实 RSS/LLM/Webhook/task_log opt-in e2e 与 CLI 默认映射测试 |
| `codex/reviews/P13-REVIEW.md` | 修改 | 当前阶段交付与阻塞证据 |

未修改 P4/P11 的执行器或流水线，以及其他 P13 黑名单业务代码。`DESIGN.md` 和 `docs/BRAND.md` 是用户已有的未跟踪文件，未改动。

## 3. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- |
| 1 | 真实 RSS + LLM + 飞书/企微推送 e2e，附截图 | ❌ 阻塞 | `tests/e2e/test_daily_digest_e2e.py` 已真实调用 RSS、ServiceContext、scheduler task log 和已启用 publisher；但 `pytest -m e2e -q` 为 `4 skipped`，本机缺 LLM key/Webhook，未发送消息也无截图。 |
| 2 | CLI `digest` / `serve` 可用 | ✅ | `python -m multiscribe_agent digest --help` 显示 `--adapter`、`--rss-url`、`--top-n`、`--target`；默认 `serve` 成功启动，`GET /openapi.json` 返回 200。 |
| 3 | `docker compose up` 可启动 | ❌ 环境阻塞 | `docker compose config` 成功；`docker compose build app` 连接 `dockerDesktopLinuxEngine` 失败，因为 Docker Desktop daemon 未运行。 |
| 4 | README 10 分钟上手 | ✅ | `README.md` 覆盖 uv、`.env`、`mkdir data`、digest、API、Docker、架构、进度和 GPL-3.0。 |
| 5 | `.env.example` 完整 | ✅ | 保留 API key、两类 webhook、`SYSTEM_PASSWORD`、`JWT_SECRET`、`DB_PATH`、`LOG_LEVEL`、provider 和 digest 默认项，并补充 Anthropic 选择提示。 |
| 6 | AGENTS.md / 阶段看板更新 | ❌ 未更新 | P13 尚未通过真实 e2e 与 Docker 验收，按看板规则不得标记已通过。 |

## 4. 详细任务完成情况

- **T1 e2e**：新增带 `@pytest.mark.e2e` 的真实端到端测试，缺少凭据时显式 `pytest.skip`；覆盖 RSS 抓取、LLM 精选、已配置 targets、scheduler task log 成功状态。另有非 e2e 测试验证 P0.5 的 `rss-adapter` 默认别名会解析为 P6 实际注册的 `rss` 插件 ID。
- **T2 CLI digest**：`digest` 直接创建 `ScheduleTask` 并经 `SchedulerService.execute_task()` 执行，因此手动运行也会记录完整 task_logs。默认 RSS 为任务包列举的 Hacker News，支持 `--adapter rss`、`--rss-url`、`--top-n`、`--target`。
- **T3 脚本**：`scripts/run_digest.py` 等价调用 `digest`，并保留传入命令行参数。
- **T4 Docker**：新增 Python 3.12 slim/uv Dockerfile、Compose app 服务和 data 卷；`.env` 设置为 optional，未配置时 API 仍可启动，配置后会自动加载。
- **T5/T6 文档与配置**：README 给出可操作命令和配置表；`.env.example` 对 Anthropic 默认 curation 配对给出明确提示。
- **T7 看板**：未标绿，因为阶段仍处于 BLOCKED 状态。

## 5. 测试与质量门（原始输出）

### `python -m ruff check .`

```text
All checks passed!
```

### `python -m ruff format --check .`

```text
115 files already formatted
```

### `python -m mypy src`

```text
Success: no issues found in 74 source files
```

### `python -m pytest -q -p no:cacheprovider`

```text
123 passed, 4 deselected in 7.00s
```

### `python -m pytest tests/e2e/test_daily_digest_e2e.py -q -p no:cacheprovider`

```text
.                                                                        [100%]
1 passed, 1 deselected in 0.50s
```

### `python -m pytest -m e2e -q -p no:cacheprovider`

```text
ssss                                                                     [100%]
4 skipped, 123 deselected in 3.09s
```

### CLI/API/Docker 诊断

```text
GET http://127.0.0.1:8001/openapi.json
200
```

```text
docker compose config
services:
  app:
    build: ...
    ports:
      - target: 8000
    volumes:
      - source: .../data
        target: /app/data
```

```text
docker compose build app
error during connect: Head "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/_ping":
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

## 6. 风险、遗留与取舍

- **真实 e2e 凭据：** 当前没有 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`FEISHU_WEBHOOK` 或 `WECOM_WEBHOOK`。P13 e2e 会在这些变量缺失时 skip，未发送外部消息。
- **截图：** 因未发生真实推送，无法提供飞书或企微消息截图；不得伪造。
- **Docker daemon：** Docker CLI 可用但 Docker Desktop Linux engine 未运行。启动 Docker Desktop 后可运行 `docker compose up --build` 完成容器验收。
- **API key/provider 对应：** 使用 Anthropic 时必须同时设置 `DEFAULT_CURATION_PROVIDER_ID=default-anthropic` 与兼容模型，README 和 `.env.example` 已提示。
- **未做的事：** 未更新阶段看板为通过，未改动黑名单业务代码，未提交 `.env`、data 或任何密钥。

## 7. 解除阻塞所需操作

1. 启动 Docker Desktop Linux containers，运行 `docker compose up --build` 并保存启动日志。
2. 在本机 `.env` 填入一个与 `DEFAULT_CURATION_PROVIDER_ID` 对应的有效 LLM API key，以及至少一个可接收消息的飞书或企微 Webhook；完整 MVP 验收建议同时配置两个目标。
3. 运行 `uv run pytest tests/e2e -m e2e -q` 或 `uv run python -m multiscribe_agent digest`，保存终端输出和实际消息截图，再交 ZCode 判定 P13。

## 8. 自评

- 我认为本包满足 `P13-MVP收尾.md` 的完成定义：**否**。
- 原因：真实推送截图和容器实际启动是硬验收，受本机受控凭据与未启动的 Docker daemon 阻塞。
