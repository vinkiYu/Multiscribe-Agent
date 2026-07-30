# 执行包：P53-A — upsert 抽象层（dialect.py 扩展 + 4 个最高风险文件迁移）

> **阶段**：后端架构债清理（第 1 包）
> **目标**：dialect.py 新增 upsert 抽象（UpsertStyle 枚举 + render_upsert + _upsert_sql 助手），让 4 个最高风险文件（curation_evaluations / daily_usage / kv / iteration_store）统一走 dialect 端口。其余 9 个硬编码文件标 TODO 后续包处理。
> **依赖**：无。
> **预估**：2 个工作日。

---

## 一、为什么需要这个包

13 个文件硬编码 `ON CONFLICT(...) DO UPDATE SET` SQL（SQLite `?` 占位符形式），当切换到 Postgres 时：
- 占位符需要从 `?` 变成 `$1, $2, ...`（dialect.py 已处理）
- `ON CONFLICT` 语法本身两后端兼容，但 4 个文件直接写 SQL 字符串不做翻译

最危险的：`iteration_store.py` 绕过 mixin 直接调用 `self._db.execute()`，完全不走 dialect。

dialect.py 扩展后，其余 9 个文件只需改 3 行代码（`_upsert_sql()` 调用）即可跨后端。

---

## 二、现状基线（已核实）

| 项 | 位置 | 现状 |
|---|---|---|
| dialect.py | `infra/dialect.py` | 占位符翻译 + `_json_extract()`；零 upsert 抽象 |
| dialect mixin | `DialectRepositoryMixin` | `_execute/_executemany/_fetchone/_fetchall`；零 upsert 助手 |
| 硬编码 upsert | 13 个文件 | 全部写 SQLite `?` 形式，翻译占位符但 upsert SQL 写死 |
| iteration_store | `agents/workflow/iteration_store.py:37` | 直接 `self._db.execute()`，绕过 mixin，危险最高 |

---

## 三、用户已确认的 1 个决策

- **范围**：仅 upsert 抽象层 + 迁移 4 个最高风险文件。其余 9 个标 TODO 后续处理。

---

## 四、任务拆解（3 个子任务）

### T1：P53-A.1 — dialect.py 扩展

**文件**：`src/multiscribe_agent/infra/dialect.py`

#### 新增 `UpsertStyle` 枚举

```python
class UpsertStyle(Enum):
    """Upsert SQL style preference — translated by dialect at runtime."""
    # Both backends:
    ON_CONFLICT_DO_UPDATE = "on_conflict_do_update"
    ON_CONFLICT_DO_NOTHING = "on_conflict_do_nothing"
    # SQLite-only:
    INSERT_OR_REPLACE = "insert_or_replace"
    INSERT_OR_IGNORE = "insert_or_ignore"
```

#### 新增 `upsert_clause()` 纯函数

```python
def upsert_clause(
    style: UpsertStyle,
    conflict_target: tuple[str, ...] | None = None,
    update_columns: tuple[str, ...] | None = None,
) -> str:
    """Build the upsert suffix for the given style.
    
    Args:
        style: Upsert strategy.
        conflict_target: Column(s) to match on conflict (e.g. ("id",) or ("a","b")).
                         None means primary key is used.
        update_columns: Columns to update on conflict. None means all non-PK columns.
    """
    conflict = ", ".join(conflict_target) if conflict_target else ""
    if style == UpsertStyle.ON_CONFLICT_DO_UPDATE:
        update_set = ", ".join(f"{col} = excluded.{col}" for col in (update_columns or ()))
        return f" ON CONFLICT ({conflict}) DO UPDATE SET {update_set}"
    if style == UpsertStyle.ON_CONFLICT_DO_NOTHING:
        return f" ON CONFLICT ({conflict}) DO NOTHING"
    return ""  # fallback: raw INSERT
```

#### `SqlDialect` 新增 `render_upsert()`

