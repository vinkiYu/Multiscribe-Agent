# Review: `P6-RSS Adapter`

**Execution package:** `docs/phases/P6-RSS适配器.md`
**Completed:** 2026-07-16
**Executor:** Codex

## 1. Scope verification

### 1.1 Changed files

| File | Change | Purpose |
| :--- | :--- | :--- |
| `.pre-commit-config.yaml` | Modified | Makes the isolated mypy hook install the two new runtime dependencies. |
| `pyproject.toml` | Modified | Adds `feedparser>=6.0` and `httpx>=0.27`. |
| `uv.lock` | Modified | Locks `feedparser==6.0.12` and its `sgmllib3k` dependency. |
| `src/multiscribe_agent/plugins/builtin/adapters/__init__.py` | Modified | Exports `RSSAdapter` from the built-in adapter package. |
| `src/multiscribe_agent/plugins/builtin/adapters/rss.py` | Added | Implements asynchronous RSS/Atom retrieval and normalization. |
| `src/multiscribe_agent/services/__init__.py` | Added | Exports the ingestion application service. |
| `src/multiscribe_agent/services/ingestion.py` | Added | Coordinates adapter retrieval, source persistence, and task logging. |
| `tests/fixtures/hackernews.xml` | Added | Local RSS fixture. |
| `tests/fixtures/sample_feed.xml` | Added | Local Atom fixture. |
| `tests/plugins/test_rss_adapter.py` | Added | Mocked RSS adapter, discovery, and network-containment coverage. |
| `tests/services/test_ingestion.py` | Added | Ingestion, task-log, deduplication, and failure-isolation coverage. |
| `codex/reviews/P6-REVIEW.md` | Added | Required phase review artifact. |

### 1.2 Whitelist compliance

- [x] All implementation and test changes are in the P6 whitelist.
- [x] `.pre-commit-config.yaml` was changed only because the new runtime dependencies must be available to the isolated mypy hook, as required by `EXEC_PROMPT.md`.
- [x] `uv.lock` is committed with the dependency change.
- [x] `codex/reviews/P6-REVIEW.md` is the mandatory review artifact and follows the existing `codex/reviews/` convention.
- [x] `plugins/base.py`, `plugins/registry.py`, `plugins/discovery.py`, other adapters, and publishers were not changed.

## 2. Acceptance criteria

| # | Criterion | Status | Evidence |
| :--- | :--- | :--- | :--- |
| 1 | Fixture RSS/Atom feeds map to complete `UnifiedData` with normalized publication dates. | Pass | `test_fetch_transform_and_fetch_and_transform` and `test_transform_atom_updated_date_is_normalized`; mapping is in `rss.py:66-147`. |
| 2 | Network errors are contained and produce an empty list rather than an exception. | Pass | `test_network_failure_returns_empty_from_template_method` uses `respx` to raise `httpx.ConnectError`; `RSSAdapter.fetch` wraps `httpx.HTTPError` as `AdapterError` at `rss.py:57-64`, then the existing base template contains it. |
| 3 | `IngestionService.run_single` and `run_all` persist items, complete task logs, deduplicate, and isolate failures. | Pass | `test_run_single_persists_and_deduplicates_with_complete_task_log` and `test_run_all_continues_after_adapter_error`; orchestration is in `ingestion.py:35-110`. |
| 4 | RSS adapter is automatically registered by discovery. | Pass | `test_rss_adapter_is_discovered` asserts the discovered class and `AdapterRegistry.list_metadata()` entry; package export is in `adapters/__init__.py:3-5`. |
| 5 | Default tests make no real network call. | Pass | RSS tests use local XML fixtures and `respx`; the live-feed slot is explicitly marked `@pytest.mark.e2e` and is deselected by the project default. |

## 3. Tests and quality gates

The final commands use `uv run --no-sync` against the locked environment. `-p no:cacheprovider` avoids a Windows sandbox permission issue in pytest's cache provider; it does not deselect any tests. Ruff reported Windows access warnings while traversing sandbox-restricted cache paths, but both Ruff commands exited successfully with their normal pass result.

### 3.1 `uv run --no-sync ruff check .`

