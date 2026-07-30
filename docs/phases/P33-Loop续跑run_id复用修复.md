# 执行包：P33 — Loop 续跑 run_id 复用修复

> **阶段**：阶段五（架构债清理 / 方向 1 加固）
> **目标**：让 `workflow_run_id` 在调度层变为确定性派生值 `(task_id:run_date)`，使崩溃后同日重跑能真正读取旧 checkpoint 并续跑 Loop，而非每次生成新 uuid4 导致 checkpoint 变孤儿。
> **依赖**：P31.2（已通过）、P32（已通过）。
> **预估**：1 个工作日。
> **来源**：方向 1（多轮 LLM 自评估 Loop + 断点续跑）探查发现的核心暗坑。

---

## 一、根因（经代码核实，2026-07-30）

```
scheduler.execute_task(task)           # 有稳定 (task.id, run_date)，但只 callback(task)
  └─ run_daily_digest_task(task)       # 不传 run_date/run_id
      └─ pipeline.run()                # run_date 默认 None，无 run_id
          └─ engine.stream(...)        # del date；trace_id = uuid4().hex（line 78）
              └─ _execute_step(...)    # workflow_run_id=trace_id（line 173，新 uuid）
                  └─ execute_loop_step # list_for_step(NEW_UUID) → 空 → 不续跑
```

**关键证据**：
- `engine.py:78` `trace_id = uuid4().hex`（每次 stream() 新生成）
- `engine.py:173` `workflow_run_id=trace_id`（同一个随机 uuid 当持久化 key）
- `engine.py:74` `del date`（传入的 date 参数被丢弃，从不影响 trace_id）
- `scheduler.py:134-135` 已有 `run_date` + `lock_key = f"...:{task.id}:{run_date}"`（**已有确定性派生先例**）
- `scheduler.py:170` `callback(task)` 只传 task，不传 run_date
- 现有续跑测试 `test_loop_persistence.py` 硬编码 `workflow_run_id="run-1"`，生产引擎从不复现

---

## 二、用户已确认的 2 个决策

1. **run_id 派生方式**：`f"{task.id}:{run_date}"`（确定性派生，与 Redis 锁 key 同源）。同日崩溃重跑 → 同一 id → 续跑成功；跨日重跑 → 不同 id → 从头跑（合理）。
2. **engine.run_id 参数可选**：`run_id: str | None = None`，不传则 `uuid4().hex` 回退。直调 pipeline.run() 的测试/手动脚本零回归。

---

## 三、任务拆解（1 个子任务，5 处改动点）

### T1：P33.1 — 透传确定性 run_id 从调度器到 iteration_store

改动按调用链自顶向下（4 个源文件 + 3 个测试，全部白名单内）：

| # | 文件 | 行 | 改动 |
|---|---|---|---|
| 1 | `src/multiscribe_agent/services/scheduler.py` | 26 | `TaskCallback` 类型加 `*, run_id: str` 关键字参数 |
| 2 | `src/multiscribe_agent/services/scheduler.py` | 134-170 | `execute_task` 内计算 `run_id = f"{task.id}:{run_date}"`（复用已有 run_date）；`callback(task, run_id=run_id)` |
| 3 | `src/multiscribe_agent/bootstrap.py` | 533-557 | `run_daily_digest_task(self, task, *, run_id: str)`；从 run_id 解析 run_date（`run_id.split(":", 1)[1]`）传给 `pipeline.run(run_date=..., workflow_run_id=run_id)` |
| 4 | `src/multiscribe_agent/agents/pipelines/daily_digest.py` | 358,363,365,367 | `run(self, *, run_date=None, workflow_run_id=None)`；传 `run_id=workflow_run_id` 给 `engine.stream`；若传入则用它初始化 `workflow_run_id` 变量（而非等 `event.trace_id` 覆盖）|
| 5 | `src/multiscribe_agent/agents/workflow/engine.py` | 43-70,78 | `run()`/`stream()` 加 `run_id: str \| None = None`；`trace_id = run_id or uuid4().hex`（line 78）；删除 `del date` |

**关键约束**：
- `loop_node.py` **无需改动**——它已正确消费 `workflow_run_id`（resume line 76-78，append line 116-128）
- `iteration_store.py` **无需改动**——key 已是 `workflow_run_id`
- engine `date` 参数保留（pipeline 仍传 `date_value`），只是不再被 `del` 浪费

**回退语义**：
- 调度器路径：传确定性 `run_id = f"{task.id}:{run_date}"` → 续跑生效
- 直调 `pipeline.run()`（测试/手动）：`workflow_run_id=None` → engine `uuid4().hex` → 现有行为不变

---

## 四、白名单与黑名单

### 白名单（可改文件，共 8 个）