```python
@staticmethod
def render_upsert(
    style: UpsertStyle,
    columns: tuple[str, ...],
    conflict_target: tuple[str, ...] | None = None,
    update_columns: tuple[str, ...] | None = None,
) -> str:
    """Render an INSERT...VALUES(...) upsert suffix for SQLite."""
    suffix = upsert_clause(style, conflict_target, update_columns)
    if suffix:
        return suffix
    if style == UpsertStyle.INSERT_OR_REPLACE:
        return " OR REPLACE"
    if style == UpsertStyle.INSERT_OR_IGNORE:
        return " OR IGNORE"
    return ""
```

#### `PgDialect` 新增 `render_upsert()`

```python
@staticmethod
def render_upsert(
    style: UpsertStyle,
    columns: tuple[str, ...],
    conflict_target: tuple[str, ...] | None = None,
    update_columns: tuple[str, ...] | None = None,
) -> str:
    """Render an INSERT...VALUES(...) upsert suffix for PostgreSQL."""
    suffix = upsert_clause(style, conflict_target, update_columns)
    if suffix:
        return suffix
    raise NotImplementedError(
        f"PgDialect.render_upsert: {style.value!r} not supported; "
        "use ON_CONFLICT_DO_UPDATE or ON_CONFLICT_DO_NOTHING"
    )
```

#### `DialectRepositoryMixin` 新增 `_upsert_sql()` 助手

```python
def _upsert_sql(
    self,
    *,
    table: str,
    columns: tuple[str, ...],
    style: UpsertStyle,
    conflict_target: tuple[str, ...] | None = None,
    update_columns: tuple[str, ...] | None = None,
) -> str:
    """Build a fully-dialect-translated INSERT...upsert SQL string.
    
    The returned string uses ? placeholders (to be translated by _execute /
    _executemany automatically) and is ready for the parameter tuple.
    """
    placeholders = ", ".join(["?"] * len(columns))
    col_list = ", ".join(columns)
    suffix = self._dialect.render_upsert(
        style,
        columns=columns,
        conflict_target=conflict_target,
        update_columns=update_columns,
    )
    return f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}){suffix}"
```

### T2：P53-A.2 — 迁移 4 个最高风险文件

#### `src/multiscribe_agent/infra/repositories/curation_evaluations.py`

**当前**（line 79 附近）：直接写 `INSERT INTO curation_evaluations ... ON CONFLICT(workflow_run_id) DO UPDATE SET ...`

**新**：

```python
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, UpsertStyle

async def upsert(self, evaluation: CurationEvaluationRecord) -> None:
    cols = (
        "workflow_run_id", "date", "recorded_at", "rounds", "converged",
        "exit_reason", "final_score", "score_delta", "avg_iter_score",
        "result_count", "usage_json",
    )
    sql = self._upsert_sql(
        table="curation_evaluations",
        columns=cols,
        style=UpsertStyle.ON_CONFLICT_DO_UPDATE,
        conflict_target=("workflow_run_id",),
        update_columns=(
            "date", "recorded_at", "rounds", "converged",
            "exit_reason", "final_score", "score_delta",
            "avg_iter_score", "result_count", "usage_json",
        ),
    )
    params = (
        evaluation.workflow_run_id,
        evaluation.date,
        evaluation.recorded_at,
        evaluation.rounds,
        int(evaluation.converged),
        evaluation.exit_reason,
        evaluation.final_score,
        evaluation.score_delta,
        evaluation.avg_iter_score,
        evaluation.result_count,
        json.dumps(evaluation.usage, ensure_ascii=False, sort_keys=True),
    )
    await self._execute(sql, params)
```

**验收**：该文件内 `grep 'ON CONFLICT'` 不应返回任何匹配。

#### `src/multiscribe_agent/infra/repositories/daily_usage.py`

**新**：

```python
async def upsert(self, date_str: str, usage: dict[str, int]) -> None:
    cols = ("date", "total_tokens", "prompt_tokens", "completion_tokens", "llm_calls")
    sql = self._upsert_sql(
        table="daily_usage",
        columns=cols,
        style=UpsertStyle.ON_CONFLICT_DO_UPDATE,
        conflict_target=("date",),
        update_columns=("total_tokens", "prompt_tokens", "completion_tokens", "llm_calls"),
    )
    await self._execute(sql, (
        date_str,
        usage.get("total_tokens", 0),
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        usage.get("llm_calls", 0),
    ))
```

