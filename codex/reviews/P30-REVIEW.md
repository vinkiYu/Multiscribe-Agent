# Review: P30-上下文窗口生产链路修复

**执行包**：`docs/phases/P30-上下文窗口生产链路修复.md`  
**完成日期**：2026-07-24  
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件清单

| 文件 | 操作 | 用途 |
| :--- | :--- | :--- |
| `pyproject.toml` | 修改 | 新增 `tiktoken>=0.7` 直接运行时依赖 |
| `.pre-commit-config.yaml` | 修改 | 将 tiktoken 加入 mypy hook 依赖 |
| `uv.lock` | 修改 | 同步项目版本 1.1.2、tiktoken 和完整依赖锁 |
| `.env.example` | 修改 | 增加模型窗口/输出 Token JSON 配置示例 |
| `src/multiscribe_agent/agents/token_counter.py` | 修改 | tiktoken 精确计数和 CJK fallback |
| `src/multiscribe_agent/agents/context.py` | 修改 | 统一 TokenCounter、摘要/历史/输入裁剪 |
| `src/multiscribe_agent/agents/executor.py` | 修改 | 使用模型感知计数器、Skill 总量上限 |
| `src/multiscribe_agent/config.py` | 修改 | 默认模型窗口、输出预算和环境覆盖 |
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | 修改 | curate 输入投影与摘要截断 |
| `tests/agents/test_token_counter_accuracy.py` | 新增 | 精确计数和 fallback 验证 |
| `tests/test_config.py` | 修改 | 默认窗口、输出预算、环境覆盖验证 |
| `tests/agents/pipelines/test_daily_digest.py` | 修改 | 100 条候选投影和终止传播验证 |
| `tests/agents/test_executor.py` | 修改 | Skill 上限和 Reflection 回归验证 |
| `tests/agents/test_context.py` | 修改 | 经授权校准新 Token 计数下的历史裁剪预算 |
| `tests/agents/test_context_window_closure.py` | 修改 | 经授权将工具 Schema 调整为精确超窗样本 |
| `codex/reviews/P30-REVIEW.md` | 新增 | 本阶段 Review |

### 1.2 白名单合规性

- P30 原始白名单内的 11 个源码/测试文件均按要求修改。
- `tests/agents/test_context.py`、`tests/agents/test_context_window_closure.py` 由决策者明确授权加入白名单，用于修订过期断言。
- `pyproject.toml`、`.pre-commit-config.yaml`、`uv.lock` 属于全局依赖同步授权；Review 文件由 P30 完成定义明确要求生成。
- 未修改 P30 黑名单中的 Provider 实现、Reflector、Workflow、API、RunBudget、Prompt 模板、frontend。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | tiktoken 可用时中文 Token 误差 < 5% | ✅ | `tests/agents/test_token_counter_accuracy.py::test_tiktoken_chinese_estimation_matches_model_encoding`；实测 exact=20，与 `encoding_for_model("gpt-4o")` 一致 |
| 2 | tiktoken 不可用时 CJK fallback 误差 < 20% | ✅ | `test_fallback_chinese_estimation_is_within_twenty_percent`；实测 fallback=22、误差 10.0% |
| 3 | gpt-4o 窗口为 128000 | ✅ | `tests/test_config.py::test_default_providers_have_known_model_windows_and_output_limits` |
| 4 | claude-sonnet-4-5 窗口为 200000 | ✅ | 同上测试 |
| 5 | PROVIDER_CONTEXT_WINDOWS 可覆盖模型窗口 | ✅ | `test_environment_overrides_provider_model_limits`、`test_environment_overrides_custom_configured_model` |
| 6 | curate 不传 description 全文/metadata/author/status | ✅ | `test_curate_projection_excludes_full_content_and_bounds_one_hundred_candidates`；投影字段严格为 id/title/summary/url/source/category |
| 7 | 100 条候选 prompt < 旧实现 30% | ✅ | 同上测试；独立实测旧 321680 字符、新 60880 字符，比例 18.93% |
| 8 | 5 个 Skill 注入总字符数 ≤ 4000 | ✅ | `tests/agents/test_executor.py::test_skill_prompt_total_chars_are_capped` |
| 9 | 全量 pytest、ruff、mypy 通过 | ✅ | 见第 3 节；`381 passed, 4 deselected` |

## 3. 测试与质量门

### 3.1 `uv run ruff check .`（等价本地命令）

```text
All checks passed!
```

