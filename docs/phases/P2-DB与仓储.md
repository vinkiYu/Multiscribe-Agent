# P2 — 数据库、仓储与 FTS5

> **状态**：未开始 · **依赖**：P1

## 目标

实现 SQLite（aiosqlite）持久化层：建表初始化、FTS5 全文索引、各仓储实现，并接通 P1 预留的 ConfigService kv 覆盖。完成后领域模型可落地入库。

## 前置依赖

P1（models/ports/config 完成）。

## 可改范围（白名单）

- `src/multiscribe_agent/infra/__init__.py`
- `src/multiscribe_agent/infra/db.py`（连接管理 + 建表 + PRAGMA + 启动修复）
- `src/multiscribe_agent/infra/repositories/__init__.py`
- `src/multiscribe_agent/infra/repositories/kv.py`
- `src/multiscribe_agent/infra/repositories/entity_json.py`
- `src/multiscribe_agent/infra/repositories/source_data.py`
- `src/multiscribe_agent/infra/repositories/task_log.py`
- `src/multiscribe_agent/infra/repositories/api_key.py`
- `src/multiscribe_agent/config.py`（仅实现 `load_overrides` 接 DB；补全 ConfigService）
- `pyproject.toml`（追加依赖：`aiosqlite>=0.20`）
- `tests/infra/conftest.py`（内存 SQLite fixture）
- `tests/infra/test_db.py`
- `tests/infra/test_repositories.py`
- `tests/test_config_db.py`

## 禁止改动（黑名单）

- 不动 domain/ 模型与 ports 定义（如发现 ports 缺方法，停下问，不擅自改 domain）。
- 不引入知识库/记忆相关表（kb_*/agent_memories）的复杂逻辑——建表占位即可，业务在 P16/P17。
- 不创建 llm/agents/plugins。

## 详细任务

### T1. `infra/db.py`

- `class Database`：封装 aiosqlite 连接，`async classmethod open(path) -> Database`，`async close()`。
- `init_schema(db)`：`CREATE TABLE IF NOT EXISTS` 全部表（对齐 ARCHITECTURE.md §6）：
  - `kv(key TEXT PK, value TEXT, expires_at REAL)`、`commit_history`、`source_data(id,title,url,description,published_date,source,category,author,metadata TEXT,fetched_at,ingestion_date,adapter_name,status)`、`task_logs(id INTEGER PK AUTOINCREMENT,task_id,task_name,start_time,end_time,duration,status,progress,message,result_count)`、`agents(id PK, data TEXT)`、`skills(id PK, data TEXT)`、`workflows(id PK, data TEXT)`、`mcp_configs(id PK, data TEXT)`、`schedules(id PK, data TEXT, updated_at)`、`api_keys(id,name,key_hash,prefix,source_fingerprint,verification_token,status,created_at,last_used_at)`、`embeddings`(后置占位：id,doc_id,vec BLOB,metadata)。
  - 占位建表（结构空壳即可）：`memory_categories`、`agent_memories`、`kb_categories`、`kb_documents`、`kb_chunks`。
- **FTS5 虚表 + 同步触发器**：
  - `source_data_fts`（索引 title, description, ai_summary[json_extract(metadata,'$.ai_summary')]），触发器 `trg_source_data_ai/ad/au`。
  - `agent_memories_fts`（content, tags）、`kb_chunks_fts`（content）触发器（占位表先建好，P16/P17 填业务）。
  - 启动时若 FTS 空而主表非空做全量回填（仅 source_data）。
- **PRAGMA**：`journal_mode=WAL`，`busy_timeout=5000`，`synchronous=NORMAL`，`foreign_keys=ON`。
- **启动修复**：把所有 `task_logs.status='running'` 改为 `'interrupted'`。
- 索引：source_data 上建 source/fetched_at/status/ingestion_date/published_date 索引 + 复合 `(published_date, fetched_at DESC)`、`(ingestion_date, fetched_at DESC)`。
- 提供 `async def init_db(path) -> Database`（open + init_schema + 修复）。

