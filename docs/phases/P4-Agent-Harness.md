# P4 — Agent Harness（ReAct + 事件流 + HarnessContext）

> **状态**：未开始 · **依赖**：P1, P3 · **Harness Engineering 主战场之一**

## 目标

实现声明式 Agent 执行器：ReAct 多轮循环 + async 事件流 + **HarnessContext**（结构化上下文窗口管理）。这是体现 Harness Engineering 的核心模块。

## 前置依赖

P1（AgentDefinition/AIMessage/ToolCall），P3（AIProvider）。

## 可改范围（白名单）

- `src/multiscribe_agent/agents/__init__.py`
- `src/multiscribe_agent/agents/context.py`（HarnessContext — Harness 核心）
- `src/multiscribe_agent/agents/executor.py`（AgentExecutor，ReAct 循环）
- `src/multiscribe_agent/agents/events.py`（事件类型定义）
- `src/multiscribe_agent/agents/planner.py`（规划器 — Harness，MVP 基础版）
- `src/multiscribe_agent/agents/reflector.py`（反思器 — Harness/Loop 第一环，MVP 基础版）
- `src/multiscribe_agent/agents/prompt_service.py`（Jinja2 模板加载，分节 ## [Name]）
- `src/multiscribe_agent/resources/prompts/common.md`（移植通用 prompt）
- `src/multiscribe_agent/resources/prompts/digest.md`（每日摘要 prompt，P11 用，P4 先建文件）
- `pyproject.toml`（追加：`jinja2>=3.1`）
- `tests/agents/conftest.py`（fake provider + fake tools）
- `tests/agents/test_executor.py`
- `tests/agents/test_context.py`
- `tests/agents/test_planner_reflector.py`

## 禁止改动（黑名单）

- 不动 llm/ provider 实现。
- 不创建 plugins/（工具由 P5 提供；本包用 fake tools 测试）。
- 不创建 workflow 引擎（P10）。
- 不动 infra/db（如需 store，停下问）。

## 详细任务

### T1. `agents/events.py` — 事件类型

```python
@dataclass
class AgentEvent:
    type: Literal["round_start","content","tool_calls_delta","tool_calls",
                  "tool_start","tool_result","tool_error","final_content","error","usage"]
    data: dict[str, Any]
    trace_id: str
```
定义事件 schema 文档（每类事件的 data 字段）。

### T2. `agents/context.py` — HarnessContext（Harness 核心）

这是 Harness Engineering 的关键。负责**结构化管理 Agent 的上下文窗口**：
- 持有 `messages: list[AIMessage]`、`token_budget: int`（默认按模型，如 120000）、`system_prompt: str`。
- `add_user(msg)` / `add_assistant(msg)` / `add_tool_result(tool_call_id, name, content)`。
- **窗口滑动截断**：`trim_if_needed()` —— 估算消息 token 数（用 `tiktoken` 或字符数启发式），超预算时保留 system + 最近 N 轮 + 工具结果完整性，丢弃中间历史（保留首尾）。
- **工具结果压缩**：超长 tool_result 自动截断/摘要（超阈值如 8000 字符时尾部保留 + 截断标记）。
- **自动注入**：`inject_memory(summary)` / `inject_knowledge(snippets)` 方法，把检索结果以结构化前缀注入（P16/P17 后接；P4 先实现接口）。
- `build_messages() -> list[AIMessage]`：产出给 provider 的最终消息序列。
- `usage_summary -> TokenUsage`：累计本次 run 的 token。

### T3. `agents/prompt_service.py`

- Jinja2 环境，加载 `resources/prompts/*.md`。
- 模板内用 `## [SectionName]` 分节；`get_section(template_name, section_name) -> str`。
- `render(template_name, section_name, **vars) -> str`。
- MVP 提供 `common.md`（移植原 common.md 的通用指令）+ `digest.md`（每日摘要指令，P11 用）。

### T4. `agents/executor.py` — AgentExecutor（ReAct 循环）

