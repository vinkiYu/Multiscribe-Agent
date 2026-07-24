# Review: `P32-上下文管理模块设计债清理`

**执行包**：`docs/phases/P32-上下文管理模块设计债清理.md`
**完成日期**：2026-07-24
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件清单（创建/修改）

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/agents/token_counter.py` | 修改 | 按 Provider/配置 ID 分派计数器，新增 Claude 的 CJK-aware 估算器。 |
| `src/multiscribe_agent/agents/artifacts.py` | 修改 | 增加只含元数据的 artifact 列举，以及当前 Agent task 的 store 解析。 |
| `src/multiscribe_agent/plugins/builtin/tools/read_artifact.py` | 新增 | 按引用分页读取压缩前工具结果。 |
| `src/multiscribe_agent/plugins/builtin/tools/__init__.py` | 修改 | 导出 `ReadArtifactTool`。 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 将 `ReadArtifactTool` 注册为运行时工具实例。 |
| `src/multiscribe_agent/agents/context_provider.py` | 修改 | Memory/Knowledge 降级分支补充脱敏结构化 warning 日志。 |
| `src/multiscribe_agent/agents/checkpoint.py` | 修改 | 删除从未写入的 `failed_attempts`、`next_actions`。 |
| `src/multiscribe_agent/agents/context.py` | 修改 | 仅增加 `id(message)` 生命周期约束注释。 |
| `tests/agents/test_token_counter_accuracy.py` | 修改 | Provider 分派和 Claude 混合语言估算回归测试。 |
| `tests/plugins/test_read_artifact_tool.py` | 新增 | Artifact 读回、分页、缺失引用测试。 |
| `tests/agents/test_context_provider.py` | 新增 | Memory 降级日志与降级结果测试。 |
| `tests/agents/test_context_optimization.py` | 修改 | Checkpoint 死字段不存在的回归断言。 |
| `codex/reviews/P32-REVIEW.md` | 新增 | 本阶段自检与质量证据。 |

### 1.2 白名单合规性

- [x] 业务代码和测试文件均在 P32 白名单内。
- [x] `executor.py`、`run_budget.py`、Provider 实现、workflow、API、frontend 和 docs 未修改。
- [x] `codex/reviews/P32-REVIEW.md` 为执行 Prompt 要求的交付文档；`codex/` 虽被 `.gitignore` 忽略，提交时将仅对此文件显式 force-add。

工作区原有且未触碰的变更：`docs/phases/README.md`、`src.zip`。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `resolve_token_counter("anthropic", "claude-sonnet-4-5")` 返回 `AnthropicTokenCounter` | ✅ | `test_resolve_token_counter_dispatches_by_provider_type_or_configured_id` 通过；实现见 `agents/token_counter.py:83,188`。 |
| 2 | `resolve_token_counter("openai", "gpt-4o")` 返回 `TiktokenCounter` | ✅ | `test_resolve_token_counter_prefers_tiktoken` 通过。 |
| 3 | `resolve_token_counter("google", "gemini-2.0-flash")` 返回 `ConservativeTokenCounter` | ✅ | `test_resolve_token_counter_dispatches_by_provider_type_or_configured_id` 通过。 |
| 4 | Claude 混合中英文估算与 tiktoken 参考差异小于 30% | ✅ | `test_anthropic_mixed_language_estimate_stays_close_to_tiktoken_reference` 通过；采用 CJK 1.8 chars/token 与其他字符 4.0 chars/token 的保守加权估算。 |
| 5 | 可通过 artifact 引用读回内容 | ✅ | 当前 `BaseTool` 契约为 `handler()` 而非任务包示例的旧 `invoke()`；`test_read_artifact_returns_content_from_injected_store` 通过。 |
| 6 | 不存在 artifact 引用返回错误而非崩溃 | ✅ | `test_read_artifact_returns_non_fatal_error_for_missing_reference` 通过。 |
| 7 | Memory 异常产生 `context_provider_memory_degraded` 日志 | ✅ | `test_memory_failure_is_logged_and_keeps_retrieval_degraded` 通过，断言事件名、截断 query、异常类型和降级 reason。 |
| 8 | `ConversationCheckpoint` 不再含两个死字段 | ✅ | `test_checkpoint_retains_goal_decision_and_tool_evidence` 断言两个属性均不存在。 |
| 9 | `_message_priorities` 定义处有架构约束注释 | ✅ | `agents/context.py:86` 明确其仅对进程内消息对象有效，并规定 checkpoint/resume 前必须改用稳定 sequence/UUID。 |
| 10 | 全量 pytest、ruff、mypy 通过 | ✅ | 第 3 节完整原始输出。 |

## 3. 测试与质量门（原始输出）

### 3.1 P32 定向测试（按 tests/agents 与 tests/plugins 分域执行）

```text
tests/agents/test_token_counter_accuracy.py ... 6 passed
tests/agents/test_context_provider.py ... 1 passed
tests/agents/test_context_optimization.py ... 6 passed
============================= 13 passed in 0.62s =============================

