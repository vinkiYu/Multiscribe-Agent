# CONTEXT.md — 领域词汇表(强制)

> 人与 AI Agent 共用的业务语言。写 Issue/Spec/计划书/测试名/日志字段时必须使用本表术语。
> 术语变更时同步检查所有消费者(类型/字段/文档/测试),不要只改本文。
> 格式参照 AI Coding 工程规范:每个术语给出定义 + Avoid(禁用叫法)。

---

## 内容与采集

**SourceData**

一条已被采集适配器(RSS/GitHub Trending/AI Search/TLDR AI 等)写入 `source_data` 表的原始资讯记录。是策展、检索和聊天搜索的事实源。

_Avoid_: 新闻、News Item、RawFeed、UnifiedData 行

**UnifiedData**

采集适配器与 Agent/发布器之间传递内容的**规范内存模型**(Pydantic)。 adapters 产出 UnifiedData,经 IngestionService 落库为 SourceData。它是传输契约,不是存储实体。

_Avoid_: 把 UnifiedData 和 SourceData 混用;FeedItem、Article

**Ingestion**

适配器抓取外部内容 → 规范化为 UnifiedData → 写入 source_data 表的完整过程。每次执行留下 TaskLog。

_Avoid_: 抓取单独指代整个链路;Crawl、Fetch(仅指 HTTP 层动作)

## 策展与日报

**Curation(策展)**

从候选池中挑选应进入日报条目的行为。评测口径为 Precision/Recall/F1(与 expected_selected_ids 比对)。执行者是 curator(默认 curation agent 的 CURATE_PROMPT)。

_Avoid_: 筛选、过滤(filter 特指 CandidateFilter 的硬性偏好过滤)、Select(仅指模型单次输出)

**Candidate / 候选池**

一次策展决策面对的 10 条左右 SourceData 子集。评测中对应 fixture 的 `candidates` 数组。

_Avoid_: Items(歧义)、Pool 单独使用

**CuratedDigest**

策展产出的最终日报聚合(条目 + 概览 + 分区),经 renderers 渲染后由 Publisher 推送。

_Avoid_: Digest Report、Newsletter(口语可用,文档中统一 CuratedDigest)

**Target Count**

单次策展允许输出的最大条目数(默认 12)。提示词中的硬上限,与软下限(score≥7 至少选 1)配对。

_Avoid_: Top-N(仅指排序取前 N 的通用动作)

## 知识与检索

**KBDocument / KBChunk**

用户上传或文本摄入的长期知识文档(`kb_documents`)及其切分单元(`kb_chunks`,带 sha256 去重)。与 SourceData 严格区分:前者是长期知识,后者是资讯流。

_Avoid_: Knowledge 单独指表;Document 与 UnifiedData 混称

**KnowledgeDocument / KnowledgeChunk**

P66 RAG 子系统的统一文档与切分契约:KnowledgeDocument 同时承载 KB 与 SourceData 的来源、用户归属、时间和内容哈希;KnowledgeChunk 是可被索引和召回的最小内容单元。它们是跨后端的对外模型,不是新的业务表。

_Avoid_: 把 KnowledgeDocument 当作数据库实体;用 UnifiedData 代替已索引文档;把 KBDocument 与 SourceData 混成同一来源

**RetrievedEvidence**

RAG 返回给 Agent 的带证据结果,同时包含 KnowledgeChunk、KnowledgeDocument、检索分数、检索来源和 RetrievalScope。后续 Agent Context 注入必须优先消费该对象,不得只传裸文本而丢失标题、URL、来源和范围。

_Avoid_: RetrievedContext 裸字符串列表;无来源的 chunk 文本;把 score 当作业务可信度

**RetrievalScope**

检索可见范围。`user_id` 是硬隔离边界,跨用户不可见;`agent_id` 是可选的软过滤维度,为 None 时表示在当前用户范围内不过滤 Agent。categories、sources、doc_types 和时间范围是附加过滤条件。

_Avoid_: 把 agent_id 当成用户权限边界;省略 user_id 的全局检索;跨用户共享 KB

**RagService**

业务层依赖的统一 RAG 服务协议,负责 retrieve、index_document、rebuild_index 和 capabilities。Haystack、BM25、向量库和可选 reranker 都只能藏在该协议之后;P66.1 只冻结接口,实现从 P66.2/P66.3 开始。

_Avoid_: 在 Agent/API 里直接调用 Haystack;把 Retriever、KBService 和 SearchSourceDataTool 当作统一服务名

**时间窗索引**

SourceData 的 RAG 索引策略:默认只索引最近 7 天的资讯,通过 `RAG_SOURCE_WINDOW_DAYS` 配置,并采用增量更新;旧资讯自然滚出索引。SourceData 的现有 FTS 路径在迁移期间始终保留。

_Avoid_: 把全部历史 SourceData 永久放入向量索引;用时间窗索引替代事实源 `source_data` 表

**Hybrid Retrieval(混合检索)**

