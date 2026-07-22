# Agent 上下文优化清单

## 目的

本文统一记录 Agent Harness 的上下文优化项，作为后续实现和验收的待办清单。
当前以 v1.1.2 为基线，统一记录上下文预算正确性、工具结果压缩、长会话检查点、
Memory/Knowledge 按需注入及可观测性等后续优化项。

## 当前基线

`HarnessContext` 当前承担一次 Agent 运行内的消息组装、Token 估算、工具结果压缩和
历史裁剪。

- 默认 Token 预算：120,000；
- 预算预警阈值：80%；
- 工具结果超过 8,000 字符时，保留约 25% 头部、截断标记和约 75% 尾部；
- 截断标记包含原始字符数和省略字符数；
- 上下文超过预算时，保留系统提示词、第一组消息、重要消息和最近若干完整消息组；
- 被删除的中间历史会生成规则化 `Conversation Summary`；
- 带 Tool Call 的 assistant 消息及其 Tool Result 作为不可拆分的消息组。
- Memory/Knowledge 使用 JSON 作为不可信数据注入，并受统一 Context 预算约束；
- 每日推送已实现偏好过滤、有限记忆召回和 `curate` Agent 注入闭环。

## 优化项总览

| ID | 优化项 | 优先级 | 状态 |
| --- | --- | --- | --- |
| CTX-001 | 工具结果压缩的信息保真 | 高 | 基础实现，待类型化增强 |
| CTX-002 | 长会话历史裁剪的语义连续性 | 高 | 基础实现，待结构化检查点增强 |
| CTX-003 | 每日推送的记忆检索与 Prompt 注入闭环 | 中 | 日报已实现，待通用 Agent 接入 |
| CTX-004 | Provider/Model 感知的 Token 估算 | 高 | 基础实现，未知模型保守降级 |
| CTX-005 | RunBudget 多级硬预算 | 最高 | 已实现 |
| CTX-006 | 类型化工具结果压缩与 Artifact 引用 | 高 | 基础实现，待扩展持久化 Store |
| CTX-007 | 结构化 ConversationCheckpoint | 高 | 基础实现，待可选语义增强 |
| CTX-008 | 固定上下文与重要消息的超限保护 | 最高 | 已实现 |
| CTX-009 | 通用 Memory/Knowledge 上下文中间件 | 高 | 已实现，待多租户作用域增强 |
| CTX-010 | 上下文可观测性与质量评估 | 中 | 基础实现，待扩展离线数据集 |

---

## CTX-001：工具结果压缩的信息保真

### 当前问题

当前通用压缩已经从“只保留尾部”升级为“约 25% 头部 + 截断标记 + 约 75% 尾部”，
并记录原始长度与省略长度，解决了查询条件和尾部错误只能二选一的问题。

剩余问题是压缩器仍按字符处理，不理解 JSON、搜索结果、网页正文和日志结构；大型 JSON
可能被截断成非法文本，高相关条目也可能位于被省略的中间区域。

### 实际代码现状

- `HarnessContext._compress_tool_result()` 负责 8,000 字符阈值和头尾压缩；
- 头部比例由 `TOOL_RESULT_HEAD_RATIO=0.25` 控制；
- Tool Call 与对应 Tool Result 仍按原子消息组裁剪。

### 优化方案

1. 保留现有头尾压缩作为未知类型的稳定降级策略。
2. 在 Tool/Adapter 边界逐步引入结构化预览，避免把完整 HTML、日志或大 JSON 直接回填。
3. 将完整大结果保存为 Artifact，上下文仅注入摘要和引用。

推荐的类型化输出：

| 结果类型 | 优先保留内容 |
| --- | --- |
| 搜索/采集 | 查询条件、来源、总数、前 N 条 `{title, url, summary}` |
| JSON API | 根字段、分页字段和有限条目 |
| 网页正文 | 标题、作者、时间、摘要和相关正文片段 |
| 命令日志 | 命令、退出码、开头环境信息和尾部错误栈 |