```text
warning: Encountered error: Access is denied. (os error 5)
warning: Encountered error: Access is denied. (os error 5)
warning: Encountered error: Access is denied. (os error 5)
warning: Encountered error: Access is denied. (os error 5)
All checks passed!
```

### 3.2 `uv run --no-sync ruff format --check .`

```text
error: Encountered error: Access is denied. (os error 5)
error: Encountered error: Access is denied. (os error 5)
error: Encountered error: Access is denied. (os error 5)
error: Encountered error: Access is denied. (os error 5)
66 files already formatted
```

### 3.3 `uv run --no-sync mypy src`

```text
Success: no issues found in 44 source files
```

### 3.4 `uv run --no-sync pytest -q -p no:cacheprovider`

```text
........................................................................ [ 92%]
......                                                                   [100%]
78 passed, 1 deselected in 8.03s
```

### 3.5 `uv run --no-sync pytest tests/plugins/test_rss_adapter.py tests/services/test_ingestion.py -q -p no:cacheprovider`

```text
......                                                                   [100%]
6 passed, 1 deselected in 0.14s
```

### 3.6 `pre-commit run --all-files`

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

## 4. Detailed task completion

- **T1 RSSAdapter:** `RSSAdapter` uses `httpx.AsyncClient` with a 30-second timeout and optional proxy, parses RSS/Atom with `feedparser`, and emits `UnifiedData`. It prioritizes `guid`, `link`, then `id`; truncates summaries to 300 characters; maps tags; and normalizes parsed timestamps to UTC ISO 8601. See `rss.py:21-174`.
- **T2 IngestionService:** `run_single` creates or restarts a running `TaskLog`, invokes `fetch_and_transform`, writes via `save_batch`, and records success/error outcome, result count, end time, and duration. `run_all` accepts `adapter_id` or `id`, supports nested `config`, skips disabled entries, and continues after a failed adapter. See `ingestion.py:21-122`.
- **T3 Tests:** two local XML fixtures cover RSS and Atom parsing. Adapter tests use mocked HTTP only; service tests use in-memory repository ports and adapter fakes to verify task logs, deduplication, and failure isolation.

## 5. Convention compliance

- [x] Production public classes and methods have type annotations and docstrings; `mypy src` passes.
- [x] Network I/O uses `async def` and `httpx.AsyncClient`.
- [x] HTTP failures are caught as concrete `httpx.HTTPError` in the adapter; service-level errors are isolated per adapter and logged without configuration contents.
- [x] No token, secret, password, cookie, or webhook is hardcoded or logged.
- [x] The domain layer remains free of external dependencies; the service depends on domain ports and plugin registry only.
- [x] Unit tests use local fixtures and `respx`; no real network request ran.

## 6. New dependencies

| Package | Constraint | Use |
| :--- | :--- | :--- |
| `feedparser` | `>=6.0` | Parse standard RSS and Atom feeds. |
| `httpx` | `>=0.27` | Asynchronous HTTP retrieval with timeout and proxy support. |

## 7. Risks, follow-ups, and trade-offs

- **Typing risk:** `feedparser` provides no type stubs. `rss.py:9` uses one scoped `# type: ignore[import-untyped]` with the reason documented; all local parsing boundaries validate runtime values.
- **Configuration shape:** `run_all` accepts `adapter_id` or `id` and an optional nested `config`; callers should use one of those explicit shapes.
- **Live-feed verification:** the real-RSS test is deliberately manual `e2e` and was not run because P6 default tests must use no real network. A configured live URL remains necessary for an operator-run e2e verification.
- **Not implemented:** no Follow/GitHub/AI-search adapters and no publisher implementation were added; they are outside P6.

## 8. Blocked items

None.

## 9. Notes for later phases

- P11 can reuse `IngestionService.run_all` for configured collection steps using `{adapter_id, config, enabled}` entries.
- Live RSS execution requires a separate configuration source for `rss_url`; this phase intentionally does not add configuration persistence or scheduling.

## 10. Self-assessment

The P6 implementation satisfies the task package acceptance criteria with fixture-backed adapter-to-repository test evidence and no default real-network activity.