FTS5/bm25 关键词召回 + 向量召回,经 RRF(Reciprocal Rank Fusion, K=60)融合的检索方式。由 `rag/RagService` 统一实现,旧 `knowledge/retriever.py` 已删除。

_Avoid_: 语义检索(仅指向量一路)、双路检索

**VectorStorePort**

向量存取的方言无关协议(`knowledge/vector_protocol.py`)。SQLite 走 sqlite-vec,PostgreSQL 走 pgvector。检索/索引代码只依赖 Port,不依赖具体方言。

_Avoid_: 直接引用 sqlite-vec/pgvector 表名于上层代码

**Degraded(降级)**

向量或 embedding 组件不可用时,混合检索自动退化为纯关键词检索的运行状态,由 `KBCapabilities.degraded` 表达,不得视为故障中断。

_Avoid_: Error/Failure 描述降级态

**MemoryEntry / AgentMemory**

Agent 长期记忆条目(`agent_memories`,FTS 可检索,带 importance/tags)。与 KB(用户显式上传)来源不同:记忆由系统/Agent 沉淀。

_Avoid_: 把 Memory 和 KB 统称"知识库"

## Agent 与执行

**Agent / AgentDefinition**

一个可执行的智能体配置(模型、提示词、工具、温度),存于 `agents` 表(JSON blob)。默认策展 agent 在 bootstrap 中幂等创建,名为 default-curation-agent。

_Avoid_: Bot、Assistant、Worker

**Harness**

Agent 的执行外壳(`agents/executor.py` + `context.py`):滑动窗口上下文、工具循环、token 预算、反思重试。

_Avoid_: Runtime、Engine(留给 DAG)

**Workflow / DAG**

声明式步骤图(`WorkflowDefinition` → `WorkflowStep`),自研 Kahn 拓扑引擎执行,支持并行层、子工作流、Loop 节点(自评收敛)。

_Avoid_: Pipeline(专指 daily_digest 的具体流水线;P66 后也指 Haystack pipeline,需上下文区分)、Chain

**Loop 节点**

DAG 中带 `max_iterations` + 退出条件的自评迭代节点(执行→评估→精炼收敛),策展环节用它做质量收敛。

_Avoid_: Retry(仅指传输层重试)

**Tool**

Agent 可调用的能力单元(插件四类之一,JSON Schema 声明参数),如 SearchSourceDataTool。与 MCP 工具经 ToolRegistry 双注册统一暴露。

_Avoid_: Function、Skill(Skill 是独立概念:带 frontmatter 的提示词模板条目)

## 基础设施

**Provider**

LLM 供应商抽象(`llm/provider.py` Protocol + openai/anthropic/google/ollama 实现),配置含 api_key/base_url/proxy/model。评估路径另有独立 provider 解析(`_resolve_eval_provider`)。

_Avoid_: Model(模型是 Provider 的一个参数)、Client

**ServiceContext / bootstrap**

进程级组合根:懒加载全部服务、注册调度任务、`reload()` 热重载、`close()` 释放。唯一允许知道所有具体实现的位置。

_Avoid_: Container、Application 单独使用

**双方言(Dual Dialect)**

同一套仓储 SQL 同时支持 SQLite(默认)与 PostgreSQL(`DB_DRIVER=postgres`),由 `infra/dialect.py` + `DialectRepositoryMixin` 承担差异。新增 SQL 必须双方言可跑。

_Avoid_: 跨库 ORM(未使用 ORM)、Migration(无正式迁移框架)

**TaskLog**

后台任务(采集/调度/推送)的生命周期记录(`task_logs`:running→success/error),是排障与评测追溯的事实源。

_Avoid_: Log 泛指(structlog 应用日志与 TaskLog 是两回事)

## 评测(P64)

**Eval / 评测体系**

四层指标(结果/过程/效率/安全)× 五段链路(采集/清洗/评测/质检/分析)× 六步周流水线。入口 `eval/` 包与 `scripts/run_eval_curation.py`。

_Avoid_: Test(指单元测试)、Benchmark 单独泛指

**Baseline(基线)**

受保护的历史最佳成绩(`data/eval/baselines/`)。新跑分多维劣化超阈值时拒绝覆盖并写入 rejected-run ledger。

_Avoid_: 旧分数、Benchmark Result

**Fixture**

评测用候选池文件(`tests/eval/fixtures/cr_NNN.json`),含 candidates + 标准答案 + schema_version + 标注人。

_Avoid_: 测试数据(Test data 泛指)、Mock

**RegressionDetected**

多维质量门禁抛出的异常:任一维度劣化超过 `MetricThresholds` 即中断基线更新。系统"只升不降"的保证。

_Avoid_: 回滚(指 git 操作)、Alert(指告警通知)

---

## 命名纪律(简要)

1. 写代码/测试/文档前先查本表;新概念先入表再用。
2. 同一概念全仓一个名字:表名、Pydantic 模型、日志字段、文档术语保持一致。
3. 历史文档中的旧叫法不回改,但新内容必须用本表术语;发现冲突时以本表 + 当前代码为准。