### 降级路径

结构化压缩器无法识别类型、解析失败或返回超限时，继续使用现有头尾压缩；压缩失败不得阻断
Agent 主链路，并保留原始长度、省略长度和所用策略。

### 验收条件

1. 未超限的工具结果保持原样。
2. 超限结果同时包含头部、截断标记和尾部。
3. 压缩结果总字符数不超过 `tool_result_limit`。
4. Tool Call 与 Tool Result 的原子消息组语义不变。
5. 增加中英文、JSON、日志和极小预算的单元测试。

### 建议测试

- 未超限、刚好等于阈值和超过阈值的边界；
- 中英文、合法/非法 JSON、搜索列表、网页正文和异常日志；
- 极小 `tool_result_limit` 及 Tool Call/Result 原子性。

---

## CTX-002：长会话历史裁剪的语义连续性

### 当前问题

当前策略已经支持消息组原子性、重要消息固定、首组与最近消息保留，并会把删除的中间历史
按 User constraint、Assistant conclusion 和 Tool evidence 等类别写入规则摘要。

剩余问题是摘要仍属于规则摘录，不能稳定识别约束冲突、目标变更、证据可信度和未完成事项。

典型风险包括：

- 用户在中间轮次新增“不要推送融资新闻”等约束，后续可能被裁掉；
- 最近消息引用“前面的搜索结果”，但被引用的搜索结果已在中间历史中删除；
- 初始任务可能在长会话中已过时，机械保留首条消息会占用预算并干扰当前目标；
- 被删除历史虽有规则摘要，但可能遗漏跨消息关系、决策变化和证据来源；
- 首组或最近 Tool 消息组自身过大时，为保持原子性可能仍使最终上下文超出预期预算。

### 实际代码现状

- `trim_if_needed()` 按首组、重要组和最近组选择保留内容；
- `_message_groups()` 保证 Tool Call 与 Tool Result 不拆分；
- `_summarize_groups()` 生成规则摘要，单条摘录和总摘要都有字符/Token 上限。

### 优化方案

1. 在删除中间历史前生成结构化会话摘要，至少保留：当前任务目标、用户约束、已确认结论、
   已执行工具及关键证据、未解决事项。
2. 为消息增加重要性或固定标记机制；用户约束、明确决策、错误结论和人工确认内容优先保留。
3. 将摘要写入系统上下文或独立的压缩消息组，替代被裁掉的中间原文。
4. 对长期任务按当前任务查询相关性检索历史摘要或 Memory，而不是固定保留第一条消息。
5. 当系统提示、固定消息组已超过预算时，明确触发二级压缩或返回可诊断错误，避免“看似有预算、
   实际已超限”的隐性状态。

### 降级路径

语义摘要或结构化检查点生成失败时继续使用现有规则摘要；上一份有效摘要不得被非法或空结果
覆盖，固定内容仍超限时返回明确错误而不是静默删除系统安全规则。

### 每日资讯场景

日报 Pipeline 的主要节点较短，历史裁剪风险低于开放式多轮 Agent；但 `curate` 节点的
ReAct 工具调用和 Reflexion 反馈仍可能积累上下文。

建议将“上一轮评分、反馈、已筛选候选 ID、已排除来源”写入结构化摘要。下一轮只需读取摘要和
当前候选内容，无需依赖完整的中间 Tool Result，从而在控制 Token 的同时保持筛选标准一致。

### 验收条件

1. 裁剪后仍可从摘要中恢复任务目标、用户约束、关键结论和未完成事项。
2. 被标记为重要的消息不会因普通历史裁剪而丢失。
3. 最近消息对历史证据的引用可由摘要或保留证据支撑。
4. Tool Call 与 Tool Result 始终作为完整消息组处理。
5. 超长系统提示或固定消息组有明确的压缩/错误处理路径。

### 建议测试

- 中途新增/撤销用户约束和任务目标切换；
- 被裁剪工具证据被最近消息引用；
- 大量重要消息、超长首组和摘要再次超限；
- 摘要生成失败后的规则降级。