**验收**：同上。

#### `src/multiscribe_agent/infra/repositories/kv.py`

**新**：

```python
async def set(self, key: str, value: str) -> None:
    cols = ("key", "value", "updated_at")
    sql = self._upsert_sql(
        table="kv",
        columns=cols,
        style=UpsertStyle.ON_CONFLICT_DO_UPDATE,
        conflict_target=("key",),
        update_columns=("value", "updated_at"),
    )
    await self._execute(sql, (key, value, _now_iso()))
```

**验收**：同上。

#### `src/multiscribe_agent/agents/workflow/iteration_store.py`

**当前问题**：`self._db.execute()` 直接调用绕过 mixin。

**新**：改为继承 `DialectRepositoryMixin`：

```python
from multiscribe_agent.infra.dialect import DialectRepositoryMixin, UpsertStyle

class IterationStore(DialectRepositoryMixin):
    def __init__(self, db: DatabaseProtocol) -> None:
        self._db = db

    async def record_round(
        self,
        workflow_run_id: str,
        step_id: str,
        round: int,
        score: float,
        converged: bool,
        reason: str,
        feedback: str,
    ) -> None:
        cols = (
            "workflow_run_id", "step_id", "round",
            "score", "converged", "reason", "feedback", "recorded_at",
        )
        sql = self._upsert_sql(
            table="workflow_iterations",
            columns=cols,
            style=UpsertStyle.ON_CONFLICT_DO_UPDATE,
            conflict_target=("workflow_run_id", "step_id", "round"),
            update_columns=("score", "converged", "reason", "feedback", "recorded_at"),
        )
        params = (
            workflow_run_id, step_id, round,
            score, int(converged), reason, feedback, _now_iso(),
        )
        await self._execute(sql, params)
```

**验收**：
- `grep 'ON CONFLICT' iteration_store.py` 不应返回匹配
- `grep 'self._db.execute' iteration_store.py` 不应返回匹配（替换为 `self._execute`）

### T3：P53-A.3 — 测试覆盖

**新建**：`tests/infra/test_dialect_upsert.py`

