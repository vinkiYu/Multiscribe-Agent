# ADR-0007: Qdrant 作为唯一向量存储(完全替换 pgvector)

- 日期:2026-10-04
- 状态:已接受(决策者拍板"引入向量数据库",选型 Qdrant + 完全替换 + 删净)
- 取代:ADR-0005 的向量存储部分(pgvector 决策)
- 修订:ADR-0006(PostgreSQL-only)增加显式例外——向量数据不在 PostgreSQL 内,其余一切保持 PG-only

## 背景

P66 以 `VectorStorePort` 收敛了向量读写的交换面;P67 塌缩后 pgvector 的触点仅剩 3 处(`knowledge/vector_store.py`、`rag/dense.py` 委托、`scripts/rebuild_rag_index.py`)。本机数据量 4218 条 512 维向量、p95 检索 30-40ms——**性能不是引入动机**。动机:向量库工程经验与叙事、存储职责单一化(向量从关系库中独立)、为规模上量预置。

## 决策

1. 引入 **Qdrant** 作为唯一向量存储;删除 pgvector 的全部残留(旧实现、`chunk_vectors` 表、`CREATE EXTENSION vector`、断言测试、测试镜像依赖)。
2. `QdrantVectorStore` 原地替换 `knowledge/vector_store.py` 的 `VectorStore`,三方法面完全不变:`upsert(chunk_id, embedding)` / `delete(chunk_id)` / `top_k(vector, k) -> [(chunk_id, distance)]`;`VectorStoreUnavailable` 留原文件,`rag/dense.py` 零 import 变更。
3. 点 ID 用 `uuid5(chunk_id)` 确定性生成:upsert 天然幂等、delete 无需查询;payload 只存 `chunk_id`。
4. 单集合 `rag_vectors`,dim=512(沿用 P66 冻结维度,bge-small-zh-v1.5),distance=Cosine,启动时懒建。
5. **一律精确检索**(`SearchParams(exact=True)`):10 万点以内精确检索毫秒级,免去 HNSW 调参与评估波动。**阈值约定:向量规模超过 100,000 点时才修订本 ADR 启用 ANN。**
6. Qdrant 侧 **scope-blind**:不存 user_id 等任何 scope payload;硬隔离仍由 PG `rag_index_registry` 回联 + `scope_predicate` 二次过滤(与 P66 语义一致)。
7. 不引入 gRPC(REST);不做双跑灰度。

## 一致性代价(认账)

向量数据成为跨库派生数据(非事务双写):PG `rag_chunks`/`rag_index_registry` 与 Qdrant 点之间可能漂移。兜底:`rebuild_rag_index.py` 是对账器;运行期以 `rag_index_registry` 行数 vs Qdrant `count()` 对账;漂移时重建。

## 后果

- 检索链路从"同库 join"变为"Qdrant 召回 → PG 过滤"两段;网络往返多一跳(本机 REST,毫秒级)。
- 运维多一个有状态容器(`qdrant/qdrant`,单容器单卷)。
- 测试基建双容器化(PG `postgres:16-alpine` + Qdrant `qdrant/qdrant`),`TEST_QDRANT_URL` 可旁路容器直连。
- 冻结评测集门禁由 P66/P67 口径延续:R@5=0.625 / semantic=0.25 / citation=1.0 / MRR=0.5521 逐位对齐(精确检索 + 同余弦度量,不一致即 bug)。
