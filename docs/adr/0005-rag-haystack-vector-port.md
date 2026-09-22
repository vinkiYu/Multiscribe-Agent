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
