# Review: P18-MCP服务器

**执行包**：`docs/phases/P18-MCP服务器.md`
**完成日期**：2026-07-19
**执行者**：Codex

## 1. 范围核对

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/mcp/**` | 新增 | 类型、认证、注册表、五工具、stdio/SSE server |
| `src/multiscribe_agent/api/routes/mcp.py` | 新增 | JWT REST 镜像 |
| `src/multiscribe_agent/app.py` | 修改 | 注册 MCP router |
| `src/multiscribe_agent/cli.py` | 修改 | `multiscribe-agent mcp` 子命令 |
| `src/multiscribe_agent/config.py` | 修改 | MCP key、host、port、transport 配置 |
| `pyproject.toml` / `uv.lock` | 修改 | 增加 `mcp>=1,<2`，锁定 1.28.1 |
| `.pre-commit-config.yaml` | 修改 | mypy hook 增加 MCP 依赖 |
| `tests/mcp/**` | 新增 | 10 项 auth、registry、tools、server/API 测试 |

上述文件都在 P18 白名单；未修改 P18 黑名单的 bootstrap、plugins/base、api deps/security、knowledge、publish history、LLM provider 或 executor。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | 五个工具注册 | ✅ | `test_server_builds_all_five_documented_tools` 固定验证五个名称 |
| 2 | stdio 服务器可用 | ✅ | 本地 dummy key/临时 DB smoke：`stdio_alive=True`；并验证 MCP 1.28.1 `Server`/`stdio_server` 导入 |
| 3 | SSE 服务器可用 | ✅ | 本地 dummy key/临时 DB smoke：`sse_alive=True`；并验证 `SseServerTransport.connect_sse` 签名 |
| 4 | MCP API key | ✅ | `test_mcp_key_requires_configuration`、`test_mcp_key_reads_environment_and_compares_in_constant_time` |
| 5 | JWT REST 镜像 | ✅ | `test_mcp_rest_api_requires_jwt_and_lists_and_calls_tools` 覆盖 401、list、call、404 |
| 6 | 至少 10 测试 | ✅ | `tests/mcp`: `10 passed` |
| 7 | 全量质量门绿 | ❌ | ruff/format/mypy 通过；全量 pytest 3 个 P16 失败 |
| 8 | 既有 193+ 无回归 | ❌ | 同上 |

## 3. 测试与质量门

```text
MCP SDK verification
mcp 1.28.1
server-import-ok
stdio_alive=True
sse_alive=True

.venv\Scripts\python.exe -m pytest tests/mcp -v -p no:cacheprovider
10 passed in 0.71s

ruff check .
All checks passed!

ruff format --check .
200 files already formatted

mypy src
Success: no issues found in 119 source files

pytest -q -p no:cacheprovider --basetemp .pytest-tmp-all
229 passed, 3 failed, 4 deselected in 25.64s
```

## 4. 详细任务完成情况

- **五工具**：RSS 触发、KB RRF/FTS 搜索、发布历史、采集源列表和发布端列表均由 `build_tool_registry()` 装配。
- **传输与认证**：stdio/SSE 共用注册表和 `_api_key` 常量时间验证；SDK 版本固定为 `mcp 1.28.1`。
- **REST/CLI**：`/api/mcp/tools` 与 call 镜像走 JWT；`mcp` CLI 支持 `stdio`、`sse`、host/port。
- **安全**：发布历史显式序列化，不使用 slots dataclass 的 `__dict__`；工具 schema 限制 RSS/KB/history limits。

## 5. 新增依赖

| 包 | 版本 | 用途 |
| :--- | :--- | :--- |
| `mcp` | `>=1,<2`，lock 为 `1.28.1` | 官方 stdio/SSE MCP server SDK |

## 6. 风险、遗留与取舍

- **阻塞风险**：全量 pytest 的 P16 既有 3 项失败，具体原因与 P17 Review 一致；不在 P18 白名单内，未修改。
- **取舍**：stdio/SSE smoke 只确认进程成功启动后立即终止；业务 handler 的完整交互由隔离注册表/API 测试覆盖，不向真实源发起请求。
- **未做**：没有添加持久化 MCP 配置 CRUD；任务包仅要求服务器和外部调用。

## 7. BLOCKED 项

- **阻塞点**：全量质量门 `pytest` 未绿，当前 `229 passed, 3 failed, 4 deselected`。
- **需要决策**：先以 P16 独立修复包处理可选 PDF/embedding 测试环境，再重跑 P18 全量门禁。

## 8. 自评

- 五工具、认证、CLI、SDK 导入和 REST 镜像已实现并专项通过；由于全量门禁失败，本包完成定义：❌