### T2. `infra/repositories/kv.py` — KvRepository

- 实现 `domain.ports.KvRepository`。
- `get(key)`：查 expires_at，过期惰性删除并返回 None；value 先 `json.loads`，失败原样返回。
- `set(key, value, ttl_seconds=None)`：`json.dumps`；expires_at = now + ttl 或 None。
- `delete(key)`。
- 全 async。

### T3. `infra/repositories/entity_json.py` — EntityJsonRepository

- 泛型 JSON blob 仓储，构造时传入 `db: Database`。
- `get(table, id) -> dict | None`：`SELECT data FROM {table} WHERE id=?`，`json.loads`。
- `save(table, id, data)`：`INSERT OR REPLACE`。
- `list_all(table) -> list[dict]`、`delete(table, id)`。
- **注意**：table 名用于本地 SQL 拼接，须做白名单校验（仅允许 `agents/skills/workflows/mcp_configs/schedules`），防注入。

### T4. `infra/repositories/source_data.py` — SourceDataRepository

- 实现 `domain.ports.SourceDataRepository`。
- `save_batch(items: list[UnifiedData], adapter_name) -> int`：批量 INSERT OR IGNORE（按 id 去重），返回实际写入数。
- `get_by_date_range(start, end, query_field="ingestion_date")`。
- `query(filters)`：支持 source/category/status 过滤 + 分页（limit/offset）。
- `search_fts(query, limit)`：`SELECT ... FROM source_data_fts WHERE source_data_fts MATCH ? ORDER BY bm25(...) LIMIT ?`，带 snippet 高亮。

### T5. `infra/repositories/task_log.py` — TaskLogRepository

- `create(log: TaskLog) -> str`：插入返回自增 id（转 str）。
- `update(log_id, **fields)`：动态拼接 SET（字段白名单）。
- `get(log_id)`。

### T6. `infra/repositories/api_key.py` — ApiKeyRepository

- `create(id, name, key_hash, prefix, source_fingerprint, verification_token, status)`。
- `get_by_prefix(prefix)`、`get_by_token(token)`、`update_status(id, status)`、`update_last_used(id)`、`list_all()`。

### T7. `config.py` 补全

- 实现 `ConfigService`：`load_overrides()` 从 kv 表读 `system_settings` key，返回 dict（合并到 Settings）。提供 `async def save_settings(settings_dict)` 写回 kv。
- `get_settings()` 仍是同步默认；新增 `async def get_settings_with_overrides() -> SystemSettings`（默认 + kv 覆盖）。

### T8. 测试

- `tests/infra/conftest.py`：`@pytest.fixture async def db()` → 内存 SQLite（`":memory:"`）+ init_schema。
- `tests/infra/test_db.py`：建表幂等（init 两次不报错）；FTS5 触发器工作（insert 后 source_data_fts 可查）；启动修复 running→interrupted；WAL pragma 生效。
- `tests/infra/test_repositories.py`：每个仓储 CRUD + 边界（kv TTL 过期、entity_json 白名单注入防御、source_data save_batch 去重、search_fts 召回、task_log 更新）。
- `tests/test_config_db.py`：save_settings → get_settings_with_overrides 往返一致。

## 验收条件

1. 全部仓储实现 ports 接口，mypy strict 通过。
2. 建表幂等；FTS5 触发器正确同步（insert/update/delete 均同步）。
3. kv TTL 过期生效（过期后 get 返回 None 且删除行）。
4. entity_json 拒绝非白名单表名（注入防御）。
5. source_data save_batch 按 id 去重，返回实际写入数正确。
6. ConfigService kv 覆盖往返一致。
7. 全部测试绿；外部无网络调用（纯内存 SQLite）。

## 测试方式

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest tests/infra tests/test_config_db.py -q
```
原始输出贴 review。

## 完成定义

7 条验收全满足；仓储有 happy + 边界 + 安全测试；SQL 全用参数化（无字符串拼接用户输入）。