```
src/multiscribe_agent/services/scheduler.py              [T1: execute_task + TaskCallback]
src/multiscribe_agent/bootstrap.py                       [T1: run_daily_digest_task]
src/multiscribe_agent/agents/pipelines/daily_digest.py   [T1: run() + stream()]
src/multiscribe_agent/agents/workflow/engine.py          [T1: stream()/run() + trace_id]
tests/services/test_scheduler.py                         [T1: 回调签名测试]
tests/agents/pipelines/test_daily_digest.py              [T1: run_id 透传测试]
tests/agents/workflow/test_engine_loop_persistence.py    [T1: 确定性 run_id 续跑测试]
docs/phases/P33-Loop续跑run_id复用修复.md                 [本任务包文档]
```

### 黑名单（禁止改动）

- `src/multiscribe_agent/agents/workflow/loop_node.py`（不改 execute_loop_step，它已正确消费 workflow_run_id）
- `src/multiscribe_agent/agents/workflow/iteration_store.py`（不改存储，key 已是 workflow_run_id）
- `src/multiscribe_agent/infra/db.py`（不加列；task_logs 不持久化 workflow_run_id——按用户决策选派生而非持久化方案）
- `src/multiscribe_agent/domain/models.py`（不改 ScheduleTask/TaskLog 模型）
- `src/multiscribe_agent/agents/executor.py`、`reflector.py`、`context.py`、`llm/providers/`、`api/`、`frontend/`

---

## 五、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | 同一 `(task_id, run_date)` 两次 execute_task → 同一 `run_id` | `test_scheduler_passes_deterministic_run_id` |
| 2 | `run_daily_digest_task(task, run_id=...)` 把 run_id 透传到 `pipeline.run(workflow_run_id=...)` | `test_pipeline_run_accepts_workflow_run_id` |
| 3 | `engine.stream(..., run_id="X")` 时 `event.trace_id == "X"`（不再 uuid4）| `test_engine_stream_uses_supplied_run_id` |
| 4 | `engine.stream(..., run_id=None)` 时回退 uuid4（现有行为不变）| `test_engine_stream_falls_back_to_uuid_when_no_run_id` |
| 5 | 模拟崩溃+同日重跑：第一次写入 round 1 checkpoint，第二次用同一 run_id 续跑到 round 3 | `test_deterministic_run_id_resumes_across_invocations` |
| 6 | 现有 `test_loop_persistence.py`（硬编码 run-1）仍通过（无回归）| 原始测试输出 |
| 7 | 全量 pytest + ruff + mypy 通过 | 原始输出 |

---

## 六、测试与质量门

```bash
.venv\Scripts\python.exe -m pytest \
    tests/services/test_scheduler.py \
    tests/agents/pipelines/test_daily_digest.py \
    tests/agents/workflow/test_engine_loop_persistence.py \
    tests/agents/workflow/test_loop_persistence.py \
    -v -p no:cacheprovider --basetemp .pytest-tmp-p33

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m ruff format --check src tests
.venv\Scripts\python.exe -m mypy src
```

---

## 七、完成定义

- [ ] 白名单文件全部修改 + 文档创建
- [ ] 7 条验收条件全部通过
- [ ] 全量 pytest 无回归（预期 587 + ~5 新测试）
- [ ] ruff / mypy 全绿
- [ ] `codex/reviews/P33-REVIEW.md` 填写完毕

---

## 八、风险与取舍

1. **跨日续跑不生效**：`run_date` 来自 `datetime.now(UTC)`，跨日重跑会得到不同 run_id → 不续跑。这是预期行为（新的一天 = 新的 digest），且与现有 Redis 锁 key 同源逻辑一致。
2. **TaskCallback 签名变更的爆炸半径**：所有注册的回调都要加 `run_id` 关键字参数。当前只有 `run_daily_digest_task` 一个生产回调；测试里的 fake 回调需更新。改为关键字参数（`*, run_id: str`）使旧的位置参数调用仍兼容。
3. **engine 的 `date` 参数**：目前被 `del date` 丢弃。本包保留该参数（pipeline 仍传 date_value），只是不再 del——未来可用于 run 报告。不删除避免无关改动。
4. **直调 pipeline.run() 的兼容**：`workflow_run_id=None` 默认 → engine uuid4 回退 → 现有测试/手动脚本零回归。
5. **DAG 级续跑仍缺失**：本包只修复 Loop 级续跑（`execute_loop_step` 的 resume）。DAG 级（ingest→dedupe 不重跑）和 ReAct AgentExecutor 级续跑不在本包——那是更大的工程，需 step_results 持久化，单独排期。
6. **不持久化到 task_logs**：按用户决策选派生方案而非加列方案。task_logs 无 workflow_run_id 列，但调度器每次算出的 run_id 可从 (task_id, run_date) 重现，无需查表。

---

## 九、文件清单

```
src/multiscribe_agent/services/scheduler.py              [修改: T1]
src/multiscribe_agent/bootstrap.py                       [修改: T1]
src/multiscribe_agent/agents/pipelines/daily_digest.py   [修改: T1]
src/multiscribe_agent/agents/workflow/engine.py          [修改: T1]
tests/services/test_scheduler.py                         [修改: T1]
tests/agents/pipelines/test_daily_digest.py              [修改: T1]
tests/agents/workflow/test_engine_loop_persistence.py    [修改: T1]
docs/phases/P33-Loop续跑run_id复用修复.md                 [本任务包文档]
```