tests/plugins/test_read_artifact_tool.py ... 3 passed
============================== 3 passed in 0.21s ==============================
```

说明：将 `tests/agents` 与 `tests/plugins` 的文件放在同一条 pytest 命令会触发现存的两个同名 `conftest.py` 顶层导入歧义（`test_context_optimization.py` 的既有 `from conftest import ...` 指向 plugins conftest）。未为该命令路径问题修改非 P32 范围的测试布局，按测试域分别执行后均通过。

### 3.2 `uv run ruff check .`

```text
All checks passed!
```

### 3.3 `uv run ruff format --check .`

```text
285 files already formatted
```

### 3.4 `uv run mypy src`

```text
Success: no issues found in 154 source files
```

### 3.5 `uv run pytest -q`

```text
........................................................................ [ 18%]
........................................................................ [ 36%]
........................................................................ [ 55%]
........................................................................ [ 73%]
........................................................................ [ 91%]
................................                                         [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  F:\software\Multiscribe\MultiscribeAgent-main\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

392 passed, 4 deselected, 1 warning in 34.16s
```

## 4. 详细任务完成情况

- **T1 Provider-aware token counter**：`resolve_token_counter()` 不再丢弃 provider，支持 `default-openai`、`default-anthropic` 这类配置 ID；OpenAI 保留 tiktoken，Anthropic 使用明确标注 degraded reason 的 CJK-aware 估算，Google/Ollama/未知端点回退保守计数。
- **T2 Artifact 读取闭环**：`InMemoryArtifactStore` 提供不含正文的 `list_artifacts()`；`ReadArtifactTool` 提供 `artifact_ref`、`offset`、`limit` 分页读取。因 P32 禁止修改执行器，store 通过 task-local `ContextVar` 在 Executor 创建后由同一 Agent run 的工具解析，避免跨并发运行串读。
- **T3 ContextProvider 可观测性**：Memory 和 Knowledge 的可恢复失败均记录 `structlog.warning`，仅写 query 前 80 字和异常文本前 200 字，不写完整检索内容或凭据。
- **T4 Checkpoint 清理**：移除未被生产路径填充或渲染的两个字段，保留现有目标、约束、结论、动作、证据和待办输出。
- **T5 生命周期约束显式化**：不在当前无持久化调用方的情况下重构优先级索引，只将迁移条件写在索引定义处，防止未来 checkpoint/resume 误用对象内存地址。

## 5. 规范符合性自检

- [x] 全量类型注解，无新增裸 `Any`。
- [x] 新工具只做内存读取，无阻塞 I/O；`handler()` 为 async。
- [x] 降级异常有 structlog warning，日志字段有长度边界。
- [x] 未记录 artifact 正文、Prompt、Memory 或凭据。
- [x] 无新增运行时依赖、无网络测试。
- [x] 分层依赖未反向：Tool 依赖 agents 的 ArtifactStore，未影响 domain 层。

## 6. 新增依赖

无。

## 7. 风险、遗留与取舍

- **风险**：ArtifactStore 仍为内存、单进程、带 TTL 的临时存储；进程重启后 artifact 引用必然失效。这是 P32 明确不扩展到持久化的边界。
- **取舍**：P32 禁止改动 `executor.py`，所以采用 `ContextVar` 使注册的工具获取同一个运行 task 中创建的 store。并发 Agent task 相互隔离；在同一 async task 的 Agent run 结束后，最后一次 store 引用会保留到下一次 store 创建，运行时工具仅在 Agent run 内调用，后续若开放脱离 Agent 的直接工具调用，应加显式绑定/清理生命周期。
- **遗留**：Google/Gemini 没有可用的官方 Python tokenizer，继续使用 CJK-aware 保守回退。
- **未做的事**：未重构 `id(message)` 为稳定 ID，未修改黑名单执行器、预算、Provider、workflow、API 文件，未做自动模型切换或 artifact 持久化。

## 8. BLOCKED 项

无。

## 9. 对后续包的提示

- 任何需要恢复历史 tool-result 正文的 Agent，应在 `AgentDefinition.tool_ids` 显式加入 `read_artifact`；该工具默认注册但不会自动暴露给所有 Agent。
- 若后续实现跨进程 checkpoint/resume，应将 `_message_priorities` 迁移到稳定 message sequence/UUID，并同时定义 Artifact 的持久化策略。

## 10. 自评

- 我认为本包**满足** `P32-上下文管理模块设计债清理.md` 的完成定义：✅
