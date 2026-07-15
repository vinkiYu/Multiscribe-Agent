# 编码规范（硬约束）

> 所有贡献代码必须 100% 遵守。Codex 执行前必读。质量门：`ruff check . && ruff format --check . && mypy src && pytest` 全绿。

## 1. 格式与 Lint（ruff）

`pyproject.toml` 配置：
- `target-version = "py312"`
- `line-length = 100`
- 启用规则集：E, F, W, I(isort), UP, B, C4, SIM, RUF, ANN(强制注解), S(安全), PT(pytest)
- `ruff format` 统一格式（等价 black 风格）。

提交前：`ruff check . --fix && ruff format .`

## 2. 类型检查（mypy）

- `mypy --strict src`
- **全量类型注解**，所有函数签名必须标注参数与返回类型。
- 禁用 `Any`；如确需（动态配置/第三方不规范数据），须 `# type: ignore[xxx]` 并注释原因。
- 用 `from __future__ import annotations` 让注解延迟求值（避免前向引用问题）。
- 容器类型必须参数化：`list[str]` 而非 `list`；`dict[str, int]` 而非 `dict`。
- Pydantic 模型字段必标类型；Protocol 方法必标签名。

## 3. 命名约定

| 类别 | 约定 | 示例 |
| :--- | :--- | :--- |
| 类 | PascalCase | `AgentExecutor`, `RSSAdapter` |
| 函数/方法/变量 | snake_case | `run_daily_digest`, `tool_calls` |
| 常量 | UPPER_SNAKE | `DEFAULT_PORT`, `MAX_ROUNDS` |
| 模块/文件 | snake_case | `agent_executor.py`, `daily_digest.py` |
| 私有 | 前缀下划线 | `_build_graph`, `_internal` |
| 类型别名 | PascalCase | `JsonDict = dict[str, Any]`（受限场景） |
| Pydantic 模型 | PascalCase，字段 snake_case | `class UnifiedData: published_date: str` |

## 4. import 规范

- 顺序（ruff isort 强制）：`__future__` → 标准库 → 第三方 → 本项目（`multiscribe_agent`），组间空行。
- 用绝对导入：`from multiscribe_agent.domain.models import UnifiedData`。
- 禁止 `from module import *`。
- 仅导入用到的东西；类型导入可用 `if TYPE_CHECKING:` 守卫避免循环依赖。

## 5. 异步约定

- 所有 I/O（DB/HTTP/文件/LLM/Webhook）用 `async def`。
- **禁止在 async 函数中直接调用阻塞 I/O**；必要时 `await asyncio.to_thread(...)`。
- 并发用 `asyncio.gather`（带 `return_exceptions=True` 视场景）；限流用 `asyncio.Semaphore`。
- HTTP 客户端统一用 `httpx.AsyncClient`（不要用 requests）。
- 数据库用 `aiosqlite`。
- 所有 await 处考虑超时（`asyncio.wait_for`）与取消处理。

## 6. 错误处理

- 外部 I/O 一律 `try/except`，捕获**具体异常**（不要裸 `except:` 或 `except Exception:` 吞掉）。
- 抛领域异常（定义在 `core/errors.py`），不要抛裸字符串或 `Exception`。
- 异常要带上下文信息（哪个 adapter/tool/agent、什么输入）。
- 失败要记 `structlog` 日志（含 trace_id），但**不得记录密钥/隐私**。
- 不要静默失败（`pass`）；至少 log warning。

## 7. 日志（structlog）

- 用 `structlog`，结构化键值对：`log.info("agent_run_start", agent_id=..., round=...)`。
- **脱敏**：自动过滤 key 含 `token/secret/password/key/cookie/auth` 的值，输出掩码如 `abcd****wxyz`。
- 不用 `print()`（除 CLI 面向用户的输出）。
- 日志级别：DEBUG 细节 / INFO 关键节点 / WARNING 可恢复异常 / ERROR 失败 / CRITICAL 系统级。
- 每次 Agent/Workflow 运行绑定 `trace_id`、`run_id`，便于串联。

## 8. 配置与密钥

- 配置走 `.env` → `pydantic-settings` Settings → KV 表持久化覆盖。
- **严禁硬编码** token/key/password/secret。
- `.env` 在 `.gitignore`；提供 `.env.example`（占位符）。
- 测试用单独的 `.env.test` 或环境变量注入，不读生产配置。

## 9. 测试规范（pytest）

- 测试文件 `test_*.py`，放在 `tests/` 镜像 src 结构。
- 测试函数 `test_*`；用 `pytest-asyncio`（`@pytest.mark.asyncio`）。
- **不打真实网络**：外部 HTTP/LLM/Webhook 一律 mock（`respx` mock httpx，或自建 fake provider）。
- 需真实外部依赖的测试用 `@pytest.mark.e2e`，默认跳过（`--all-additional-reads` 时才跑）。
- 每个公共函数/类至少 1 个 happy path + 1 个边界/异常。
- 测试要快：单测 < 1s；用 fixture 复用 DB（内存 SQLite）。
- 覆盖核心：领域模型校验、仓储 CRUD、DAG 引擎排序、飞书/企微渲染、流水线编排。

## 10. 文档与注释

- 模块级 docstring 说明职责。
- 公共类/函数 docstring（Google 风格：Args/Returns/Raises）。
- 复杂逻辑注释「为什么」而非「是什么」。
- 类型即文档：优先用类型表达，少写显而易见的注释。

## 11. Git/提交

- 每个 phase 包的改动作为一组聚焦提交。
- commit message：`<type>(<scope>): <subject>`，如 `feat(dag): add cycle detection`。
- 不提交：`.env`、`data/`、`__pycache__`、`.venv`、`dist/`。
