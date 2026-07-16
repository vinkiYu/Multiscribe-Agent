# Review: P2-数据库、仓储与 FTS5

**执行包**：`docs/phases/P2-DB与仓储.md`
**完成日期**：2026-07-16
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件清单

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `pyproject.toml` | 修改 | 添加 `aiosqlite>=0.20` runtime 依赖 |
| `uv.lock` | 修改 | 锁定 `aiosqlite==0.22.1` |
| `.pre-commit-config.yaml` | 修改 | 为隔离 mypy hook 同步 aiosqlite 依赖 |
| `src/multiscribe_agent/infra/__init__.py` | 新增 | infra 包声明 |
| `src/multiscribe_agent/infra/db.py` | 新增 | aiosqlite 连接、schema、FTS、修复、回填 |
| `src/multiscribe_agent/infra/repositories/__init__.py` | 新增 | 仓储包声明 |
| `src/multiscribe_agent/infra/repositories/kv.py` | 新增 | KV JSON/TTL 仓储 |
| `src/multiscribe_agent/infra/repositories/entity_json.py` | 新增 | JSON blob 仓储与表名白名单 |
| `src/multiscribe_agent/infra/repositories/source_data.py` | 新增 | SourceData 批量保存、过滤与 FTS 查询 |
| `src/multiscribe_agent/infra/repositories/task_log.py` | 新增 | TaskLog CRUD 与字段白名单更新 |
| `src/multiscribe_agent/infra/repositories/api_key.py` | 新增 | API key hash 元数据仓储 |
| `src/multiscribe_agent/config.py` | 修改 | KvRepository 注入、保存和覆盖加载 |
| `tests/infra/conftest.py` | 新增 | 内存 SQLite fixture |
| `tests/infra/test_db.py` | 新增 | schema、FTS、WAL、修复、回填测试 |
| `tests/infra/test_repositories.py` | 新增 | 全仓储 CRUD、安全和边界测试 |
| `tests/test_config_db.py` | 新增 | ConfigService KV 往返测试 |
| `codex/reviews/P2-REVIEW.md` | 新增 | 阶段 review 归档（沿用 P1 已提交惯例） |

- [x] P2 白名单内的源码、配置、依赖和测试文件全部覆盖。
- [x] `.pre-commit-config.yaml` 因新增 runtime 依赖，按 `codex/EXEC_PROMPT.md` 的自动白名单授权同步。
- [x] `uv.lock` 按全局授权保留并将随提交进入版本库。
- [x] 未修改 domain 模型或 ports；未创建 llm/agents/plugins；知识库和记忆表仅为 schema/FTS 占位。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- |
| 1 | 全部仓储实现 ports 接口，mypy strict 通过 | PASS | 5 个仓储；`Success: no issues found in 17 source files` |
| 2 | 建表幂等；FTS5 insert/update/delete 同步 | PASS | `test_schema_initialization_is_idempotent`、`test_source_fts_triggers_sync_insert_update_and_delete` 通过 |
| 3 | KV TTL 过期后返回 None 且删除行 | PASS | `test_kv_crud_and_expired_value_is_deleted` 通过 |
| 4 | entity_json 拒绝非白名单表名 | PASS | `test_entity_json_crud_and_table_injection_defense` 通过 |
| 5 | source_data 按 ID 去重并返回实际写入数 | PASS | `test_source_data_batch_deduplication_filtering_and_fts` 通过 |
| 6 | ConfigService KV 覆盖往返一致 | PASS | `test_config_service_persists_and_loads_kv_overrides` 通过 |
| 7 | 测试全绿且无外部网络 | PASS | 定向 10/10、全量 31/31；均使用内存/临时 SQLite |

## 3. 测试与质量门（原始输出）

### 3.1 依赖同步

```text
Resolved 42 packages in 9.86s
Building multiscribe-agent @ file:///F:/software/Multiscribe/MultiscribeAgent-main
Built multiscribe-agent @ file:///F:/software/Multiscribe/MultiscribeAgent-main
Prepared 2 packages in 8.39s
Installed 2 packages in 74ms
 + aiosqlite==0.22.1
 ~ multiscribe-agent==0.1.0 (from file:///F:/software/Multiscribe/MultiscribeAgent-main)
```

锁文件证据：`uv.lock` 含 `aiosqlite==0.22.1` 与 `multiscribe-agent` 的 `>=0.20` 依赖记录；项目虚拟环境导入输出 `0.22.1`。

### 3.2 Ruff

```text
All checks passed!
```

### 3.3 Ruff format

```text
25 files already formatted
```

