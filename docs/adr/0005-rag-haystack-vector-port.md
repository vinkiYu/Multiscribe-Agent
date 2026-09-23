# ADR-0005 RAG 子系统选型:Haystack 管 RAG,向量库沿用存量 Port,Qdrant 仅可选适配

- 状态:已采纳(P66 总览批准时生效)
- 日期:2026-09-22
- 关联:`docs/phases/P66-RAG-重构总览.md`、`knowledge/vector_protocol.py`、`knowledge/vector_store.py`、`agents/context_provider.py`

## 背景

知识检索(KB 的 FTS+向量)与资讯检索(source_data 的 FTS)是两套割裂链路;ContextProvider 丢弃 `agent_id`(scope 未生效);检索结果是无 metadata 的裸文本;embedding 硬编码英文小模型。规划引入外部 RAG 框架收敛为一条子系统。候选:Haystack 2.x + Qdrant(蓝图首选);自研扩展;pgvector 深化。

## 决策

1. **Haystack 承担 RAG pipeline 标准化**(indexing: 文档规范化/切分/embedding;retrieval: BM25+dense+融合),但**禁用其 DocumentStore 持久化**——索引产物只落自研 `VectorStorePort` + 业务表,业务库是唯一真相源。业务层只依赖自研 `RagService` 接口,不感知 Haystack。
2. **向量库不新增服务**:沿用存量 `VectorStorePort`(SQLite→sqlite-vec / PostgreSQL→pgvector);**Qdrant 降级为 Port 的可选适配器**,等规模(千级→百万级 chunk)、过滤复杂度或量化需求被证明后再启用。否决蓝图"Qdrant 首选":其增益在本项目量级用不上,而新服务的部署/备份/一致性成本是即期负担;且"外部实现藏在接口后"的原则对向量库与对 Haystack 应当一致。
3. **评估门禁前置**:P66.1 先建真实查询集(≥30 条,中英混合)与 Recall@K/MRR/引用覆盖率基线;P66.6 仅当新方案任一指标不低于旧基线才允许删除旧检索路径(RRF retriever/kb_service.search)。复用 P64 的 metrics_schema/ledger 模式。
4. **三个蓝图缺失项补齐**:中文分词(jieba 预分词组件,否则 hybrid 在中文查询下静默失效);scope schema 迁移(kb 表补 owner 字段 + 回填,依赖"知识库共享 vs 按用户隔离"的产品决策);reranker 默认关、以 MRR 增益 vs p95 增量的数字门禁决定开启(bge-reranker-v2-m3 为候选)。

## 被否/搁置方案

- Qdrant 首选:见决策 2;以适配器形式保留未来通道。
- Haystack 全托管(含 DocumentStore/组件自治):违背"业务库唯一真相源",否决。
- 不引框架纯自研扩展:pipeline 标准化、组件生态与可评估性收益不足,放弃。

## 后果

- 获得:统一索引入口(SourceData+KB+本地文档)、引用证据对象(RetrievedEvidence)、scope 真正生效、检索可评估可回归。
- 承担:仓库同时存在 LangChain 与 Haystack 两个框架——以"Haystack 只进 knowledge 边界内、依赖单独 commit"控制;Haystack 组件为同步 `run()`,接入 async 需线程池包装(并发预算按线程池上限压测)。
- 现存检索债务(事后过滤、搜索期重复 encode、无界 embedding 缓存、`del agent_id`)在 P66 对应子包作为验收项清偿。

## 决策补录(2026-09-22，P66.1)

### D-1 知识库隔离边界

知识库采用 **user 硬隔离 + agent 软过滤**。统一 `RetrievalScope` 必须携带 `user_id`;跨用户的 KB 文档和 chunk 不得被检索或注入。`agent_id` 作为可选过滤维度传入:有值时只筛选该 Agent 的知识,为 `None` 时在当前用户范围内不过滤 Agent。选择该方案是为了保留当前单用户部署的共享语义,同时为多用户隔离提供不可绕过的硬边界;否决 agent 硬隔离作为唯一边界,避免把同一用户的共享知识重复复制到多个 Agent。

### D-2 SourceData 的 RAG 索引策略

SourceData **进入统一 RAG 索引**,但只索引最近 N 天的内容(默认 7 天,由 `RAG_SOURCE_WINDOW_DAYS` 配置),采用增量更新,过期资讯自然滚出索引。`source_data` 表和现有 FTS 路径仍是事实源与降级路径,在 P66.6 的 Recall@K/MRR/引用覆盖率门禁通过前不得删除。选择时间窗而非全量索引,是为了让资讯检索保持时效并控制向量索引规模、重建成本和旧内容噪声。

P66.1 将上述语义冻结为 `KnowledgeDocument`、`KnowledgeChunk`、`RetrievedEvidence`、`RetrievalScope` 和 `RagService` 契约;P66.2 起的 Haystack 适配器不得改变这些边界。

## 决策补录(2026-09-23，P66.5)

1. Embedding 模型通过 `RAG_EMBEDDING_MODEL` / `RAG_EMBEDDING_DIM` 配置，默认使用
   `BAAI/bge-small-zh-v1.5` 的 512 维空间。SQLite `vec0` 表的维度随配置创建；模型或维度变化
   时必须先备份数据库，再由重建脚本清理派生索引并全量重建。业务表仍是唯一真相源，数据库备份、
   向量缓存和评测产物不入库。
2. Reranker 使用可选的 `BAAI/bge-reranker-v2-m3`，通过 `RAG_RERANKER_ENABLED` 显式开启，
   默认关闭。它只位于 RRF 融合之后、Evidence 返回之前；是否改为默认开启，必须同时满足
   MRR 增益至少 `+0.05` 且 p95 延迟增量不超过 `+1500ms`，并由决策者拍板。
3. 本机离线或模型下载失败时，系统保留 BM25/向量降级路径，不伪造 bge-zh 质量结论；评测报告必须
   将真实模型指标标为 `PENDING`，直到模型可加载并完成冻结集 A/B。
