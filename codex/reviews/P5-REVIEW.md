# Review: `P5-插件骨架`

**执行包**：`docs/phases/P5-插件骨架.md`
**完成日期**：2026-07-16
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件清单（创建/修改）

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/plugins/__init__.py` | 新增 | 插件基类、Registry、发现 API 公共导出 |
| `src/multiscribe_agent/plugins/base.py` | 新增 | Adapter/Publisher/Storage/Tool 四类 ABC |
| `src/multiscribe_agent/plugins/registry.py` | 新增 | 四类单例 Registry 与 Tool 双注册 |
| `src/multiscribe_agent/plugins/discovery.py` | 新增 | builtin/custom 包扫描和元数据注册 |
| `src/multiscribe_agent/plugins/builtin/__init__.py` | 新增 | 内置插件包 |
| `src/multiscribe_agent/plugins/builtin/tools/__init__.py` | 新增 | 内置工具导出 |
| `src/multiscribe_agent/plugins/builtin/tools/execute_command.py` | 新增 | 安全命令示例 Tool |
| `src/multiscribe_agent/plugins/builtin/adapters/__init__.py` | 新增 | P6 Adapter 落点 |
| `src/multiscribe_agent/plugins/builtin/publishers/__init__.py` | 新增 | P7/P8 Publisher 落点 |
| `src/multiscribe_agent/plugins/builtin/storages/__init__.py` | 新增 | 后续 Storage 落点 |
| `tests/plugins/conftest.py` | 新增 | 单例 Registry 测试隔离 |
| `tests/plugins/test_base.py` | 新增 | ABC 与 Adapter 容错测试 |
| `tests/plugins/test_registry.py` | 新增 | Registry、覆盖、Tool 双注册测试 |
| `tests/plugins/test_discovery.py` | 新增 | 临时包与真实 builtin 发现测试 |
| `tests/plugins/test_execute_command.py` | 新增 | 命令白黑名单、超时、截断测试 |
| `codex/reviews/P5-REVIEW.md` | 新增 | 本次强制 review 交付物 |

### 1.2 白名单合规性

- [x] 所有功能源码和测试均在 P5 白名单内。
- [x] 未修改 domain/models.py、agents/executor.py，也未实现 RSS/飞书/企微插件。
- [x] `codex/reviews/P5-REVIEW.md` 是 `EXEC_PROMPT.md` 强制交付物，沿用既有 review 目录。
- [x] 本包无新增依赖，`pyproject.toml`、`.pre-commit-config.yaml`、`uv.lock` 未变化。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | 四基类 + 四 Registry + 自动发现完整 | ✅ | `base.py:16,45,62,72`；`registry.py:59,71,83,95`；`discovery.py:27,34`。 |
| 2 | 发现带 metadata 的类并跳过基类/非插件 | ✅ | `test_scan_registers_metadata_classes_and_skips_others`：注册列表严格等于 1 个 TemporaryTool，base 模块和 PlainClass 均在 skipped；重复扫描后 metadata 数仍为 1。 |
| 3 | ExecuteCommandTool 白黑名单生效 | ✅ | `test_allowlisted_python_command_executes`、`test_blocked_and_chained_commands_are_rejected`、timeout/output 测试通过。 |
| 4 | ToolRegistry 类/实例双注册与调用 | ✅ | `test_tool_registry_dual_registration_and_call` 验证 register、register_tool、get_tool、call_tool、定义筛选及 P4 execute 适配。 |
| 5 | mypy strict + ruff + pytest 全绿 | ✅ | Ruff/format 通过；mypy `41 source files`；P5 `13 passed`；全量 `72 passed`。 |

## 3. 测试与质量门（原始输出）

项目依赖未变化。最终命令用 `uv run --no-sync` 执行已锁定环境；`-p no:cacheprovider` 仅规避受控 Windows pytest cache 权限，不跳过测试。

### 3.1 `uv run --no-sync ruff check .`

```text
All checks passed!
```

### 3.2 `uv run --no-sync ruff format --check .`

```text
61 files already formatted
```

### 3.3 `uv run --no-sync mypy src`

```text
Success: no issues found in 41 source files
```

### 3.4 `uv run --no-sync pytest tests/plugins -q -p no:cacheprovider`

```text
.............                                                            [100%]
13 passed in 2.48s
```

### 3.5 `uv run --no-sync pytest -q -p no:cacheprovider`

```text
........................................................................ [100%]
72 passed in 7.96s
```

### 3.6 `pre-commit run --all-files`

```text
ruff check...............................................................Passed
ruff format..............................................................Passed
mypy.....................................................................Passed
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...............................................................Passed
check toml...............................................................Passed
check for added large files..............................................Passed
```

## 4. 详细任务完成情况

- **T1 四类基类**：直接 import 规划层补齐的 `PluginMetadata`，四类均为 ABC；Adapter 模板方法在插件隔离边界记录错误类型并返回空列表，见 `plugins/base.py:16`。
- **T2 Registry**：Adapter/Publisher/Storage 使用 Python 3.12 泛型底座和各自模块级 singleton；Tool 分离 class discovery 与 initialized instance，并把实例映射为 `ToolDefinition`，见 `registry.py:59`。
- **T3 自动发现**：扫描 builtin/custom namespace，跳过含 base 和 `_test` 文件，只注册定义于本模块、metadata 类型与基类一致的 class；按 id 覆盖保证重复扫描幂等，见 `discovery.py:34`。
- **T4 ExecuteCommandTool**：首词规范化并应用 allow/block list；额外拒绝 shell 链式操作符，未知命令拒绝并提示审批；子进程具备 1..120 秒超时、20,000 字符 stdout/stderr 上限和 async cwd 校验，见 `execute_command.py:24`。
- **T5 测试**：13 项测试覆盖 ABC、容错、四类单例基础、Tool 双注册、临时/真实包发现、命令安全与进程边界；全量 72 项无回归。

## 5. 规范符合性自检

- [x] 公共类/函数有类型注解与 docstring；生产代码无新增裸 `Any`。
- [x] 外部 fetch、publish、upload、tool handler 与子进程均采用 async 接口。
- [x] cwd 文件系统检查通过 `asyncio.to_thread`，未在 async handler 阻塞事件循环。
- [x] Adapter 错误日志只含 adapter id 和异常类型，不含配置/密钥/原始数据。
- [x] ExecuteCommandTool 不记录命令内容；拒绝黑名单、未知命令和 shell 操作符。
- [x] plugins 只依赖 domain/core，不产生 domain 反向依赖。
- [x] 测试不访问网络；仅启动本机 Python 子进程验证命令行为。

## 6. 新增依赖

无。

## 7. 风险、遗留与取舍

- **风险**：`create_subprocess_shell` 是任务包指定接口，因此安全边界同时采用首词 allowlist 和 shell 操作符拒绝；仍不应把此 Tool 暴露给未授权用户。
- **取舍**：未知命令在 MVP 直接抛 `ToolExecutionError("command requires approval")`，未实现交互审批状态机。
- **取舍**：`ToolRegistry.get_all_tools()` 仅暴露已初始化实例；discovery 只注册类，bootstrap 注入依赖并 `register_tool()` 后才可被 Agent 调用。
- **兼容性**：Registry 额外提供 P4 Protocol 所需的 `get_definitions(tool_ids)` 与 `execute(tool_call)` 薄适配，不修改 P4 executor。
- **未做的事**：未创建 custom 目录、RSS/飞书/企微插件或自动实例化 bootstrap；均属于后续阶段。

## 8. BLOCKED 项

无。初次发现 P1 缺少插件契约后按流程停下；规划层提交 `0eebd1d` 补齐 `PluginMetadata`、`ConfigField`、`PluginType` 后才开始 P5 实现。

## 9. 对后续包的提示

- P6/P7/P8 插件类必须声明 domain `PluginMetadata`，discovery 会校验 metadata.type 与实际基类一致。
- Bootstrap 必须先 discovery class，再构造需要依赖的实例并调用 `register_tool()`；只有实例会出现在 Agent 工具定义中。
- P4 可直接把 `ToolRegistry.get_instance()` 作为其 registry Protocol 注入。

## 10. 自评

- 我认为本包**满足** `docs/phases/P5-插件骨架.md` 的完成定义：✅
