# Review: P33 — Loop 续跑 `run_id` 复用修复

**执行包**：`docs/phases/P33-Loop续跑run_id复用修复.md`
**完成日期**：2026-07-30
**执行者**：Codex
**结论**：通过，建议交 ZCode 复审

## 1. 范围核对

本阶段修改了任务包白名单内的 4 个源文件和 3 个测试文件：

| 文件 | 变更 |
| --- | --- |
| `src/multiscribe_agent/services/scheduler.py` | 派生 `task.id:run_date`，向新回调传递 `run_id`，兼容旧单参数回调 |
| `src/multiscribe_agent/bootstrap.py` | 接收调度器 `run_id`，解析日期并传入每日流水线 |
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | `run`/`stream`/注册回调支持 `workflow_run_id` 透传 |
| `src/multiscribe_agent/agents/workflow/engine.py` | `run`/`stream` 支持可选 `run_id`，使用其作为 trace/checkpoint key |
| `tests/services/test_scheduler.py` | 调度器确定性 ID 测试 |
| `tests/agents/pipelines/test_daily_digest.py` | 流水线 ID 透传测试 |
| `tests/agents/workflow/test_engine_loop_persistence.py` | supplied UUID fallback 与跨调用续跑测试 |

未修改任务包黑名单中的 `loop_node.py`、`iteration_store.py`、数据库 schema、领域模型、Executor、API 或 Provider 文件。工作区原有的 `codex/reviews/P32-REVIEW.md` 修改未纳入本阶段提交。

## 2. 验收条件

| # | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | 同一 `(task_id, run_date)` 两次调度得到同一 `run_id` | 通过 | `scheduler.py:181`；`test_scheduler_passes_deterministic_run_id`（`test_scheduler.py:78`） |
| 2 | `run_daily_digest_task(..., run_id=...)` 透传到 `pipeline.run(workflow_run_id=...)` | 通过 | `bootstrap.py:533-560`；Pipeline 接收及返回 ID 的 `test_pipeline_run_accepts_workflow_run_id`（`test_daily_digest.py:1028`） |
| 3 | supplied `run_id` 成为所有 workflow event 的 trace ID | 通过 | `engine.py:81`；`test_engine_stream_uses_supplied_run_id`（`test_engine_loop_persistence.py:98`） |
| 4 | 未提供 `run_id` 时仍回退 `uuid4().hex` | 通过 | `engine.py:81`；`test_engine_stream_falls_back_to_uuid_when_no_run_id`（`test_engine_loop_persistence.py:111`） |
| 5 | 模拟崩溃后同日同 ID 从 round 1 checkpoint 续跑到 round 3 | 通过 | `test_deterministic_run_id_resumes_across_invocations`（`test_engine_loop_persistence.py:123`）断言两次 stream、三条持久化记录及最终 `third` |
| 6 | 原有硬编码 `run-1` Loop 持久化测试无回归 | 通过 | `tests/agents/workflow/test_loop_persistence.py` 定向测试通过 |
| 7 | 全量 pytest、ruff、format、mypy 通过 | 通过 | 见第 3 节原始输出 |

## 3. 测试与质量门

### P33 定向套件

```text
58 passed in 2.45s
```

命令：

```text
.venv\Scripts\python.exe -m pytest tests/services/test_scheduler.py tests/services/test_scheduler_usage_persistence.py tests/agents/pipelines/test_daily_digest.py tests/agents/workflow/test_engine_loop_persistence.py tests/agents/workflow/test_loop_persistence.py -q -p no:cacheprovider --basetemp .pytest-tmp-p33-final-target
```

### Ruff

```text
All checks passed!
```

命令：`.venv\Scripts\python.exe -m ruff check src tests`

### Format

```text
353 files already formatted
```

命令：`.venv\Scripts\python.exe -m ruff format --check src tests`

### Mypy

```text
Success: no issues found in 182 source files
```

命令：`.venv\Scripts\python.exe -m mypy src`

### 全量测试

使用本地模型缓存离线运行：

```text
592 passed, 6 deselected, 1 warning in 61.32s (0:01:01)
```

命令：

```text
$env:HF_HUB_OFFLINE='1'; .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p33-final-full
```

唯一 warning 为依赖侧 `StarletteDeprecationWarning`（Starlette TestClient 与 httpx 的兼容提示），与本阶段改动无关。测试进程结束时偶发的 OTel console exporter closed-stream traceback 也不改变 pytest 退出码和断言结果。

## 4. 实现摘要

调度器沿用已有的 UTC 日期锁键，派生 `f"{task.id}:{run_date}"` 并以关键字参数传给回调。Bootstrap 和每日资讯流水线继续传递该 ID，WorkflowEngine 使用 supplied ID 作为本次 stream 的 trace ID；Loop 节点因此用相同 `(workflow_run_id, step_id)` 查询并追加 checkpoint。直调 Engine/Pipeline 不传 ID 时仍生成随机 UUID，保持旧行为。为避免现有 CLI 和第三方扩展回调因签名升级立即失败，调度器在新回调上发送 `run_id`，检测到旧单参数回调时回退为原调用形式。

## 5. 风险与取舍

- 同一任务跨 UTC 日期会生成不同 ID，因此不会跨天续跑；这是每日 digest 的预期隔离语义。
- 仅修复 Loop checkpoint 的 run ID 复用；DAG 已完成 step 的结果和 ReAct AgentExecutor 状态仍不续跑，按任务包约束留待后续阶段。
- `run_id` 没有写入 `task_logs`，可由 `task.id` 与 UTC 日期重新派生，避免 schema 迁移。
- 调度器保留旧单参数回调兼容路径，意味着未升级的扩展不会获得续跑能力，但不会被本阶段直接打断。

## 6. 自评

本阶段满足白名单、确定性 ID 透传、UUID 回退、Loop 跨调用续跑和全量质量门要求，结论为**通过**，等待 ZCode 复审。
