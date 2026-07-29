# Review: P46 - Loop Iteration Persistence Wiring

**Execution date:** 2026-07-29
**Executor:** Codex
**Status:** Implemented and locally committed; not pushed

## 1. Scope

| File | Change |
| --- | --- |
| `src/multiscribe_agent/agents/workflow/engine.py` | Added optional `IterationStore` injection and forwarded `workflow_run_id=trace_id` plus the store to `execute_loop_step`. |
| `src/multiscribe_agent/agents/workflow/iteration_store.py` | Added bounded `list_recent(limit)` ordered by `recorded_at DESC, round DESC`. |
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | Added optional store injection and passed it to each per-run `WorkflowEngine`. |
| `src/multiscribe_agent/bootstrap.py` | Created one database-backed `IterationStore` and injected it into the generic and daily-digest engines. |
| `src/multiscribe_agent/api/routes/workflow_iterations.py` | Added authenticated GET API for run+step history and recent cross-run records, including score deltas. |
| `src/multiscribe_agent/app.py` | Registered the iteration read router. |
| `tests/agents/workflow/test_engine_loop_persistence.py` | Added production engine wiring, resume, no-store compatibility, and recent-order tests. |
| `tests/api/test_workflow_iterations_routes.py` | Added authenticated filtering/recent-list API coverage. |

The existing P45 changes and unrelated worktree edits were preserved. No blacklisted files (`loop_node.py`, protocols, DB schema, services, LLM, config, or frontend) were changed for P46.

## 2. Acceptance Evidence

| # | Acceptance condition | Result | Evidence |
| --- | --- | --- | --- |
| 1 | `WorkflowEngine.__init__` accepts optional `iteration_store` | PASS | `engine.py:30-41`. |
| 2 | Loop execution receives `workflow_run_id=trace_id` and the store | PASS | `engine.py:163-175`. |
| 3 | Injected engine writes `workflow_iterations` rows | PASS | `test_engine_persists_loop_rounds_and_same_run_resumes`; persisted rounds `[1, 2, 3]`. |
| 4 | `iteration_store=None` preserves existing behavior | PASS | `test_engine_without_iteration_store_keeps_existing_behavior`; final output is returned and DB count remains zero. |
| 5 | Same run ID resumes from the latest round | PASS | Same test invokes the engine execution boundary twice with `run-1`; executor is called three times total and history is rounds `[1, 2, 3]`. |
| 6 | `list_recent(limit)` returns newest records and is bounded | PASS | `test_iteration_store_list_recent_is_bounded_and_newest_first`; deterministic timestamps return `run-2`, `run-1` for limit 2. |
| 7 | `GET ...?run_id&step_id` returns that step history | PASS | `test_workflow_iterations_route_filters_run_and_step`; rounds and score delta are asserted. |
| 8 | `GET ...?limit` returns recent records across runs | PASS | `test_workflow_iterations_route_lists_recent_and_requires_auth`; limit 2 and both run IDs are asserted. |
| 9 | Daily digest production composition injects the store | PASS | `bootstrap.py:281`, `bootstrap.py:375-380`, `bootstrap.py:505-523`, and `daily_digest.py:269-284, 372-380`. |
| 10 | Full tests and quality gates pass | PASS | See Section 3. |

The read API is authenticated consistently with the existing dashboard, workflow, adapter-health, and publish-history APIs. It exposes `workflow_run_id`, `step_id`, `round`, `output`, `score`, `delta`, `feedback`, `converged`, and `reason`; run+step responses derive absolute score deltas from adjacent persisted scores because the existing schema does not store a separate delta column.

## 3. Test and Quality Gates

### P46 targeted tests

```text
6 passed in 0.61s
```

Command:

```text
.venv\Scripts\python.exe -m pytest tests/agents/workflow/test_engine_loop_persistence.py tests/agents/workflow/test_loop_persistence.py tests/api/test_workflow_iterations_routes.py -v -p no:cacheprovider --basetemp .pytest-tmp-p46-final
```

### Daily digest and workflow regression

```text
45 passed in 1.19s
```

An existing OpenTelemetry test teardown emitted a non-failing `I/O operation on closed file` exporter message; the test process exited successfully.

### Full Python suite

```text
497 passed, 4 deselected, 1 warning in 34.44s
```

The run used `HF_HUB_OFFLINE=1` to avoid optional model downloads. The one warning is the existing Starlette/httpx deprecation warning from the installed test dependency.

### Static checks

```text
.venv\Scripts\python.exe -m ruff check .
All checks passed!

.venv\Scripts\python.exe -m ruff format --check .
322 files already formatted

.venv\Scripts\python.exe -m mypy src
Success: no issues found in 170 source files
```

## 4. Risks and Deliberate Trade-offs

- `trace_id` is reused as `workflow_run_id`, exactly as specified. A future change to trace semantics or task-log correlation must update both contracts together.
- This phase persists Loop rounds only. It does not persist all DAG step outputs, so cross-process crash recovery of an entire workflow remains out of scope.
- Iteration rows accumulate indefinitely. The current bounded loop limits per-run growth; TTL/retention cleanup is deferred.
- The API returns bounded Loop output already truncated by `IterationStore.append` to 8,000 characters; full prompt/context recovery is intentionally not provided by this phase.
- Recent records are authenticated but not paginated beyond the bounded `limit` (1-100); a future dashboard can add cursor pagination if the table grows substantially.

## 5. Commit

Local commit created after verification:

```text
feat(workflow): persist loop iterations in production engine
```

The commit was not pushed to GitHub.
