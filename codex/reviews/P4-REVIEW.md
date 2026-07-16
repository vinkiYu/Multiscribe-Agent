# Review: `P4-Agent Harness`

**执行包**：`docs/phases/P4-Agent-Harness.md`
**完成日期**：2026-07-16
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件清单（创建/修改）

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/agents/__init__.py` | 新增 | Harness 公共导出 |
| `src/multiscribe_agent/agents/events.py` | 新增 | AgentEvent 类型与 data schema |
| `src/multiscribe_agent/agents/context.py` | 新增 | 上下文窗口、截断、工具压缩、注入与 usage |
| `src/multiscribe_agent/agents/prompt_service.py` | 新增 | Jinja Markdown 分节加载与渲染 |
| `src/multiscribe_agent/agents/executor.py` | 新增 | ReAct 多轮循环、工具执行、事件流和反思重试 |
| `src/multiscribe_agent/agents/planner.py` | 新增 | JSON 步骤规划器 |
| `src/multiscribe_agent/agents/reflector.py` | 新增 | Reflection 模型和质量评估器 |
| `src/multiscribe_agent/resources/prompts/common.md` | 新增 | 通用系统与反思反馈 prompt |
| `src/multiscribe_agent/resources/prompts/digest.md` | 新增 | P11 摘要筛选/评估 prompt |
| `tests/agents/conftest.py` | 新增 | FakeProvider、FakeTool 与 Agent fixture |
| `tests/agents/test_context.py` | 新增 | 上下文、截断、压缩、token 测试 |
| `tests/agents/test_executor.py` | 新增 | ReAct、事件、异常、反思重试测试 |
| `tests/agents/test_planner_reflector.py` | 新增 | PromptService、Planner、Reflector 测试 |
| `pyproject.toml` | 修改 | 新增 Jinja2 运行时依赖 |
| `.pre-commit-config.yaml` | 修改 | mypy 隔离环境同步 Jinja2 |
| `uv.lock` | 修改 | 锁定 Jinja2/MarkupSafe |
| `codex/reviews/P4-REVIEW.md` | 新增 | 本次强制 review 交付物 |

### 1.2 白名单合规性

- [x] 所有功能源码、prompt、测试和 `pyproject.toml` 均在 P4 白名单内。
- [x] 未修改 `llm/`、`plugins/`、workflow、infra/db 或 domain 模型。
- [x] `.pre-commit-config.yaml` 与 `uv.lock` 是总执行指令对新增运行时依赖的授权同步项。
- [x] `codex/reviews/P4-REVIEW.md` 是 `EXEC_PROMPT.md` 强制交付物，沿用 `codex/reviews/` 既有位置。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | HarnessContext 窗口截断、工具结果压缩、token 预算 | ✅ | `context.py:15,100`；`test_trim_preserves_first_recent_and_tool_integrity`、`test_tool_result_compression_keeps_tail_and_marker`、`test_token_estimate_is_monotonic_and_usage_accumulates` 通过。 |
| 2 | ReAct 事件流完整且序列正确 | ✅ | `executor.py:45,102`；`test_one_round_without_tools_emits_final_content` 与 `test_tool_call_runs_two_rounds_in_expected_sequence` 通过。 |
| 3 | 工具异常不崩 executor | ✅ | `test_tool_exception_emits_error_and_loop_continues` 验证 `tool_error` 后进入第二轮并产出 `final_content`。 |
| 4 | Reflector 评估并触发重试 | ✅ | `reflector.py:18,27`；`test_reflector_failure_triggers_visible_retry` 验证 fail 反馈注入、两次 `round_start` 和改善后的 final。 |
| 5 | PromptService 正确分节加载 | ✅ | `prompt_service.py:13`；`test_prompt_service_loads_sections_and_renders_variables` 验证分节、变量渲染和缺失 section 异常。 |
| 6 | 全部测试绿、零真实网络 | ✅ | P4 `13 passed in 0.30s`；全量 `59 passed in 4.50s`。FakeProvider/FakeTool 无网络 I/O。 |
| 7 | mypy strict 通过 | ✅ | `Success: no issues found in 31 source files`。 |

## 3. 测试与质量门（原始输出）

依赖已先执行 `uv lock` 与 `uv sync --all-extras`。最终命令使用 `--no-sync`，防止验收时重新解析已锁定环境；`-p no:cacheprovider` 仅规避受控 Windows pytest cache 权限，不跳过测试。

### 3.1 `uv run --no-sync ruff check .`

```text
All checks passed!
```

### 3.2 `uv run --no-sync ruff format --check .`

```text
46 files already formatted
```

### 3.3 `uv run --no-sync mypy src`

```text
Success: no issues found in 31 source files
```

### 3.4 `uv run --no-sync pytest tests/agents -q -p no:cacheprovider`

```text
.............                                                            [100%]
13 passed in 0.30s
```

### 3.5 `uv run --no-sync pytest -q -p no:cacheprovider`

```text
...........................................................              [100%]
59 passed in 4.50s
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

