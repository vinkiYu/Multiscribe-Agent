# P3 — LLM Provider 抽象层

> **状态**：未开始 · **依赖**：P1（models/config）。可与 P2 并行，但建议 P2 先行。

## 目标

实现多模型 Provider 抽象：统一 OpenAI/Anthropic（MVP 必需，Google/Ollama 后置或可选）的 generate/stream/list_models，统一 tool calling 与消息归一化。这是 Agent Harness 的依赖底座。

## 前置依赖

P1（AIMessage/AIResponse/ToolCall/ProviderConfig/ToolDefinition）。

## 可改范围（白名单）

- `src/multiscribe_agent/llm/__init__.py`
- `src/multiscribe_agent/llm/provider.py`（Protocol + 工厂 + 消息归一化）
- `src/multiscribe_agent/llm/providers/__init__.py`
- `src/multiscribe_agent/llm/providers/openai.py`
- `src/multiscribe_agent/llm/providers/anthropic.py`
- `src/multiscribe_agent/llm/providers/google.py`（可选实现，无 key 时 graceful skip）
- `src/multiscribe_agent/llm/providers/ollama.py`（可选实现）
- `pyproject.toml`（追加：`langchain>=0.3`，`langchain-openai>=0.2`，`langchain-anthropic>=0.2`；可选 `langchain-google-genai`，`langchain-ollama`）
- `tests/llm/conftest.py`（fake provider + LC mock）
- `tests/llm/test_provider.py`
- `tests/llm/test_providers_unit.py`（用 fake LC chat model，不打真实网络）

## 禁止改动（黑名单）

- 不动 domain/ 模型（如发现缺字段，停下问）。
- 不实现 Agent ReAct 循环（那是 P4）。
- 不创建 agents/ 目录。
- 不在测试里打真实 OpenAI/Anthropic 网络（用 mock chat model）。

## 详细任务

### T1. `llm/provider.py`

- `class AIProvider(Protocol)`：
  - `async def generate(self, messages: list[AIMessage], tools: list[ToolDefinition] | None = None, system_instruction: str | None = None) -> AIResponse`
  - `def stream(self, messages, tools=None, system_instruction=None) -> AsyncIterator[AIResponse]`（async generator）
  - `async def list_models(self) -> list[str]`
- 消息归一化（模块级纯函数，可单测）：
  - `to_lc_messages(messages: list[AIMessage], system_instruction: str | None) -> list[BaseMessage]`：转 LangChain HumanMessage/AIMessage/SystemMessage/ToolMessage；tool_calls.arguments 映射。
  - `from_lc_message(msg: BaseMessage) -> AIResponse`：提取 content（含 list content 如 image_url）、tool_calls、usage（从 usage_metadata/response_metadata 归一化）。
- `normalize_tools(tools: list[ToolDefinition]) -> list[dict]`：转 LC bindTools 格式 `{name, description, schema=parameters}`。
- 工厂签名（**决策者 2026-07-16 钉定，消除模型来源歧义**）：
  ```python
  def create_provider(
      config: ProviderConfig,
      *,
      model: str | None = None,        # 来自 AgentDefinition.model
      temperature: float | None = None, # 来自 AgentDefinition.temperature
      proxy: str | None = None,
  ) -> AIProvider
  ```
  - 模型解析顺序：`model` 参数 → 兜底 `config.models[0]`（端点首个可用模型）→ 仍无则抛 `ProviderError("no model configured for provider {id}")`。
  - `temperature` 参数 → 兜底 `0.7`。
  - `AIProvider` Protocol 的 `generate/stream` **不**接收 model 参数（model 在构造时固定），保持接口简洁。

### T2. `llm/providers/openai.py` — OpenAIProvider

- 构造接收 `config: ProviderConfig, model: str, temperature: float, proxy: str | None`（由工厂解析后传入，**永远是确定值**）。
- 内部建 `ChatOpenAI(model=model, api_key=config.api_key, temperature=temperature, base_url=config.base_url, http_client=httpx.AsyncClient(proxy=proxy) if proxy else None)`。
- `generate`：`llm.bind_tools(normalize_tools(tools))` → `await ainvoke(to_lc_messages(...))` → `from_lc_message`。
- `stream`：`astream` → 逐 chunk `from_lc_message` yield；合并流式 tool_calls（按 id/name 去重，arguments 字符串拼接）。
- `list_models`：直接返回 `config.models`（不再打网络 `client.models.list()`，因为端点已声明支持清单；若需动态拉取留 e2e）。
- 超时与重试：用 LangChain 自带 + 包一层 `asyncio.wait_for`。

### T3. `llm/providers/anthropic.py` — AnthropicProvider

- 同结构，基于 `ChatAnthropic`。
- 注意：system_instruction 走 Anthropic 的 system 参数（LC 已处理，但归一化时确保不被当作普通 message）。

### T4. Google / Ollama（可选）

- 同结构。无 API key 时工厂仍能构造，但 `generate` 抛 `ProviderError("no api key configured")`，不崩启动。
- 若实现成本高，P3 可只做 OpenAI+Anthropic，Google/Ollama 在 `create_provider` 里抛 `NotImplementedError` 并注释「P18 后补」——**但必须在 review 里明确说明取舍**。

### T5. 测试（全 mock，不打真实网络）

- `tests/llm/conftest.py`：`FakeChatModel`（继承 BaseChatModel，可预设返回的 message 列表 + usage），用它替代真实 API；或用 `unittest.mock.AsyncMock` patch LC 的 ainvoke/astream。
- `tests/llm/test_provider.py`：
  - `to_lc_messages`/`from_lc_message`/`normalize_tools` 纯函数单测（含 image_url、tool_calls、usage 归一化）。
  - 工厂分发正确（各 type 对应 Provider；未知 type 抛错）。
- `tests/llm/test_providers_unit.py`：
  - OpenAIProvider.generate（mock ainvoke）返回正确 AIResponse，含 tool_calls。
  - OpenAIProvider.stream（mock astream）产出多个 chunk，最终 tool_calls 合并正确。
  - AnthropicProvider 同上。
  - 缺 key 时抛 ProviderError 不崩。
  - 标记真实调用测试为 `@pytest.mark.e2e`，默认跳过。

## 验收条件

1. `AIProvider` Protocol + 工厂 + 两个 Provider（OpenAI/Anthropic 必需）实现完成。
2. 消息归一化函数正确处理：纯文本、tool_calls、image_url、usage（单测覆盖）。
3. 流式 tool_calls 合并正确（多 chunk 拼接成完整 ToolCall）。
4. 工厂对未知 type 抛 `ProviderError`；缺 key 抛 `ProviderError` 不崩启动。
5. 全部测试绿，且**零真实网络调用**（CI 安全）。
6. Google/Ollama 如未实现，review 明确说明并记入风险。

## 测试方式

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest tests/llm -q
```
原始输出贴 review。可选验证真实调用（手动，不计入 CI）：
```bash
uv run pytest tests/llm -q -m e2e  # 仅在配了真实 key 时跑
```

## 完成定义

验收全满足；归一化函数有详尽单测；e2e 测试正确标记默认跳过。
