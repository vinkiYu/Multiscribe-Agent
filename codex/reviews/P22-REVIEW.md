# Review: P22-Interop

**执行包**：`docs/phases/P22-Interop.md`  
**完成日期**：2026-07-19  
**执行者**：Codex

## 1. 范围核对

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/services/interop.py` | 新增 | API key 生成、sha256 存储、审批、验证、用量更新 |
| `src/multiscribe_agent/services/interop_rate_limit.py` | 新增 | key 维度滑动窗口限流 |
| `src/multiscribe_agent/services/interop_registry.py` | 新增 | OpenAI Function Calling tool schema 与执行注册表 |
| `src/multiscribe_agent/api/routes/ai_v1.py` | 新增 | `/register`、`/tools`、`/execute`、审批端点 |
| `src/multiscribe_agent/domain/models.py` | 修改 | 新增 frozen `InteropKey` |
| `src/multiscribe_agent/infra/db.py` | 修改 | 新增 `interop_keys` 表和 approved 索引 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 初始化 interop service/limiter/registry |
| `src/multiscribe_agent/app.py` | 修改 | 挂载 `ai_v1.router` |
| `tests/interop/*` | 新增 | API、service、rate limit 测试 |

白名单合规：`app.py` 已由 P22 rev1 补入白名单。未修改 P22 黑名单中的 MCP route/security/agent pipeline/front-end。

## 2. 验收对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `InteropKey` + sha256 hash，不存明文 | 通过 | `tests/interop/test_service_interop.py::test_key_is_hashed_and_verified` |
| 2 | 滑动窗口 rate limiter | 通过 | `tests/interop/test_rate_limit.py` |
| 3 | ToolRegistry + OpenAI Function Calling schema | 通过 | `tests/interop/test_api_v1_tools.py` |
| 4 | `/api/ai/v1/register` 返回一次性 key | 通过 | `tests/interop/test_api_v1_register.py` |
| 5 | `/api/ai/v1/tools` 返回工具数组 | 通过 | `test_tools_use_openai_function_schema` |
| 6 | `/api/ai/v1/execute` 鉴权、限流、执行工具 | 通过 | `tests/interop/test_api_v1_execute.py` |
| 7 | 全量 pytest + ruff + mypy | 部分通过 | pytest/mypy/ruff check 通过；全量 format 见第 3 节 |

## 3. 测试与质量门

```text
.venv\Scripts\python.exe -m pytest tests/interop -q -p no:cacheprovider --basetemp .pytest-tmp-p22
10 passed, 1 warning in 1.44s
```

```text
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-full2
288 passed, 4 deselected, 1 warning in 31.78s
```

```text
.venv\Scripts\python.exe -m ruff check .
warning: Encountered error: 拒绝访问。 (os error 5)
All checks passed!
```

```text
.venv\Scripts\python.exe -m ruff format --check .
error: Encountered error: 拒绝访问。 (os error 5)
Would reformat: src\multiscribe_agent\agents\pipelines\daily_digest.py
1 file would be reformatted, 235 files already formatted
```

```text
.venv\Scripts\python.exe -m mypy src
Success: no issues found in 135 source files
```

## 4. 任务完成情况

- T1-T2：`InteropKey` 和 `interop_keys` 表完成，hash 字段唯一。
- T3-T4：`SlidingWindowLimiter` 和 `InteropService` 使用 async `Database`，适配当前仓库架构。
- T5-T6：`ToolRegistry` 暴露 `list_sources`、`kb_search`、`list_publishers` 三个 OpenAI function tools。
- T7：`ServiceContext` 初始化 interop 组件，`app.py` 挂载 `/api/ai/v1`。

## 5. 风险与遗留

- `register` 默认白名单自动通过；生产环境若需审批，应由后续包接管理员鉴权。
- `/api/ai/v1/tools` 当前未强制鉴权，符合任务包工具发现口径，但生产暴露前建议确认安全策略。
- 手动 curl 未启动真实服务执行；等价 HTTP 验收由 FastAPI `TestClient` 覆盖。

## 6. 自评

我认为 P22 满足主要完成定义；全量 format 门仍受白名单外既有文件影响。
