# Review: `P3-LLM Provider 抽象`

**执行包**：`docs/phases/P3-LLM-Provider.md`
**完成日期**：2026-07-16
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件清单（创建/修改）

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/llm/__init__.py` | 新增 | LLM 公共导出 |
| `src/multiscribe_agent/llm/provider.py` | 新增 | Protocol、工厂、消息/工具归一化、流式工具调用合并 |
| `src/multiscribe_agent/llm/providers/__init__.py` | 新增 | Provider 导出 |
| `src/multiscribe_agent/llm/providers/openai.py` | 新增 | OpenAI LangChain Provider |
| `src/multiscribe_agent/llm/providers/anthropic.py` | 新增 | Anthropic LangChain Provider |
| `src/multiscribe_agent/llm/providers/google.py` | 新增 | P18 前的显式保留模块 |
| `src/multiscribe_agent/llm/providers/ollama.py` | 新增 | P18 前的显式保留模块 |
| `tests/llm/conftest.py` | 新增 | 全 mock ChatModel 与配置 fixture |
| `tests/llm/test_provider.py` | 新增 | 归一化与工厂单测 |
| `tests/llm/test_providers_unit.py` | 新增 | OpenAI/Anthropic generate/stream mock 单测 |
| `pyproject.toml` | 修改 | LangChain 运行时依赖与供应商模块 mypy 跳过规则 |
| `.pre-commit-config.yaml` | 修改 | mypy 隔离环境的 LangChain、structlog、langsmith 兼容依赖 |
| `uv.lock` | 修改 | 锁定新增依赖 |
| `codex/reviews/P3-REVIEW.md` | 新增 | 本次必交 review |

### 1.2 白名单合规性

- [x] 所有源码与测试文件均在 P3 白名单内。
- [x] 未修改 domain/、Agent ReAct 或 agents/ 目录等黑名单内容。
- [x] `pyproject.toml`、`.pre-commit-config.yaml` 和 `uv.lock` 均为 P3 新增运行时依赖及总执行指令授权的同步改动。
- [x] `codex/reviews/P3-REVIEW.md` 是 `EXEC_PROMPT.md` 强制要求的交付物，依照 P0/P1/P2 既有约定存放在 `codex/reviews/`；它不属于 P3 的源码或功能实现范围。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `AIProvider` Protocol + 工厂 + OpenAI/Anthropic Provider 完成 | ✅ | `provider.py:30,182`；`openai.py:27`；`anthropic.py:25`；工厂分发单测 `test_create_provider_dispatches_*` 通过。 |
| 2 | 归一化处理纯文本、tool_calls、image_url、usage | ✅ | `provider.py:53,95,115`；`test_from_lc_message_preserves_image_tool_calls_and_usage` 通过。 |
| 3 | 流式 tool_calls 多 chunk 合并正确 | ✅ | `provider.py:153`；`test_openai_stream_merges_tool_call_argument_chunks` 通过。 |
| 4 | 未知 type 与缺 key 抛 `ProviderError` | ✅ | `provider.py:182`；`test_create_provider_rejects_unknown_type` 与 `test_provider_requires_api_key` 通过。 |
| 5 | 全部测试绿，零真实网络调用 | ✅ | `uv run --no-sync pytest -q -p no:cacheprovider` 输出 `46 passed in 2.53s`；15 个 P3 测试以 fake ChatModel/mock patch 执行。 |
| 6 | Google/Ollama 未实现时明确记录 | ✅ | 工厂对两者抛 `NotImplementedError(... deferred to P18)`，覆盖 `test_create_provider_marks_optional_providers_as_deferred`；风险见第 7 节。 |

## 3. 测试与质量门（原始输出）

同步已锁定环境后，以 `uv run --no-sync` 执行，避免验收过程中重新解析已经提交的锁文件；命令仍使用任务要求的 uv 运行时。

### 3.1 `uv run --no-sync ruff check .`

```text
All checks passed!
```

### 3.2 `uv run --no-sync ruff format --check .`

```text
35 files already formatted
```

### 3.3 `uv run --no-sync mypy src`

```text
Success: no issues found in 24 source files
```

### 3.4 `uv run --no-sync pytest -q -p no:cacheprovider`

```text
..............................................                           [100%]
46 passed in 2.53s
```

`-p no:cacheprovider` 仅用于规避 Windows 默认 pytest cache 目录的权限警告；测试收集、执行和断言均未跳过。`TEMP/TMP` 指向项目内临时目录，避免受控环境拒绝写入默认系统临时目录。

### 3.5 `pre-commit run --all-files`

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

### 3.6 额外运行时绑定验证

```text
RunnableBinding
```

该零网络构造检查验证 `ChatAnthropic.bind_tools()` 可接受内部适配后的 `parameters` 形状，避免此前发现的 `schema` 形状 `KeyError`。

## 4. 详细任务完成情况

- **T1 `llm/provider.py`**：实现 `AIProvider` Protocol、模型解析顺序（显式 model -> `config.models[0]` -> `ProviderError`）、温度默认值 0.7、四种角色消息转换、响应 usage/tool-call/image 内容归一化，以及按 id/name 合并流式调用，见 `src/multiscribe_agent/llm/provider.py:30`、`:53`、`:95`、`:153`、`:182`。
- **T2 OpenAIProvider**：使用 `ChatOpenAI`、可选 `httpx.AsyncClient` 代理、60 秒超时、`ProviderError` 归一化和无网络 `list_models`，见 `src/multiscribe_agent/llm/providers/openai.py:27`。
- **T3 AnthropicProvider**：使用 `ChatAnthropic`、SDK 支持的 `anthropic_proxy`、系统消息归一化、60 秒超时和同样的流式合并，见 `src/multiscribe_agent/llm/providers/anthropic.py:25`。公共 `schema` 契约在绑定前转换成 LangChain 实际需要的 `parameters`，见 `provider.py:130`。
- **T4 Google/Ollama**：保留模块并在工厂显式抛 `NotImplementedError`，避免静默错误；实现延期到 P18。
- **T5 测试**：15 个 P3 单元测试覆盖消息、usage、图片、工具、工厂、缺 key、OpenAI/Anthropic mock generate/stream；无测试访问真实模型 API。

## 5. 规范符合性自检

- [x] 新增公共类/函数有类型注解与 docstring；无裸 `Any`。
- [x] LLM I/O 为 async；`generate` 和 `stream` 分别使用 `asyncio.wait_for` 与 `asyncio.timeout`。
- [x] OpenAI 代理使用 `httpx.AsyncClient`；Anthropic 使用其 SDK 暴露的 `anthropic_proxy` 参数。
- [x] 外部 I/O 超时或 HTTP/OS 错误转换为 `ProviderError`，并以 structlog 记录不含密钥的上下文。
- [x] 未记录或硬编码任何 key/token；测试 key 为无效占位符。
- [x] domain 未被修改，分层依赖方向保持正确。
- [x] 所有测试使用 fake/mocking；未执行 e2e 网络调用。

## 6. 新增依赖

| 包 | 版本约束 | 用途 |
| :--- | :--- | :--- |
| `langchain` | `>=0.3,<1` | Provider 统一消息和 chat model 抽象 |
| `langchain-openai` | `>=0.2,<1` | OpenAI Chat Provider |
| `langchain-anthropic` | `>=0.2,<1` | Anthropic Chat Provider |

## 7. 风险、遗留与取舍

- **风险**：Google/Ollama 尚未实现；工厂会明确抛 `NotImplementedError`，应在 P18 补齐。
- **取舍**：`normalize_tools` 保持任务包指定的 `{name, description, schema}` 公共形状；Provider 在调用 LangChain 前转换为 SDK 所需的 `parameters`，已做零网络真实构造验证。
- **兼容性**：LangChain 1.x 的 transitive SDK 类型定义会导致 pre-commit 所用 mypy 1.16.1 内部错误，因此依赖约束为兼容的 0.x；mypy 对供应商实现设置 `follow_imports = "skip"`，项目源码仍严格检查。
- **未做的事**：未实现 Agent ReAct、Google/Ollama 实际 Provider、真实 API e2e；均不属于 P3 必做范围。

## 8. BLOCKED 项

无。P3 之前的 `ProviderConfig.models` 契约缺口已由规划层提交 `abe3d01` 解决，本次未修改 P1/domain 文件。

## 9. 对后续包的提示

- P4 应从 `create_provider(config, model=agent.model, temperature=agent.temperature, proxy=...)` 构造 Provider，之后只调用 `generate/stream`，不再传 model。
- P4 的工具执行循环可直接消费流式 `AIResponse.tool_calls`；每个后续 chunk 都带截至当前的累计 tool-call 参数。
- P18 实现 Google/Ollama 时应沿用同一固定模型和 `AIResponse` 归一化契约。

## 10. 自评

- 我认为本包**满足** `docs/phases/P3-LLM-Provider.md` 的完成定义：✅