---

## CTX-003：每日推送的记忆检索与 Prompt 注入闭环

### 当前问题

当前项目已经通过 `DigestMemoryContextBuilder` 在默认 `DailyDigestPipeline` 的 `curate`
节点前完成偏好读取、硬约束过滤、候选排序、FTS 记忆召回、Top-K 压缩和 Prompt 注入。

剩余问题是这套闭环只服务日报场景；普通 Agent、Workflow Agent 和 API Agent 仍依赖调用方
显式传入 `memory_summaries`，Knowledge 也没有形成同等级的通用注入入口。

### 实际代码现状

- `DigestMemoryContextBuilder` 执行硬约束过滤、偏好排序、FTS 召回和摘要压缩；
- 记忆最多保留 5 条、总字符数最多 1,600；
- `AgentExecutor` 接受显式 `memory_summaries`，`HarnessContext` 同时具备 Memory/Knowledge 注入接口。

### 优化方案

1. 保留日报现有硬约束、软偏好、Top-K 和字符预算策略。
2. 抽象通用 `MemoryContextProvider`，供所有 Agent 入口按需复用。
3. 为 Knowledge 增加与 Memory 对称的有限召回和注入接口。
4. 统一定义检索不可用、无命中和注入失败时的无上下文降级路径。

### 降级路径

Memory 或 Knowledge 服务不可用、没有命中或超时后，Agent 按无增强上下文路径正常执行；记录
服务、失败类型和降级原因，但不向模型注入内部异常。

目标链路：

```text
当前日报任务 + 候选资讯
  -> MemoryService.search_entries()
  -> 相关记忆过滤、排序、去重
  -> Top-K 偏好摘要
  -> HarnessContext.inject_memory()
  -> Agent 进行 Top-N 精选与摘要生成
```

### 每日资讯示例

用户历史记忆：

```text
- 偏好 Agent、RAG、Python 工程实践
- 屏蔽 Web3 融资新闻
- 更关注开源项目和可落地的技术方案
```

当天候选中同时存在 Agent 工作流框架、RAG 评估方案、Web3 融资新闻时，系统应在进入 LLM
筛选前排除或显著降低 Web3 融资新闻优先级，并将前两类内容作为重点候选和 Prompt 偏好。

### 验收条件

1. 有匹配记忆时，`curate` Agent 的 system context 包含有限、格式化后的记忆摘要。
2. 无匹配记忆或 MemoryService 不可用时，日报任务可正常完成并走无记忆降级路径。
3. 硬约束能够阻止对应来源或主题进入最终候选；软偏好仅影响排序，不覆盖当前显式请求。
4. 注入的记忆数量和字符数有上限，不挤占主要任务的 Context 预算。
5. 覆盖记忆召回、排序、去重、注入、降级和最终筛选结果的单元/集成测试。

### 建议测试

- 日报、普通 Agent 和 Workflow Agent 的召回一致性；
- 无命中、Memory/Knowledge 单独失败和全部不可用；
- Top-K、字符预算、去重和跨用户/Agent 作用域隔离；
- 当前显式请求与历史软偏好冲突。

---

## CTX-004：Provider/Model 感知的 Token 估算

### 当前问题

`HarnessContext` 当前按约四字符一个 Token 估算上下文。中文、英文、代码和 JSON 的分词密度
差异较大，而且 Provider 单独接收的 Tool Definition/JSON Schema 尚未完整计入预算。

### 实际代码现状

- `context.py::_estimate_text()` 使用字符启发式，Tool Call arguments 会计入消息估算；
- Provider 返回的真实 `TokenUsage` 会累计，但只用于记录；
- 工具 Schema 在 `provider.stream(messages, tools)` 的独立参数中传入。

### 优化方案

1. 定义 `TokenCounter` 协议，根据 provider、model、messages 和 tools 计算 Token。
2. 已知模型使用对应 tokenizer，未知或 tokenizer 不可用时保留字符估算并增加安全系数。
3. 将 System、Memory、Knowledge、Conversation Summary、Tool Call 和 Tool Schema 分区计数。
4. 记录估算值与 Provider 实际 input usage 的偏差，用回归数据校准降级系数。

