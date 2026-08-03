# Review: P54-D-Loop 续跑链路加固

**执行包**：`docs/phases/P54-D-Loop续跑链路加固.md`
**完成日期**：2026-08-03
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件清单

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `tests/agents/workflow/test_iteration_store_postgres.py` | 新增 | 捕获 PostgreSQL 方言 SQL，覆盖三元组冲突键、步骤查询和跨步骤续跑查询 |
| `tests/agents/workflow/test_iteration_store_sorting.py` | 新增 | 固化 epoch 时间戳的 `list_recent` 最新优先排序语义 |
| `src/multiscribe_agent/agents/workflow/loop_node.py` | 修改 | 仅为 `_iteration_from_record` 增加 `delta/usage` 不持久化的已知限制说明 |

### 1.2 白名单合规性

✅ 实际 P54-D 改动仅涉及任务包白名单内的两个新测试文件和 `loop_node.py` 注释。
✅ 未修改任务包黑名单中的 `iteration_store.py`、`engine.py`、`infra/db.py`、PostgreSQL schema 或 `_iteration_from_record` 逻辑。
✅ 工作树中已有其他历史阶段修改均未被本阶段暂存或提交。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `append` 在 PG 下生成三元组 `ON CONFLICT` 与 `$1..$8` | ✅ | `test_append_translates_to_postgres_upsert_with_triple_conflict_target`；定向测试 `4 passed` |
| 2 | `list_for_step` 使用 `$1/$2` 与 `ORDER BY round ASC` | ✅ | `test_list_for_step_translates_to_postgres_parameterized_query` |
| 3 | `resume_loop` 使用最新 checkpoint 查询 | ✅ | `test_resume_loop_translates_to_postgres_latest_checkpoint_query` |
| 4 | SQLite epoch 时间戳按最新优先排序 | ✅ | `test_list_recent_orders_by_epoch_timestamp_newest_first`；使用 `1722681600/01/02` 三个等宽 epoch 值 |
| 5 | `_iteration_from_record` 注释说明 `delta/usage` 丢失限制 | ✅ | `src/multiscribe_agent/agents/workflow/loop_node.py` docstring；未改恢复逻辑 |
| 6 | 既有 SQLite Loop 续跑测试无回归 | ✅ | `tests/agents/workflow/test_loop_persistence.py`、`test_engine_loop_persistence.py` 包含在排除前端静态测试的全量回归中 |
| 7 | ruff + mypy 通过 | ✅ | 第 3 节原始输出 |

## 3. 测试与质量门

### 3.1 定向 P54-D 测试

执行：

```text
.\.venv\Scripts\python.exe -m pytest tests/agents/workflow/test_iteration_store_postgres.py tests/agents/workflow/test_iteration_store_sorting.py -q -p no:cacheprovider
```

输出：

```text
....                                                                     [100%]
4 passed in 0.28s
```

### 3.2 `ruff check .`

```text
All checks passed!
```

### 3.3 `ruff format --check .`

```text
381 files already formatted
```

### 3.4 `mypy src`

```text
Success: no issues found in 192 source files
```

### 3.5 原始全量 pytest

执行：

```text
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

结果：

```text
FAILED tests/api/test_frontend_static.py::test_frontend_index_is_served_at_root
1 failed, 657 passed, 6 deselected, 1 warning in 37.85s
```

失败是既有前端静态页标题断言仍期待 `Multiscribe · 智能采集`，实际构建 HTML 不含该旧标题；该文件不在 P54-D 白名单且与 Loop 续跑无关。

排除该历史失败后的回归：

```text
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --ignore tests/api/test_frontend_static.py
653 passed, 6 deselected, 1 warning in 37.57s
```

警告为 Starlette 对 `httpx` TestClient 的 deprecation warning，不影响本阶段功能。

## 4. 详细任务完成情况

- **T1 PG SQL 捕获**：使用 `PlaceholderStyle.DOLLAR` 的本地 capture fake，验证 `IterationStore.append` 的三列冲突目标、全部八个 `$n` 参数、更新列，以及 `list_for_step`/`resume_loop` 的参数化查询和排序。
- **T2 排序固化**：插入三条跨秒 epoch 值，覆盖 `recorded_at` 后调用 `list_recent(limit=3)`，断言 run-2、run-1、run-0 顺序；注释说明当前 SQLite INTEGER affinity 与历史 epoch 文本的兼容语义。
- **T3 限制文档化**：在 `_iteration_from_record` docstring 中明确持久化表不保存历史 `delta/usage`，但下一轮 delta 从恢复的 score 重算，退出分类仍正确。

## 5. 规范符合性自检

- ✅ 新增测试和注释具备完整类型注解、模块/函数 docstring。
- ✅ 测试只使用内存 SQLite 与本地 SQL capture fake，无真实 PostgreSQL、LLM 或网络调用。
- ✅ 未新增依赖，未修改运行时 SQL、schema 或 Loop 行为。
- ✅ ruff、format、mypy 均通过。

## 6. 新增依赖

无。未修改 `pyproject.toml` 或 `uv.lock`。

## 7. 风险、遗留与取舍

- **历史 `delta/usage` 不恢复**：这是任务包明确接受的限制。当前轮 delta 会依据上一轮恢复 score 重算；如未来要做精确收敛曲线或成本回放，需要扩展 `workflow_iterations` 字段和迁移。
- **PG capture 不是实库集成测试**：它验证 DialectRepositoryMixin 输出的 SQL 文本和参数编号，不验证真实 PostgreSQL 执行；真 PG 环境仍需单独集成测试。
- **时间戳类型依赖**：当前 SQLite 表声明为 INTEGER，PostgreSQL 为 DOUBLE PRECISION；测试固化等宽 epoch 值的排序行为，未改变 schema。若未来改为变长文本或混合格式，必须重新定义排序策略。
- **未修复前端静态标题测试**：该问题超出 P54-D 白名单，保留为既有工作树风险。

## 8. BLOCKED 项

无。P54-D 的测试和文档任务已完成；全量 pytest 的唯一失败属于既有前端静态标题断言，已明确记录且不影响本阶段验收。

## 9. 对后续包的提示

- 后续若接入 Loop 运营趋势图，不应把恢复后的历史 `delta/usage` 当成完整审计数据；当前只能依赖每轮 `score` 和总用量记录。
- 若要把 PostgreSQL capture 升级为真集成测试，可复用本阶段三元组冲突键断言，并在 CI 增加 PostgreSQL service。

## 10. 自评

我认为本包满足 P54-D 的完成定义：✅。运行时逻辑保持不变，SQLite 续跑回归、PostgreSQL 方言 SQL 和排序隐式依赖均有测试证据；静态质量门全绿，剩余全量测试失败为已知、越界的前端标题断言。
