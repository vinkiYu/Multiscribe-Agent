# Review: `P9-Scheduler`

**Execution package:** `docs/phases/P9-调度器.md`
**Completed:** 2026-07-17
**Executor:** Codex

## 1. Scope verification

| File | Change | Purpose |
| :--- | :--- | :--- |
| `pyproject.toml` | Modified | Adds APScheduler 3.x. |
| `uv.lock` | Modified | Locks APScheduler and timezone dependencies. |
| `src/multiscribe_agent/services/__init__.py` | Modified | Exports scheduler service APIs. |
| `src/multiscribe_agent/services/scheduler.py` | Added | Cron scheduling, callback injection, hot reload, and task logs. |
| `tests/services/test_scheduler.py` | Added | Scheduler lifecycle, callback, error, reload, and cron validation tests. |
| `codex/reviews/P9-REVIEW.md` | Added | Required phase review artifact. |

- [x] All functional changes are in the P9 whitelist; the review is the required artifact.
- [x] `ingestion.py` and all daily-digest execution logic remain unchanged.

## 2. Acceptance criteria

| # | Criterion | Status | Evidence |
| :--- | :--- | :--- |
| 1 | start/stop/register/unregister/reload/run_now work. | Pass | `test_register_run_now_and_unregister_create_complete_log` and `test_errors_missing_executor_reload_and_invalid_cron_are_isolated`. |
| 2 | Task logs contain lifecycle fields. | Pass | `execute_task` creates `running`, then updates end time, duration, status, result count, and message; success assertions cover result count. |
| 3 | Callback failures do not stop scheduler. | Pass | Failing callback produces error log; subsequent reload and invalid-cron assertion proceed. |
| 4 | TaskExecutorRegistry dispatches by task type. | Pass | Tests register `daily_digest` executor, start from persisted task, and call `run_now`. |
| 5 | Invalid cron does not register. | Pass | Invalid cron raises before adding job in the test. |
| 6 | Full suite passes. | Pass | `95 passed, 3 deselected`. |

## 3. Tests and quality gates

```text
python -m pytest tests/services/test_scheduler.py -q -p no:cacheprovider
2 passed in 0.26s

python -m ruff check .
All checks passed!

python -m ruff format --check .
77 files already formatted

python -m mypy src
Success: no issues found in 50 source files

python -m pytest -q -p no:cacheprovider
........................................................................ [ 75%]
.......................                                                  [100%]
95 passed, 3 deselected in 9.07s
```

## 4. Implementation

- `TaskExecutorRegistry` maps task type to injected async callback, leaving P11 to provide `daily_digest` behavior.
- `SchedulerService` uses `AsyncIOScheduler` and `CronTrigger.from_crontab`, loads persisted schedules, supports reload and immediate execution, and stores jobs only in memory.
- Every callback execution records `TaskLog` running/success/error lifecycle. APScheduler 3.x has no type markers, so `scheduler.py` scopes mypy's `import-untyped` disable to that module only.

## 5. Risks and follow-ups

- APScheduler jobs are intentionally in-memory; persisted state is the `schedules` entity store and reload restores configured jobs.
- P11 must register its `daily_digest` executor before `start()` or call `register()` for a concrete task.
- No business execution logic, rate limiting, or daily-digest workflow was added.

## 6. Blocked items

None.

## 7. Self-assessment

P9 meets its task package definition with callback-injection separation, task-log evidence, cron validation, and full regression coverage.