```python
class AgentExecutor:
    def __init__(self, provider_factory, tool_registry, prompt_service, reflector=None): ...
    async def run(self, agent_def: AgentDefinition, user_input: str, *, tools_override=None) -> AIResponse:
        """非流式：收集全部事件，返回最终 AIResponse。"""
    def stream(self, agent_def, user_input, *, tools_override=None) -> AsyncIterator[AgentEvent]:
        """流式：async generator 产出事件。"""
```

核心循环（max_rounds，默认 5，可配）：
1. 用 HarnessContext 组装系统提示（skill prompt 占位 + system_prompt）+ 初始 user。
2. 每轮：`provider.stream(context.build_messages(), tools)` → yield content/tool_calls_delta 事件。
3. 有 tool_calls：yield tool_calls → 逐个 yield tool_start → 执行工具（从 tool_registry 取，异常 yield tool_error）→ yield tool_result → context.add_tool_result → 继续。
4. 无 tool_calls：yield final_content → break。
5. 每轮记录 usage（yield usage 事件）。
6. **Reflector 钩子**：循环结束后，若配置启用 reflector 且自评不达标，带反馈重跑一轮（最多 reflector_max_retries）。

工具执行：`tools_override` 提供 list[ToolDefinition] + 一个 `tool_executor` callable（P5 接 registry；P4 用 fake）。本地工具优先；非本地视为 MCP（P18 接，P4 占位抛 NotImplementedError）。

### T5. `agents/planner.py`（MVP 基础版）

- `class Planner`：`async def plan(self, task: str, provider) -> list[str]`。
- 用一个固定 prompt 让 LLM 把复杂任务拆成子步骤（返回 JSON 数组）。
- MVP：实现但不在主路径强制启用（agent config 可选 `enable_planning`）。主要价值是给 P11 流水线和后续 Loop 用。

### T6. `agents/reflector.py`（MVP 基础版 — Loop 第一环）

- `class Reflector`：`async def assess(self, task: str, output: str, provider) -> Reflection`。
- `Reflection`：`quality: Literal["pass","fail"], score: float, feedback: str, should_retry: bool`。
- 用固定 prompt 让 LLM 评分 + 给反馈。`should_retry = quality=="fail"`。
- 这是 Loop Engineering 的"评估"环节；P10/P11 的 Loop 节点会调用它。

### T7. 测试（fake provider + fake tools，不打真实网络）

- `tests/agents/conftest.py`：`FakeProvider`（可预设多轮响应序列，模拟 tool call → tool result → final）；`FakeTool`（实现 BaseTool 接口的测试桩）；`make_agent_def()` helper。
- `tests/agents/test_context.py`：
  - add/build messages 正确；trim_if_needed 超预算时保留首尾且工具结果完整；tool_result 压缩触发；token 估算单调。
- `tests/agents/test_executor.py`：
  - 无工具 round：1 轮 final_content。
  - 有工具：round1 tool_calls → tool_result → round2 final_content，事件序列正确。
  - max_rounds 达上限优雅终止（yield error 或带说明的 final）。
  - 工具异常 yield tool_error 不崩。
  - reflector 不达标触发重跑（fake provider 第 N 轮返回差质量，reflector 返回 fail）。
- `tests/agents/test_planner_reflector.py`：plan 返回步骤列表；reflector 评分结构正确。

## 验收条件

1. HarnessContext 实现窗口滑动截断 + 工具结果压缩 + token 预算（有单测证明截断生效）。
2. ReAct 循环事件流完整（round_start/content/tool_calls/tool_start/tool_result/final_content/usage/error），序列符合预期。
3. 工具异常不崩 executor。
4. Reflector 能评估并触发重试（Loop 闭环可观察）。
5. PromptService 正确分节加载。
6. 全部测试绿，零真实网络。
7. mypy strict 通过。

## 测试方式

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest tests/agents -q
```
原始输出贴 review。建议附一个事件序列的断言示例输出（证明多轮 tool calling 正确）。

## 完成定义

验收全满足；HarnessContext 有清晰的截断/压缩测试证据；事件流序列可验证。后续 P10 DAG 引擎会复用本 executor。