```python
"""Tests for dialect.py upsert abstraction layer."""

import pytest
from multiscribe_agent.infra.dialect import (
    SqlDialect, PgDialect, UpsertStyle, upsert_clause, DialectRepositoryMixin,
)
from multiscribe_agent.infra.db import init_db


class TestUpsertClause:
    def test_on_conflict_do_update_with_target(self):
        result = upsert_clause(
            UpsertStyle.ON_CONFLICT_DO_UPDATE,
            conflict_target=("id",),
            update_columns=("name", "value"),
        )
        assert "ON CONFLICT (id) DO UPDATE SET name = excluded.name" in result
        assert "value = excluded.value" in result

    def test_on_conflict_do_nothing(self):
        result = upsert_clause(
            UpsertStyle.ON_CONFLICT_DO_NOTHING,
            conflict_target=("id",),
        )
        assert result == " ON CONFLICT (id) DO NOTHING"

    def test_insert_or_replace_not_supported_by_clause(self):
        # upsert_clause is only for ON CONFLICT styles; OR REPLACE is handled in render_upsert
        assert upsert_clause(UpsertStyle.INSERT_OR_REPLACE) == ""


class TestSqlDialectRenderUpsert:
    def test_on_conflict_do_update(self):
        result = SqlDialect.render_upsert(
            UpsertStyle.ON_CONFLICT_DO_UPDATE,
            columns=("a", "b"),
            conflict_target=("a",),
            update_columns=("b",),
        )
        assert "ON CONFLICT (a) DO UPDATE SET b = excluded.b" in result

    def test_on_conflict_do_nothing(self):
        result = SqlDialect.render_upsert(
            UpsertStyle.ON_CONFLICT_DO_NOTHING,
            columns=("a", "b"),
            conflict_target=("a",),
        )
        assert "ON CONFLICT (a) DO NOTHING" in result

    def test_insert_or_replace(self):
        result = SqlDialect.render_upsert(UpsertStyle.INSERT_OR_REPLACE, columns=("a",))
        assert result == " OR REPLACE"

    def test_insert_or_ignore(self):
        result = SqlDialect.render_upsert(UpsertStyle.INSERT_OR_IGNORE, columns=("a",))
        assert result == " OR IGNORE"


class TestPgDialectRenderUpsert:
    def test_on_conflict_do_update(self):
        result = PgDialect.render_upsert(
            UpsertStyle.ON_CONFLICT_DO_UPDATE,
            columns=("a", "b"),
            conflict_target=("a",),
            update_columns=("b",),
        )
        assert "ON CONFLICT (a) DO UPDATE SET b = excluded.b" in result

    def test_on_conflict_do_nothing(self):
        result = PgDialect.render_upsert(
            UpsertStyle.ON_CONFLICT_DO_NOTHING,
            columns=("a", "b"),
            conflict_target=("a",),
        )
        assert "ON CONFLICT (a) DO NOTHING" in result

    def test_insert_or_replace_raises(self):
        with pytest.raises(NotImplementedError, match="INSERT_OR_REPLACE"):
            PgDialect.render_upsert(UpsertStyle.INSERT_OR_REPLACE, columns=("a",))

    def test_insert_or_ignore_raises(self):
        with pytest.raises(NotImplementedError, match="INSERT_OR_IGNORE"):
            PgDialect.render_upsert(UpsertStyle.INSERT_OR_IGNORE, columns=("a",))


@pytest.mark.asyncio
class TestCurationEvaluationsViaMixin:
    async def test_upsert_is_idempotent(self):
        db = await init_db(":memory:")
        try:
            from multiscribe_agent.infra.repositories.curation_evaluations import (
                CurationEvaluationRepository,
            )
            from multiscribe_agent.domain.models import CurationEvaluationRecord
            repo = CurationEvaluationRepository(db)
            record = CurationEvaluationRecord(
                workflow_run_id="run-1",
                date="2026-07-01",
                recorded_at=1234567890,
                rounds=3,
                converged=True,
                exit_reason="threshold",
                final_score=8.0,
                score_delta=1.5,
                avg_iter_score=7.5,
                result_count=12,
                usage={},
            )
            await repo.upsert(record)
            await repo.upsert(record)  # same key — idempotent
            results = await repo.query()
            assert len(results) == 1
        finally:
            await db.close()


@pytest.mark.asyncio
class TestIterationStoreViaMixin:
    async def test_record_round_is_idempotent(self):
        db = await init_db(":memory:")
        try:
            from multiscribe_agent.agents.workflow.iteration_store import IterationStore
            store = IterationStore(db)
            await store.record_round("run-1", "step-1", 1, 7.0, False, "reason", "feedback")
            await store.record_round("run-1", "step-1", 1, 8.0, True, "reason2", "feedback2")
            latest = await store.resume_loop("run-1", "step-1")
            assert latest is not None
            assert latest.score == 8.0
        finally:
            await db.close()
```

---

## 五、白名单与黑名单

### 白名单（可改/新增，共 7 个）

```
src/multiscribe_agent/infra/dialect.py                          [T1: 新增 UpsertStyle + upsert_clause + render_upsert + _upsert_sql]
src/multiscribe_agent/infra/repositories/curation_evaluations.py  [T2: 走 _upsert_sql]
src/multiscribe_agent/infra/repositories/daily_usage.py          [T2: 走 _upsert_sql]
src/multiscribe_agent/infra/repositories/kv.py                  [T2: 走 _upsert_sql]
src/multiscribe_agent/agents/workflow/iteration_store.py         [T2: 继承 mixin + 走 _upsert_sql]
tests/infra/test_dialect_upsert.py                              [T3: 新增]
tests/infra/test_repositories.py                                [T3: 既有测试（如需补回归断言）]
docs/phases/P53-A-upsert抽象.md                                  [本任务包]
```

### 黑名单（禁止改动）

