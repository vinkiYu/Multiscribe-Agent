# P12 — FastAPI 骨架 + JWT 认证 + 基础可观测

> **状态**：未开始 · **依赖**：P1-P11（组装各服务）

## 目标

搭建 FastAPI 应用：路由骨架、JWT 认证、关键端点（手动触发流水线/抓取、查询状态/日志）、structlog 结构化日志、CLI serve 子命令接通。让 MVP 能通过 API/CLI 操作。

## 前置依赖

P1-P11（各服务就绪，本包组装）。

## 可改范围（白名单）

- `src/multiscribe_agent/app.py`（FastAPI 应用工厂 + 中间件 + 异常处理）
- `src/multiscribe_agent/api/__init__.py`
- `src/multiscribe_agent/api/deps.py`（依赖注入：get services）
- `src/multiscribe_agent/api/security.py`（JWT 签发/校验）
- `src/multiscribe_agent/api/routes/__init__.py`
- `src/multiscribe_agent/api/routes/auth.py`
- `src/multiscribe_agent/api/routes/dashboard.py`
- `src/multiscribe_agent/api/routes/digest.py`（手动触发流水线）
- `src/multiscribe_agent/api/routes/agents.py`（agent CRUD + run，复用 P4）
- `src/multiscribe_agent/api/routes/workflows.py`（workflow CRUD + run，复用 P10）
- `src/multiscribe_agent/api/routes/schedules.py`（调度 CRUD + run_now）
- `src/multiscribe_agent/core/__init__.py`（若未建）
- `src/multiscribe_agent/core/logging.py`（structlog 配置）
- `src/multiscribe_agent/bootstrap.py`（ServiceContext 单例：组装 init_db + 各 service + scan_plugins + scheduler.start）
- `src/multiscribe_agent/cli.py`（实现 serve 子命令；其他子命令占位）
- `pyproject.toml`（追加：`fastapi>=0.115`，`uvicorn[standard]>=0.30`，`sse-starlette>=2.1`，`python-jose[cryptography]>=3.3`，`passlib>=1.7`）
- `tests/api/conftest.py`（httpx AsyncClient + TestClient + 内存 DB fixture）
- `tests/api/test_auth.py`
- `tests/api/test_dashboard.py`
- `tests/api/test_digest.py`
- `tests/api/test_agents_workflows.py`
- `tests/api/test_schedules.py`

## 禁止改动（黑名单）

- 不动各 service 的业务逻辑（仅组装调用）。
- 不做前端（P20）。
- 不实现完整 OTel（P23；本包仅 structlog）。
- 不动领域模型。

## 详细任务

### T1. `core/logging.py` — structlog

- 配置 structlog：JSON 输出（生产）/ console（开发，按 log_level）。
- 自动 bind `trace_id`（每请求生成 uuid）、`run_id`。
- **脱敏 processor**：递归过滤 key 含 `token/secret/password/key/cookie/auth/webhook` 的值 → 掩码。
- `get_logger() -> structlog.BoundLogger`。

### T2. `api/security.py` — JWT

- `create_access_token(subject, role, expires_hours) -> str`（用 Settings.jwt_secret；未设 secret 时开发回退固定值 + warn，生产抛错）。
- `decode_token(token) -> dict`。
- FastAPI dependency `get_current_user`：从 `Authorization: Bearer` 或 `?token=` 解析；非法抛 401。
- 默认密码机制：未配 system_password 用 `admin123`，token payload 带 `must_change_password`。
- 登录端点 `POST /api/login`：校验密码 → 发 token。

### T3. `app.py` — 应用工厂

- `create_app(settings) -> FastAPI`：加 CORS（可配 origin）、异常处理器（领域异常 → 合适 HTTP 码）、structlog access log 中间件、注册路由。
- 全局异常：`MultiscribeError` 子类映射到 HTTP 码（AuthError→401，ValidationError→400，ProviderError→502，NotFound→404 等）。

### T4. `bootstrap.py` — ServiceContext

```python
class ServiceContext:
    """单例：懒加载 + reload。"""
    db: Database
    ingestion: IngestionService
    publishing: PublishingService
    agent_executor: AgentExecutor
    workflow_engine: WorkflowEngine
    scheduler: SchedulerService
    config_service: ConfigService
    # ...
    async def init(self):  # init_db → scan_plugins → 实例化各 service → 注册 executors → scheduler.start
    async def reload(self):  # 停 scheduler → 重新 init
def get_context() -> ServiceContext: ...
```

- 把 P11 的 `daily_digest_executor` 注册进 `TaskExecutorRegistry`。
- scan_plugins（P5）+ 实例化已配置的 adapter/publisher（按 settings）。

### T5. 路由

- `POST /api/login` → token。
- `GET /api/dashboard/stats`：抓取统计、最近 task_log（mock-friendly）。
- `GET /api/dashboard/logs`：task_logs 列表（分页）。
- `POST /api/dashboard/ingest`：手动触发抓取（指定 adapter 或全部）。
- `POST /api/digest/run`：手动触发每日推送流水线（body: DailyDigestConfig 或默认）→ 返回 run 结果或 task_log_id。
- `GET/POST/DELETE /api/agents[/:id]`、`POST /api/agents/:id/run`（SSE 用 sse-starlette）。
- `GET/POST/DELETE /api/workflows[/:id]`、`POST /api/workflows/:id/run`（SSE）。
- `GET/POST/DELETE /api/schedules[/:id]`、`POST /api/schedules/:id/run`（run_now）。
- 所有非 login 端点经 `get_current_user`（除显式公开）。

### T6. CLI serve

- `cli.py` 的 `serve` 子命令：`uvicorn.run(create_app(...))`，host/port 可配（默认 127.0.0.1:8000）。
- 启动前 `await ServiceContext.init()`（用 lifespan）。

### T7. 测试

- `tests/api/conftest.py`：`async def client()` fixture → 用 `httpx.AsyncClient` + ASGI transport 跑 `create_app`，注入内存 DB + mock services。
- `tests/api/test_auth.py`：登录成功发 token；错误密码 401；默认密码 token 带 must_change_password；受保护端点无 token 401。
- `tests/api/test_dashboard.py`：stats/logs 返回结构；ingest 触发 IngestionService（mock 验证调用）。
- `tests/api/test_digest.py`：POST /api/digest/run 触发流水线（mock workflow_engine），返回结果。
- `tests/api/test_agents_workflows.py`：CRUD + run（SSE 端点用 TestClient 收事件）。
- `tests/api/test_schedules.py`：CRUD + run_now（mock scheduler）。

## 验收条件

1. FastAPI app 启动（`uv run python -m multiscribe_agent serve` 起得来）。
2. JWT 认证全链路（login → token → 受保护端点 → 401 无 token）。
3. structlog 输出结构化 JSON + 脱敏（webhook/secret 掩码，测试覆盖）。
4. 关键端点工作：digest/run、dashboard/ingest、agents/workflows/schedules CRUD。
5. SSE 事件流（agent run / workflow run）正确推送。
6. 领域异常 → HTTP 码映射正确。
7. ServiceContext 组装 + reload 工作。
8. 全测试绿（mock 外部，不打真实网络）。

## 测试方式

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest tests/api -q
uv run python -m multiscribe_agent serve --help  # 验证 CLI
```
原始输出贴 review。建议手动启动服务 + curl /api/login 一次，贴响应。

## 完成定义

验收全满足；API 骨架可用；structlog 脱敏有测试。P13 做真实 e2e 与打包收尾。
