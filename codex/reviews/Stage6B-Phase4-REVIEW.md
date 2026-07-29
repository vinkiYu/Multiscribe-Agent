# Review: Stage6B Phase4 配置 Bootstrap 双驱动

执行包：`docs/phases/Stage6B-Phase4-配置Bootstrap双驱动.md`
完成日期：2026-07-29
执行者：Codex

## 1. 范围核对

本阶段实际改动仅覆盖任务包白名单：

| 文件 | 操作 | 内容 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/config.py` | 修改 | 新增 `db_driver`、`db_dsn`、`db_pool_size`、`db_pool_timeout` |
| `src/multiscribe_agent/infra/db.py` | 修改 | 新增 `init_database()` 双驱动工厂；SQLite 委托原 `init_db()`，PostgreSQL 懒加载 `asyncpg` 并应用 Phase 3 DDL |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 使用新工厂；按数据库协议派发 FTS builder 和 VectorStore |
| `src/multiscribe_agent/infra/postgres/__init__.py` | 新增 | PostgreSQL 可选模块入口 |
| `.env.example` | 修改 | 增加双驱动、DSN 和连接池示例，保留中英文注释 |
| `docker-compose.yml` | 修改 | 增加 `postgres:16-alpine`、健康检查、持久化卷和 app 依赖 |
| `tests/infra/test_init_database_driver_dispatch.py` | 新增 | 工厂、缺包、DDL、环境示例和 Compose 验收 |
| `tests/bootstrap/test_kb_init_vector_store_dispatch.py` | 新增 | SQLite/PostgreSQL FTS 和 VectorStore 派发验收 |

工作区中已有的 `docs/phases/README.md`、前端样式、Logo 删除、`.idea/`、`UI/` 及压缩包均为既有无关改动，未触碰、未纳入本阶段提交。

## 2. 验收条件逐条证据

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `SystemSettings.db_driver` 默认 `sqlite` | 通过 | `config.py:291-293`；`test_init_database_driver_dispatch_default_to_sqlite` |
| 2 | SQLite 工厂等价委托 `init_db` | 通过 | `db.py:888-894`；`test_init_database_sqlite_path_delegates_to_init_db` |
| 3 | 未安装 `asyncpg` 时 PostgreSQL 抛带安装提示的 `ImportError` | 通过 | `db.py:896-907` 懒加载；`test_init_database_postgres_requires_asyncpg_extra` |
| 4 | PostgreSQL DDL 顺序包含 pgvector、4 张表和 GIN 索引 | 通过 | `db.py:923-937`；fake asyncpg 验证 11 条语句及顺序 |
| 5 | 非法 driver 抛 `ValueError` | 通过 | `db.py:939`；`test_init_database_unsupported_driver_raises` |
| 6 | Bootstrap 注入 `FtsQueryBuilder(driver)` | 通过 | `bootstrap.py:448-461`；`test_kb_init_injects_fts_builder_for_driver` |
| 7 | SQLite 使用现有 `VectorStore` | 通过 | `bootstrap.py:454-459`；`test_kb_init_sqlite_uses_vector_store` |
| 8 | PostgreSQL 使用 `PostgresVectorStore` | 通过 | `bootstrap.py:451-456`；`test_kb_init_postgres_uses_postgres_vector_store` |
| 9 | `.env.example` 包含数据库驱动和连接池键 | 通过 | `.env.example:79-99`；`test_env_example_contains_db_driver_keys` |
| 10 | Compose 包含 PostgreSQL service 和 healthcheck | 通过 | `docker-compose.yml:13-31`；`test_docker_compose_contains_postgres_service` |
| 11 | 全量质量门禁通过 | 通过 | 见第 3 节 |

## 3. 测试与质量门禁

定向测试：

```text
10 passed in 0.59s
```

全量非 e2e 测试（使用仓库内可写的 basetemp，并设置 `HF_HUB_OFFLINE=1` 使用本机缓存模型，避免测试尝试联网下载 embedding 模型）：

```text
557 passed, 4 deselected, 1 warning in 24.52s
```

质量命令：

```text
ruff check .                 -> All checks passed!
ruff format --check .       -> 347 files already formatted
mypy src                     -> Success: no issues found in 181 source files
```

第一次未指定 `--basetemp` 的全量运行受 Windows 默认临时目录权限限制，产生 `PermissionError: C:\Users\hp\AppData\Local\Temp\pytest-of-hp`；改用仓库内 `.pytest-tmp-stage6b-phase4-final` 后完成上述全量结果。唯一警告是既有 Starlette/httpx deprecation warning。

## 4. 实现说明

- `db_driver` 支持 `DB_DRIVER` 与 `MULTISCRIBE_DB_DRIVER`；DSN 同时兼容 `DB_DSN`、`DATABASE_URL` 及对应 prefixed 变量，避免 `.env.example` 与运行时命名不一致。
- PostgreSQL 路径只在选中时导入 `asyncpg` 和 `PostgresDatabase`，SQLite 用户不需要安装 PostgreSQL extra。
- PostgreSQL 启动阶段只应用 Phase 3 已交付的基础 pgvector/FTS schema；Bootstrap 通过 `placeholder_style == DOLLAR` 识别后端，避免强依赖具体实现类。
- SQLite 继续执行既有 `migrate_kb()`；PostgreSQL 路径不重复执行该 SQLite migration。

## 5. 风险、遗留与取舍

- **PostgreSQL 仍不是完整业务迁移完成态。** 现有大量 Repository 和 Service 仍使用 SQLite `?` 占位符、`json_extract`、SQLite 专用表/迁移语句。Phase 4 仅完成“配置 + 基础 schema + 知识库装配”，在真实 PostgreSQL 上启动完整 ServiceContext 仍可能在后续业务 schema 初始化或旧 SQL 处失败；需由后续迁移阶段统一改造并做真实集成测试。
- **默认 Compose 密码仅用于本地开发。** `POSTGRES_PASSWORD=password` 不应直接用于生产环境；生产应通过 Secret/外部环境变量注入。
- **PostgreSQL DDL 依赖业务基础表已存在。** `source_data_fts`、`kb_chunks_fts`、`agent_memories_fts` 的外键要求对应业务表先由迁移阶段创建；Phase 4 的 fake 测试只验证执行顺序，不连接真实数据库。
- 未修改 `init_db()` 签名，保留旧调用方兼容性；现有 `Database` 类型别名仍指向 SQLite，工厂边界使用兼容 cast，待全仓库 Repository 完成协议化后可移除。

## 6. BLOCKED

无。本阶段白名单内实现和测试均完成；上述 PostgreSQL 业务 SQL 兼容性是明确的后续阶段风险，不构成本阶段阻塞。

## 7. 自评

我认为本阶段满足任务包的“配置 + Bootstrap 双驱动装配”完成定义，可以交由 ZCode 复审。建议下一阶段优先处理 Repository/Service 的 PostgreSQL 方言和基础业务表迁移，再进行真实 PostgreSQL 集成验证。