### 降级路径

Tokenizer 缺失、模型名称未知或代理端点不兼容时，继续使用字符估算，不阻断 Agent；日志记录
`token_counter_degraded` 及降级原因。

### 验收条件

1. Tool Schema 被纳入请求预算。
2. 已知模型估算误差目标不超过约 10%。
3. 未知模型仍可正常执行且采用保守预算。

### 建议测试

- 中英文、代码、JSON、大 Tool Schema 的 Token 估算；
- tokenizer 缺失和未知代理模型降级；
- 估算值与 Fake Provider usage 的误差指标。

---

## CTX-005：RunBudget 多级硬预算

### 当前问题

现有 `token_budget` 主要限制单次送入模型的上下文窗口，真实 usage 虽会累计，但不会阻止整次
Agent Run 继续调用模型或工具，无法严格控制成本和调用次数。

### 实际代码现状

- `HarnessContext` 累计 input/output/total usage；
- `AgentExecutor` 发出 `usage` 和 80% `budget_warning`；
- 最大轮数能限制循环，但没有累计输入、输出、工具调用和费用级硬预算。

### 优化方案

1. 新增 `RunBudget`，包含最大上下文 Token、累计输入、累计输出、总 Token、LLM 调用次数、
   工具调用次数和可选费用上限。
2. 每轮及每次工具执行前预检预算，Provider 返回 usage 后再次核算。
3. 达到预警线发出 `budget_warning`，超过硬限制发出 `budget_exhausted` 并立即停止后续调用。
4. 明确区分预算耗尽、最大轮数、超时和 Provider 错误等退出原因。

### 降级路径

Provider 不返回 usage 时使用 TokenCounter 估算累计值；价格信息未知时只禁用费用预算，其他硬预算
继续生效。

### 验收条件

1. 任一硬预算耗尽后不会再调用 Provider 或工具。
2. 最终事件包含预算类型、限制值、实际值和退出轮次。
3. 流式响应的 usage 不会被重复累计。

### 建议测试

- 单轮未超上下文、但多轮累计 total 超限；
- input、output、LLM 次数和工具次数分别触发；
- Provider 无 usage 时的估算降级；
- 预算耗尽后断言调用计数不再增长。

---

## CTX-006：类型化工具结果压缩与 Artifact 引用

### 当前问题

通用头尾压缩无法理解结果结构，可能破坏 JSON、遗漏搜索 Top-K、丢失网页元数据或保留大量
无关日志；上下文也无法按需重新读取被省略的完整内容。

### 实际代码现状

- `HarnessContext._compress_tool_result()` 提供稳定的头尾字符压缩；
- 工具返回值被序列化为字符串后直接写入 Tool Message；
- 当前没有统一压缩协议或 Artifact 引用。

### 优化方案

1. 定义 `ToolResultCompressor`，按 JSON、搜索、日志、网页和未知类型选择策略。
2. JSON 保留根字段、分页、错误和有限条目；搜索保留查询、来源、总数和 Top-K；日志保留命令、
   退出码、异常栈和尾部错误；网页保留标题、作者、时间、摘要和相关片段。
3. 完整结果写入 Artifact Store，上下文只保存结构化预览、压缩元数据和 `artifact_ref`。
4. 提供受预算控制的分页读取工具，禁止一次重新注入完整大结果。

### 降级路径

类型无法识别、解析失败或 Artifact Store 不可用时，继续使用现有头尾压缩，并标记
`strategy=head_tail` 和 `artifact_unavailable`。

### 验收条件

1. 压缩内容不超过预算且保留结果类型的关键字段。
2. JSON 策略输出有效结构，不产生半截 JSON。
3. Artifact 可追溯到原工具调用，并受权限和生命周期控制。

### 建议测试