### 3.2 `uv run ruff format --check .`

```text
281 files already formatted
```

### 3.3 `uv run mypy src`

```text
Success: no issues found in 153 source files
```

### 3.4 `uv run pytest -q`

```text
381 passed, 4 deselected, 1 warning in 33.14s
```

唯一警告为既有 Starlette/httpx 弃用提示：`Using httpx with starlette.testclient is deprecated`。

### 3.5 定向测试

```text
32 passed
```

覆盖 TokenCounter、配置、daily digest、Executor、历史裁剪和 Tool Schema 预算边界。

### 3.6 `uv lock --check --offline`

```text
Resolved 178 packages in 1ms
```

## 4. 详细任务完成情况

- **T1 P30.1**：`TiktokenCounter` 按模型选择 encoding；`resolve_token_counter` 在缺包时回退到 `chars_per_token=1.5`。HarnessContext 的分组、摘要、用户输入裁剪统一使用同一个 TokenCounter，避免估算口径分裂。见 `src/multiscribe_agent/agents/token_counter.py:83`、`src/multiscribe_agent/agents/context.py:77`。
- **T2 P30.2**：默认 Google/Anthropic/OpenAI/Ollama 模型写入窗口和默认输出预算；支持 `PROVIDER_CONTEXT_WINDOWS`、`PROVIDER_OUTPUT_TOKENS` JSON 覆盖。见 `src/multiscribe_agent/config.py:14`、`src/multiscribe_agent/config.py:273`、`src/multiscribe_agent/config.py:395`。
- **T3 P30.3**：curate 节点仅投影六个必要字段，description 截断为 500 字符，保留 id 供结果映射。见 `src/multiscribe_agent/agents/pipelines/daily_digest.py:36`、`src/multiscribe_agent/agents/pipelines/daily_digest.py:387`、`src/multiscribe_agent/agents/pipelines/daily_digest.py:600`。
- **T4 P30.4**：Skill 拼接使用 4000 字符总预算，超过预算时保留明确截断标记；系统提示不会因多 Skill 无限膨胀。见 `src/multiscribe_agent/agents/executor.py:52`、`src/multiscribe_agent/agents/executor.py:761`。

## 5. 规范符合性自检

- [x] 源码新增接口均有类型注解，mypy 通过。
- [x] 未新增阻塞 I/O 或真实网络测试。
- [x] 配置解析只处理正整数 Token 限制，不记录凭据。
- [x] 测试使用 mock/fake Provider，不调用真实 LLM、Webhook 或 RSS。
- [x] 未修改 domain 分层方向和 Provider 实现。

## 6. 新增依赖

| 包 | 版本约束 | 用途 |
| :--- | :--- | :--- |
| `tiktoken` | `>=0.7` | 模型感知的精确 Token 计数 |

## 7. 风险、遗留与取舍

- **风险**：tiktoken 对未知中转模型使用 `cl100k_base`，无法覆盖代理自定义 tokenizer 的消息 framing 差异；已有 Provider 拒绝后一次 15% 降额重试作为误差缓冲。
- **风险**：模型窗口预置值是静态知识；Ollama 实际窗口仍取决于其 `num_ctx`，可通过环境 JSON 覆盖。
- **取舍**：Skill 上限按字符而非 Token 控制，作为系统提示硬上限；实际请求仍由 TokenCounter 进行最终预算计算。
- **遗留**：P30 未实现 Ollama `num_ctx` 透传、Provider 错误模式库扩展、ArtifactStore 跨重启持久化，这些保留在任务包 follow-up。
- **未做的事**：没有提交、推送或修改 GitHub 远端；没有运行真实凭据 e2e。

## 8. BLOCKED 项

无。此前发现的两个旧测试契约冲突已在决策者授权后完成校准，授权范围已记录在 1.2 节。

## 9. 对后续包的提示

- 后续 Agent/Workflow 节点应通过 `resolve_token_counter(provider, model)` 获取计数器，不要重新实例化旧的 `ConservativeTokenCounter()`。
- 新增 Provider 模型时应同步配置 `context_window_tokens` 或通过 `PROVIDER_CONTEXT_WINDOWS` 明确真实窗口。
- daily digest curate 输入应继续使用 `_curate_item_dict`，不要恢复 `UnifiedData.model_dump()` 全量投影。

## 10. 自评

- 我认为本包满足 `P30-上下文窗口生产链路修复.md` 的完成定义：✅