- `infra/repositories/source_data.py`（标 TODO）
- `infra/repositories/entity_json.py`（标 TODO）
- `memory/repositories/memory_entries.py`（标 TODO）
- `memory/repositories/memory_categories.py`（标 TODO）
- `core/adapter_health.py`（标 TODO）
- `core/daily_digest_archive.py`（标 TODO）
- `core/publish_history.py`（标 TODO）
- `core/pushed_content.py`（标 TODO）
- `knowledge/vector_store.py`（标 TODO）
- `infra/db.py` schema DDL
- `infra/postgres_driver.py`
- `frontend/`（本包不涉及前端）

---

## 六、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | `dialect.py` 有 `UpsertStyle` 枚举 | `grep UpsertStyle dialect.py` |
| 2 | `dialect.py` 有 `upsert_clause()` 函数 | `grep upsert_clause dialect.py` |
| 3 | `SqlDialect.render_upsert()` 覆盖 4 种 style | 函数测试 |
| 4 | `PgDialect.render_upsert()` 覆盖 2 种 style，不支持 OR REPLACE/OR IGNORE | 函数测试 |
| 5 | `DialectRepositoryMixin._upsert_sql()` 存在 | `grep _upsert_sql dialect.py` |
| 6 | `curation_evaluations.py` 无字面 `ON CONFLICT` | `grep 'ON CONFLICT' curation_evaluations.py` 无结果 |
| 7 | `daily_usage.py` 无字面 `ON CONFLICT` | 同上 |
| 8 | `kv.py` 无字面 `ON CONFLICT` | 同上 |
| 9 | `iteration_store.py` 无字面 `ON CONFLICT` | 同上 |
| 10 | `iteration_store.py` 无 `self._db.execute`（替换为 `self._execute`）| `grep 'self._db.execute' iteration_store.py` 无结果 |
| 11 | `test_dialect_upsert.py` 全部测试通过 | pytest 输出 |
| 12 | `test_curation_evaluations.py` 3 测试通过 | pytest 输出 |
| 13 | `test_daily_usage_repo.py` 2 测试通过 | pytest 输出 |
| 14 | `test_loop_persistence.py` 通过 | pytest 输出 |
| 15 | 全量 pytest + ruff + mypy 通过（无回归）| 输出 |

---

## 七、测试与质量门

```bash
.venv\Scripts\python.exe -m pytest tests/infra/test_dialect_upsert.py -v
.venv\Scripts\python.exe -m pytest tests/infra/repositories/ -v
.venv\Scripts\python.exe -m pytest tests/agents/workflow/test_loop_persistence.py -v
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p53a
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy src
```

---

## 八、完成定义

- [ ] 白名单 7 个文件全部创建/修改
- [ ] 15 条验收条件全部通过
- [ ] 4 个文件全部走 `_upsert_sql()`，无字面 `ON CONFLICT`
- [ ] `iteration_store.py` 继承 `DialectRepositoryMixin`
- [ ] dialect.py 可被其余 9 个文件直接复用（仅标 TODO，不强制本包迁移）
- [ ] 全量 pytest 零回归
- [ ] `codex/reviews/P53-A-REVIEW.md` 填写完毕

---

## 九、风险与取舍

1. **9 个文件未迁移**：当前全部走 SQLite，**运行无影响**。Codex review 中列出 TODO 清单。
2. **`PgDialect.render_upsert` 抛 NotImplementedError**：fail-fast，不静默错误。
3. **column 顺序**：调用方需确保 `update_columns` 与 params 顺序一致（助手只管 SQL 生成，不管参数）。
4. **`iteration_store` 的 `_now_iso()`**：需确认该函数在文件内已存在或引入。

---

## 十、文件清单

```
src/multiscribe_agent/infra/dialect.py                          [修改: T1]
src/multiscribe_agent/infra/repositories/curation_evaluations.py  [修改: T2]
src/multiscribe_agent/infra/repositories/daily_usage.py          [修改: T2]
src/multiscribe_agent/infra/repositories/kv.py                  [修改: T2]
src/multiscribe_agent/agents/workflow/iteration_store.py        [修改: T2]
tests/infra/test_dialect_upsert.py                              [新增: T3]
tests/infra/test_repositories.py                                [修改: T3（如需）]
docs/phases/P53-A-upsert抽象.md                                [新增: 本任务包]
```