### 3.4 mypy

```text
Success: no issues found in 17 source files
```

### 3.5 P2 定向测试

```text
..........                                                               [100%]
10 passed in 0.44s
```

### 3.6 全量 pytest

```text
...............................                                          [100%]
31 passed in 0.42s
```

### 3.7 pre-commit

```text
ruff check...............................................................Passed
ruff format..............................................................Passed
mypy.....................................................................Passed
trim trailing whitespace.................................................Passed
fix end of files.........................................................Passed
check yaml...............................................................Passed
check toml...............................................................Passed
check for added large files..............................................Passed
```

说明：当前 Codex runtime 切换后未自带 `uv`，最终 ruff/mypy/pytest/pre-commit 通过项目 `.venv` 中由 `uv sync` 建立的相同工具运行。尝试恢复 runtime 级 uv 被环境策略拒绝，未绕过该限制；锁文件由同步输出、lock diff 和已安装包版本交叉验证。

## 4. 详细任务完成情况

- **T1**：`infra/db.py:12` 定义 Database；`infra/db.py:278` 建表/FTS schema；`infra/db.py:312` 提供 open + schema + running 修复 + FTS 回填的 `init_db`。
- **T2**：`repositories/kv.py:12` JSON 序列化、TTL 时间戳和过期惰性删除。
- **T3**：`repositories/entity_json.py:42` 使用固定 SQL 映射，不把表名拼入 SQL；仅允许 5 张 JSON 表。
- **T4**：`repositories/source_data.py:81` 批量 `INSERT OR IGNORE`，通过 source_data 前后计数排除 FTS trigger 对写入数的影响；查询、日期字段和筛选组合均为静态 SQL。
- **T5/T6**：TaskLog 更新字段先白名单验证再固定 SQL 更新；API key 仅保存 `key_hash` 和元数据，未保存明文 key。
- **T7**：`config.py:127` 注入 domain KvRepository Protocol；`save_settings/load_overrides/get_settings_with_overrides` 完成 KV 覆盖闭环。
- **T8**：10 个异步测试覆盖 schema/FTS/恢复/回填、5 类仓储和配置覆盖。

## 5. 规范符合性自检

- [x] 全量类型注解，mypy strict 通过。
- [x] DB I/O 均为 aiosqlite async 调用；无真实网络。
- [x] SQL 参数值全部绑定；动态对象名由固定 SQL 映射取代。
- [x] TaskLog 更新字段、EntityJson 表名、SourceData 日期字段和筛选组合均有安全边界。
- [x] infra 依赖 domain models/ports，domain 未反向依赖 infra。
- [x] 无硬编码密钥；API key 仓储仅接受 hash 和验证元数据。

## 6. 新增依赖

| 包 | 版本约束 | 用途 |
| :--- | :--- | :--- |
| `aiosqlite` | `>=0.20`，锁定 `0.22.1` | 异步 SQLite 连接与查询 |

## 7. 风险、遗留与取舍

- **取舍**：`source_data_fts` 是独立 FTS 表，不使用 external-content 模式，因为 `ai_summary` 来自 JSON metadata 而非 source_data 列；触发器以共享 rowid 同步。
- **取舍**：`save_batch` 通过 source 表计数差计算实际插入数，避免 SQLite `total_changes` 把 FTS trigger 写入误算到返回值。
- **遗留**：memory/KB 表与 FTS 仅提供 schema/触发器占位，业务查询和领域逻辑留给 P16/P17。
- **风险**：SQLite FTS5 默认 tokenizer 对中文分词能力有限；P16 混合检索阶段需评估 tokenizer/分词策略。
- **未做**：未实现 DB migration framework、向量检索、LLM、Agent 或插件功能。

## 8. BLOCKED 项

无。

## 9. 对后续包的提示

- P3/P5/P6 可通过 `init_db(settings.db_path)` 获取数据库，并复用各仓储实例。
- P2 的 ConfigService 需在应用装配层传入 `KvRepository`，无仓储实例时同步 `get_settings()` 仍只读取默认值/环境。
- SourceDataRepository 的 `get_by_date_range` 支持 `ingestion_date` 和 `published_date`；其他日期字段会拒绝。

## 10. 自评

- 我认为本包满足 `P2-DB与仓储.md` 的完成定义：✅
- Git commit：待本 review 归档后创建。

## 给 ZCode 的判定请求

请按范围合规、验收有据、测试全绿、规范干净、无回归、风险诚实六项标准 review。建议重点复核独立 FTS 表与触发器同步方案，以及 `save_batch` 计数排除 trigger 变化的实现。
