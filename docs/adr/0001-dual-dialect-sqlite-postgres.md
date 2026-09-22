# ADR-0001 数据库双方言(SQLite 默认 + PostgreSQL 可选)

- 状态:已采纳
- 日期:2026-07 起(Stage6B 系列落地),2026-09-22 补录
- 关联:`infra/dialect.py`、`infra/postgres/`、`docs/postgres-migration-guide.md`、`docs/phases/Stage6B-*`

## 背景

MVP 以 SQLite+WAL 单文件起步,满足单人/单实例部署。随着采集并发、聊天链路和长期运行需求出现,`database is locked` 与备份能力成为约束。

## 备选方案

1. **全量迁移 PostgreSQL,删除 SQLite** — 部署门槛升高,违背"单机开箱即用"的既有承诺。
2. **引入 ORM 屏蔽差异** — 重写全部仓储,迁移面过大,且 ORM 掩盖 FTS5/tsvector 等方言特性。
3. **双方言:仓储层内收敛方言差异**(采纳)— `DialectRepositoryMixin` + `dialect.py` 承担 SQL 方言转换;`DB_DRIVER=postgres` + `DATABASE_URL` 启用 PG。

## 取舍

- 采纳 3:SQLite 与 PG 各自保留 FTS 与向量方言实现(sqlite-vec / pgvector),差异被 `VectorStorePort`/`FtsQueryBuilder` 收敛,上层零感知。
- 代价:新增 SQL 必须双方言可跑、双份测试矩阵;无正式迁移框架(靠幂等 DDL + 启动修复),复杂 schema 变更靠 Stage6B 式专项任务包。

## 后果

- 单机模式始终可用;PG 是可选升级而非必选项。
- 每个涉及 SQL 的 phase 文档必须包含双方言验证证据(review 硬检查项)。