- 大 JSON、搜索列表、HTML、异常日志和二进制/未知结果；
- Artifact 写入失败降级；
- 分页读取的权限、页大小和总 Token 限制。

---

## CTX-007：结构化 ConversationCheckpoint

### 当前问题

规则摘要可以减少历史丢失，但无法可靠表达当前目标、约束覆盖关系、证据来源和未完成事项；
摘要再次超长时采用头尾压缩，也可能破坏语义连续性。

### 实际代码现状

- 被裁剪消息按 User constraint、Assistant conclusion、Tools requested 和 Tool evidence 摘录；
- 单条摘录有字符上限，汇总摘要有独立预算；
- 摘要不保存来源 ID、约束版本和明确任务状态。

### 优化方案

1. 定义 `ConversationCheckpoint`：`current_goal`、`hard_constraints`、`decisions`、
   `completed_actions`、`key_evidence`、`open_items`、`failed_attempts` 和 `next_actions`。
2. 每条约束、结论和证据保留来源 message/tool_call ID。
3. 新指令与旧约束冲突时按最近明确用户指令更新，并保留 superseded 关系。
4. 先使用确定性抽取，按配置选择 LLM 语义压缩；LLM 结果必须通过结构校验。

### 降级路径

语义压缩失败、超时或预算不足时，回退到现有规则摘要；结构校验失败的结果不得覆盖上一份有效
Checkpoint。

### 验收条件

1. 裁剪后可恢复目标、硬约束、已完成工作、关键证据和下一步。
2. 已被用户修改的旧约束不会继续生效。
3. 摘要结论可追溯到原消息或 Artifact。

### 建议测试

- 中途新增约束、撤销旧约束和目标切换；
- 最近消息引用已裁剪工具证据；
- LLM 摘要超时、非法 JSON 和上一检查点保护。

---

## CTX-008：固定上下文与重要消息的超限保护

### 当前问题

System Prompt、Skill、Memory、Knowledge、首组消息和 `important=True` 消息优先保留；当这些固定
内容本身超过预算时，普通历史即使全部删除也无法保证最终请求不超限。

### 实际代码现状

- 用户原始请求和 Reflection feedback 会标记为重要；
- System 部分和重要组会优先占用预算；
- 剩余消息预算小于等于零时，当前裁剪流程可能无法继续压缩固定内容。

### 优化方案

1. 为 System、Skill、Memory、Knowledge、Checkpoint 和重要消息分别设置分区上限。
2. Skill 只注入当前任务相关说明；Memory/Knowledge 超限时减少 Top-K 或片段长度。
3. 多轮 Reflection 只保留最新反馈和累计问题摘要，不永久保留全部反馈原文。
4. 二级压缩后仍超限时返回 `context_budget_unresolvable`，禁止把隐性超限请求发给 Provider。

### 降级路径

按 Knowledge、Memory、非核心 Skill、旧 Reflection 的顺序缩减；系统安全规则和当前用户目标不得
静默删除。仍无法满足预算时显式失败并报告各分区占用。

### 验收条件

1. Provider 收到的消息与工具定义始终不超过计算预算。
2. 固定内容超限有确定的缩减顺序和可诊断错误。
3. 多轮重要反馈不会无限挤占上下文。

### 建议测试

- 超长 System Prompt、多个大 Skill、大量 Memory/Knowledge；
- 连续 Reflection feedback；
- 极小预算下的二级压缩和显式失败。

---

## CTX-009：通用 Memory/Knowledge 上下文中间件

### 当前问题

日报已经实现记忆闭环，但普通 Agent 和 Workflow Agent 不会自动召回；Knowledge 虽有
`inject_knowledge()`，却没有与 Memory 对称的通用执行入口和统一预算策略。

### 实际代码现状

- `AgentExecutor.run/stream()` 接受调用方显式传入的 `memory_summaries`；
- 日报使用 `DigestMemoryContextBuilder` 完成过滤、排序和有限注入；
- KBService 和 HarnessContext 已具备检索、注入的基础能力。

### 优化方案

