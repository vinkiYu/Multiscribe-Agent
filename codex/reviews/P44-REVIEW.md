# Review: P44-DatabaseProtocol 抽象

执行包：`docs/phases/P44-DatabaseProtocol抽象.md`  
完成日期：2026-07-29  
执行者：Codex

## 1. 范围核对

本阶段实际修改均在 P44 白名单内：

| 文件 | 变更 |
| --- | --- |
| `src/multiscribe_agent/infra/db_protocol.py` | 新增运行时可检查的 `DatabaseProtocol` |
| `src/multiscribe_agent/infra/db.py` | 重命名为 `SqliteDatabase`、保留 `Database` 别名、返回 Mapping 行包装器 |
| `src/multiscribe_agent/infra/repositories/source_data.py` | row 类型改为 `Mapping[str, Any]` |
| `src/multiscribe_agent/infra/repositories/task_log.py` | row 类型改为 `Mapping[str, Any]` |
| `src/multiscribe_agent/infra/repositories/api_key.py` | row 类型改为 `Mapping[str, Any]` |
| `src/multiscribe_agent/core/adapter_health.py` | row 类型改为 `Mapping[str, Any]` |
| `src/multiscribe_agent/core/daily_digest_archive.py` | row 类型改为 `Mapping[str, Any]` |
| `src/multiscribe_agent/core/publish_history.py` | row 类型改为 `Mapping[str, Any]` |
| `tests/infra/test_db_protocol.py` | 新增别名、运行时协议和真实 SQLite Mapping 测试 |

任务包黑名单未修改；工作区原有的 `daily_digest.py`、前端日报文件、Logo 删除、UI/压缩包等用户改动均未纳入提交。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | `DatabaseProtocol` 定义 execute/executemany/fetchone/fetchall/close/set_audit_logger | PASS | `infra/db_protocol.py:12-35`；协议测试通过 |
| 2 | Protocol 的 fetchone 返回 `Mapping[str, Any] \| None`，fetchall 返回 Mapping 列表 | PASS | `db_protocol.py:21-31`；mypy 通过 |
| 3 | `SqliteDatabase` 满足运行时 Protocol | PASS | `tests/infra/test_db_protocol.py:13-18`，`isinstance(..., DatabaseProtocol)` 通过 |
| 4 | `Database = SqliteDatabase` 向后兼容别名存在 | PASS | `infra/db.py:755`；别名断言通过 |
| 5 | 六个仓储/核心转换函数使用 `Mapping[str, Any]` | PASS | source_data:213、task_log:99、api_key:84、adapter_health:147、daily_digest_archive:180、publish_history:143 |
| 6 | 六个文件不再 import/标注 `aiosqlite.Row` | PASS | `rg -n "aiosqlite\\.Row|import aiosqlite" src/multiscribe_agent` 过滤 db.py/connection_pool.py 后零命中 |
| 7 | SQLite 专属 FTS/jieba 逻辑不进入 Protocol | PASS | hooks 仍在 `SqliteDatabase` 实现内；Protocol 文件仅含通用 CRUD |
| 8 | 现有数据库/仓储行为无回归 | PASS | P44 定向 18 passed；全量 484 passed |
| 9 | ruff 与 mypy 通过 | PASS | 第 3 节原始输出 |
| 10 | 仅类型/边界抽象，无业务逻辑变更 | PASS | 六个转换函数方法体未改；新增的 SQLite 行包装器仅保留列名和旧序号访问兼容 |

## 3. 测试与质量门禁

### P44 定向测试

```text
.venv\Scripts\python.exe -m pytest tests/infra/test_db_protocol.py tests/infra -q -p no:cacheprovider --basetemp .pytest-tmp-p44
..................                                                       [100%]
18 passed in 0.98s
```

### 全量非 e2e 回归

首次未设置离线模型环境时，知识库测试触发 `sentence_transformers` 下载 HuggingFace 模型并等待网络；faulthandler 定位为 `huggingface_hub.file_download`，不是数据库代码。随后使用离线模式完成可复现回归：

```text
$env:HF_HUB_OFFLINE='1'; .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p44-full-offline-2
484 passed, 4 deselected, 1 warning in 20.20s
```

离线模式只让可选向量能力快速降级，SQLite/FTS 测试仍完整执行。

### ruff

```text
.venv\Scripts\python.exe -m ruff check .
All checks passed!
```

```text
.venv\Scripts\python.exe -m ruff format --check .
313 files already formatted
```

### mypy

```text
.venv\Scripts\python.exe -m mypy src
Success: no issues found in 166 source files
```

## 4. 实现说明与风险

- `SqliteDatabase` 内部把 `aiosqlite.Row` 转成 `_SqliteRowMapping`，它是标准 `Mapping`，同时保留历史 `row[0]` 访问，避免未在本阶段白名单内的旧代码出现行为回归。
- 对外 `fetchone`/`fetchall` 的声明已经是 `Mapping[str, Any]`，Protocol 不暴露 `aiosqlite` 类型；SQLite 的连接、迁移、`lastrowid` 和 FTS/jieba hooks 仍是实现细节。
- `Database` 别名保证现有约 20 处 import 无需大规模重构；Postgres 阶段可新增另一个 `DatabaseProtocol` 实现并逐步替换注入类型。
- 本阶段没有引入 `asyncpg`、Postgres 配置、Alembic 或 FTS5 到 `tsvector` 的迁移；这些属于后续 Postgres 阶段。
- 协议目前是基础 CRUD 边界，SQLite 专属 `connection`、`migrate_*` 和 `lastrowid` 尚未抽象；这是任务包明确保留的 Phase 0 取舍。

## 5. BLOCKED

无。联网模型下载造成的首次测试等待已通过离线降级方式解决，不影响本阶段验收。

## 6. 后续建议

下一阶段新增 `PostgresDatabase(DatabaseProtocol)` 时，应让服务构造函数逐步依赖 `DatabaseProtocol`，并为事务、参数占位符、分页和迁移生命周期定义第二层协议；SQLite 的 FTS/jieba wrapper 不应复用到 Postgres。

## 7. 自评

P44 白名单实现、协议测试、类型去耦和质量门禁均完成，建议提交规划层复审。
