# ADR-0006 PostgreSQL-only:移除双数据库支持,取代 ADR-0001

- 状态:已采纳(2026-09-23,决策者拍板"定位 B + 移除 SQLite")
- 取代:**ADR-0001(双方言:SQLite 默认 + PostgreSQL 可选)**
- 关联:`infra/dialect.py`、`infra/connection_pool.py`、Stage6B 系列、`docs/adr/0005`(pgvector 转正)

---

## 背景

ADR-0001 采纳双方言时,产品假设是"单人单文件部署为主,PG 为可选升级"。此后工程投资持续转向多实例服务化:Redis 分布式调度锁、连接池抽象、Stage6B 完整 PG 迁移工程、JWT/API Key 服务化设施。P66 全程进一步暴露了双方言的实测成本:

1. **维护税**:22 个文件的 `PgDialect` 分支、双份向量实现(vec0 怪癖:不支持 REPLACE)、PG 维度迁移两轮挂账(384→512)、每处 SQL 写两遍测两遍;
2. **验证失衡**:全部真实运行发生在 SQLite;PG 路径零次真实执行,等于持续为一个未使用的分支付全价;
3. **定位冲突**:Redis 分布式锁与 SQLite 单文件在语义上互斥(文件锁跨不了机器)——工程身体已进入"多实例 PG 服务化",决策却未明说。

## 决策

1. **PostgreSQL 成为唯一受支持的数据库**。`DB_DRIVER` 配置、SQLite 分支、aiosqlite/sqlite-vec 依赖全部移除。
2. **方言抽象层移除**:`infra/dialect.py`、`DialectRepositoryMixin` 及 22 个消费文件的方言分支塌缩为单路 PG SQL(`$n` 占位符、tsvector FTS、pgvector)。
3. **SQLite 专属组件删除**:`infra/connection_pool.py`(SQLite 专用池)、FTS5 虚表与触发器路径、`workflow/iteration_store.py` 与 `eval/collector/random_pool.py` 的 sqlite3 直连改造为 PG 仓储。
4. **测试与开发**:verify 的 pytest 步骤通过 testcontainers 拉起一次性 PG(默认),或连 `TEST_DATABASE_URL` 指向的本地 PG;开发者本地需 Docker(首选)或本地 PG 实例。
5. **运行数据一次性迁移**:Stage6B 的 `migrate_sqlite_to_postgres.py` 全量搬迁 + RAG 派生索引按当前模型(bge-zh 512)重建;旧 `database.sqlite` 归档不删。

## 备选方案与否决理由

- **维持双方言**:持续双倍维护/测试税,且 PG 路径持续零验证——被 P66 实测成本否决。
- **仅移除向量层的双方言**(numpy 单实现):被定位决策否决——多实例服务化下,内存/BLOB 向量是反分布式设计,pgvector 才是战略存储。
- **SQLite 保留为"仅开发"模式**:仍需维护全部分支,节省有限,复杂度不减。

## 后果

**收益**:22 个文件的方言分支消失;删除 aiosqlite、sqlite-vec、connection_pool、FTS5 触发器体系;向量层单一实现(pgvector);FTS 单一实现(tsvector);"每处 SQL 写两遍测两遍"的税基清零。

**代价**:
- 本地开发/测试需要 Docker(testcontainers)或本地 PG——贡献者门槛上升,属定位 B 的既定成本;
- 既有 SQLite 部署用户需执行一次性数据迁移(工具已在);
- 无正式迁移框架的既有短板仍在,PG 上的 schema 演进纪律(幂等 DDL)需保持。

**边界**:Redis 分布式锁、连接池语义、多用户体系(仍单 admin)不在本决策范围内;`retriever.py` 已在 P66.6 删除,本决策不再涉及旧检索路径。