1. 在 AgentExecutor 外围定义 `ContextProvider`，统一返回 Memory、Knowledge、来源和预算信息。
2. 请求携带 user、workspace、agent、session、task 和最大注入预算等作用域。
3. 使用 FTS/向量相关度、重要度、时间和可信度混合排序，并执行去重。
4. 当前明确用户指令优先于历史软偏好，硬约束必须有可信来源。
5. AgentDefinition 可关闭召回、限制类别、Top-K 和各分区预算。

### 降级路径

Memory 或 Knowledge 任一服务不可用时，另一服务仍可工作；全部不可用时走无增强上下文路径，
不得阻断主任务，并记录降级原因。

### 验收条件

1. 普通 Agent、Workflow Agent 和日报复用同一召回协议。
2. 不同用户、工作区和 Agent 的上下文严格隔离。
3. 注入总量受预算控制，当前用户请求不会被历史偏好覆盖。

### 建议测试

- 三种 Agent 入口的一致召回；
- 无命中、单服务失败和全部降级；
- 跨用户/跨 Agent 隔离；
- 硬约束与软偏好冲突。

---

## CTX-010：上下文可观测性与质量评估

### 当前问题

当前已有 usage 和预算预警，但无法完整回答哪些内容被裁剪、各分区占用多少、为何召回某条记忆，
以及压缩后是否仍保留关键约束和证据。

### 实际代码现状

- Agent 事件包含 `usage` 和 `budget_warning`；
- 截断标记记录工具结果原始长度和省略长度；
- 缺少统一的压缩事件、分区 Token 指标和上下文质量数据集。

### 优化方案

1. 增加 `context_pressure`、`context_compacted`、`context_degraded` 和
   `context_budget_exhausted` 事件。
2. 记录 System、Skill、Memory、Knowledge、History、Checkpoint 和 Tool Schema 的 Token 占用。
3. 记录压缩策略、压缩前后大小、丢弃消息组数、Artifact ID 和召回原因。
4. 建立离线 fixture，评估目标、约束、决策、证据和未完成事项的保留率。
5. 指标和日志只保存摘要与指纹，不记录凭据或完整敏感正文。

### 降级路径

指标后端或 OTel 不可用时保留本地结构化事件；可观测性失败不得影响 Agent 主链路，敏感内容
默认不采集。

### 验收条件

1. 可从一次 trace 还原预算变化、压缩策略和退出原因。
2. 能比较压缩前后 Token、延迟和关键事实保留率。
3. 日志、事件和指标中不包含 API Key、Webhook 或完整敏感工具结果。

### 建议测试

- 触发预警、压缩、降级和硬预算耗尽的事件序列；
- 各上下文分区 Token 汇总一致性；
- 离线 fixture 的关键事实保留率；
- 敏感数据脱敏回归。

---

## 实施顺序

1. P0：实现 CTX-005 和 CTX-008，先保证预算不会隐性超限。
2. P1：实现 CTX-004、CTX-006 和 CTX-007，提高估算、压缩和长会话连续性。
3. P1：实现 CTX-009，将日报已有能力抽象为通用 Agent 上下文中间件。
4. P2：实现 CTX-010，建立上下文可观测性和离线质量评估。
5. CTX-001～003 保留为已有基础能力的持续增强项，不重复实现现有链路。

## 影响范围

- `src/multiscribe_agent/agents/context.py`
- `src/multiscribe_agent/agents/executor.py`
- `src/multiscribe_agent/agents/pipelines/daily_digest.py`
- `src/multiscribe_agent/memory/`
- `tests/agents/test_context.py`
- `tests/agents/test_executor.py`
- `tests/agents/pipelines/test_daily_digest.py`

## 非目标

- 本清单不要求一次性重写 Harness，应按 P0、P1、P2 分阶段交付。
- 本清单不以增加 LLM 摘要调用作为默认方案，所有语义压缩必须受 RunBudget 控制。
- 本清单不改变当前用户指令高于历史软偏好的优先级原则。