### 3.7 两轮工具事件序列断言

`test_tool_call_runs_two_rounds_in_expected_sequence` 的确定序列：

```text
round_start
tool_calls_delta
usage
tool_calls
tool_start
tool_result
round_start
content
usage
final_content
```

## 4. 详细任务完成情况

- **T1 事件类型**：`AgentEvent` 使用 frozen/slots dataclass，定义 10 类事件及每类 data 字段，见 `src/multiscribe_agent/agents/events.py:23`。
- **T2 HarnessContext**：系统 prompt 与 memory/knowledge 结构化拼装；按约四字符估算 token；截断时保留首条和最近原子组，assistant tool_calls 与相邻 tool results 不拆分；超长工具结果保留尾部和原长度标记，见 `context.py:15`。
- **T3 PromptService**：`FileSystemLoader` 加载 Markdown，正则解析 `## [Section]`，StrictUndefined 渲染；Prompt 是纯文本，明确关闭 HTML autoescape，见 `prompt_service.py:13`。
- **T4 AgentExecutor**：构造时配置 `max_rounds`、reflection 重试和 token budget；`tools_override` 为工具定义列表与 async callable，默认 registry 使用最小 Protocol；每轮流式产事件、追加 assistant/tool 上下文、累计 usage，见 `executor.py:45`。
- **T5 Planner**：固定 system instruction 要求纯 JSON 数组，校验非空字符串步骤，见 `planner.py:14`。
- **T6 Reflector**：校验 pass/fail、0..1 score 和 feedback，并由 quality 唯一派生 `should_retry`，见 `reflector.py:18`。
- **T7 测试**：13 项 P4 测试覆盖全部验收路径；全量 59 项证明 P0-P3 无回归。

## 5. 规范符合性自检

- [x] 公共类/函数具备完整类型注解和 docstring；新增生产代码无裸 `Any`。
- [x] Provider、工具和反思调用均为 async；无同步网络或数据库 I/O。
- [x] 工具插件边界捕获异常并记录脱敏的工具名、trace_id 和异常类型，不记录 arguments/结果隐私。
- [x] `trace_id` 在单次 run 的全部事件中稳定一致。
- [x] domain/llm/infra 等前置模块未修改，依赖方向为 agents -> domain/llm。
- [x] 测试仅用 FakeProvider/FakeTool，无真实模型或外部网络。

## 6. 新增依赖

| 包 | 版本约束 | 用途 |
| :--- | :--- | :--- |
| `jinja2` | `>=3.1` | 分节 Markdown prompt 的严格变量渲染 |

`uv.lock` 解析版本：`jinja2==3.1.6`、`markupsafe==3.0.3`。

## 7. 风险、遗留与取舍

- **风险**：token 估算是四字符启发式，不是模型 tokenizer 精确值；P4 明确允许该方案，预算设计偏保守。
- **取舍**：工具失败会作为 `[tool error]` ToolMessage 回填上下文，使下一轮模型可恢复；插件边界使用顶层异常隔离但不静默吞错，同时发出 `tool_error` 并记录异常类型。
- **遗留**：非本地/未注册工具显式产生 `NotImplementedError` 路径并转 `tool_error`；MCP 实际执行留 P18。
- **未做的事**：未创建 P5 plugins、P10 workflow、infra store，也未修改 AgentDefinition 增加规划字段；Planner 保持可选且不强制接入主路径。

## 8. BLOCKED 项

无。初版任务包的 executor 白名单路径冲突已由规划提交 `f290492` 修正后才开始实现。

## 9. 对后续包的提示

- P5 registry 可实现 `ToolRegistry.get_definitions(tool_ids)` 与 `execute(tool_call)`，无需让 P4 反向依赖 plugins。
- P10/P11 可复用 `AgentExecutor.stream()` 的稳定 trace_id 与完整事件序列；Planner/Reflector 均只依赖 `AIProvider`。
- P16/P17 可直接调用 `HarnessContext.inject_knowledge()` / `inject_memory()`，无需改变消息契约。

## 10. 自评

- 我认为本包**满足** `docs/phases/P4-Agent-Harness.md` 的完成定义：✅
