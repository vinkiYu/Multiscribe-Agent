# Review: P45 - Public Digest Click Tracking and Preference Feedback

**Execution date:** 2026-07-29
**Executor:** Codex
**Status:** Implemented and locally committed; not pushed

## 1. Scope

| File | Change |
| --- | --- |
| `src/multiscribe_agent/infra/db.py` | Added the `click_events` table and two indexes; wired migration into `init_db`. |
| `src/multiscribe_agent/core/click_events.py` | Added JSON-tag click persistence and date-window aggregation with malformed-row tolerance. |
| `src/multiscribe_agent/api/routes/track_click.py` | Added public `GET /api/track-click`, request metadata capture, HTTP(S) validation, and 302 redirect. |
| `src/multiscribe_agent/app.py` | Registered the public tracking router. |
| `src/multiscribe_agent/services/preference_feedback.py` | Added bounded click-tag merging that preserves the complete manual preference object. |
| `src/multiscribe_agent/bootstrap.py` | Created one shared `ClickEventRepository`, `PreferenceStore`, and feedback service in `ServiceContext`. |
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | Applies click feedback once before each digest workflow run and passes it through executor-created pipelines. |
| `frontend/src/daily-news.tsx` | Article links now go through the tracker while retaining the original URL and item metadata. |
| `tests/core/test_click_events.py` | Schema, JSON normalization, time-window, threshold, and malformed JSON coverage. |
| `tests/api/test_track_click.py` | Public 302, missing URL, and unsafe scheme coverage. |
| `tests/services/test_preference_feedback.py` | Manual ordering, full-field preservation, max-tag bound, and no-op save coverage. |

The existing user edits in `frontend/src/daily-news.tsx` and `src/multiscribe_agent/agents/pipelines/daily_digest.py` were retained. Unrelated worktree files (`docs/phases/README.md`, CSS, `.idea/`, archives, and the deleted root logo) were not staged.

## 2. Acceptance Evidence

| Requirement | Result | Evidence |
| --- | --- | --- |
| `click_events` has required columns and indexes | PASS | `tests/core/test_click_events.py::test_record_persists_json_tags_and_metadata` checks `PRAGMA table_info` and `PRAGMA index_list`. |
| Event tags are JSON and duplicate/blank tags are normalized | PASS | Same repository test; `_normalize_tags` de-duplicates per click. |
| Aggregation is date-windowed and supports `min_clicks` | PASS | `test_tag_click_counts_filters_window_and_minimum`; filtering uses `clicked_at >= since_dateT00:00:00`. |
| Invalid legacy JSON does not break feedback | PASS | `test_tag_click_counts_ignores_invalid_json_and_empty_tags`. |
| Public endpoint records and redirects without authentication | PASS | `tests/api/test_track_click.py::test_track_click_records_and_redirects_without_auth` returned HTTP 302 and the original `Location`. |
| Missing target returns 400 and unsafe schemes are rejected | PASS | `test_track_click_requires_item_url` and `test_track_click_rejects_non_http_urls`. |
| Manual preferences remain first and other fields are preserved | PASS | `test_click_feedback_preserves_manual_fields_and_orders_tags`. |
| Click tags are ranked, deduplicated, bounded, and saves are idempotent | PASS | `test_click_feedback_is_bounded_and_skips_unchanged_save`. |
| Feedback is applied before curation | PASS | `DailyDigestPipeline.run()` invokes `apply_click_feedback` before building the workflow engine; bootstrap injects the shared service. |
| Frontend preserves source URL while tracking metadata | PASS | `daily-news.tsx` builds `${API_BASE}/track-click` with encoded date, URL, source, and tags; frontend build passed. |

## 3. Test and Quality Gates

### Targeted P45 tests

```text
8 passed in 0.71s
```

Command:

```text
.venv\Scripts\python.exe -m pytest tests/core/test_click_events.py tests/api/test_track_click.py tests/services/test_preference_feedback.py -q -p no:cacheprovider --basetemp .pytest-tmp-p45-final
```

### Full Python suite

```text
492 passed, 4 deselected, 1 warning in 21.35s
```

The run used `HF_HUB_OFFLINE=1` as documented for this repository. The single warning is the existing Starlette/httpx deprecation warning from the installed test dependency.

### Static checks

```text
.venv\Scripts\python.exe -m ruff check .
All checks passed!

.venv\Scripts\python.exe -m ruff format --check .
319 files already formatted

.venv\Scripts\python.exe -m mypy src
Success: no issues found in 169 source files
```

### Frontend build

```text
npm run build
vite ...
✓ built in 3.21s
```

Vite emitted existing offline Google Fonts resolution notices; the production bundle was generated successfully.

## 4. Risks and Deliberate Trade-offs

- Click events are anonymous and aggregate by tag, so this phase does not provide per-user preference isolation. A multi-user deployment needs an explicit privacy-safe user/session dimension in a later phase.
- Public GET tracking can receive bot or crawler traffic. `User-Agent` is retained for later filtering, and `min_clicks` is available, but bot classification and click decay are intentionally out of scope.
- Feedback only appends click-derived tags and never removes manual tags or other preference fields. It has no negative feedback signal or time-decay weighting yet.
- Redirects accept only absolute `http` and `https` URLs, preventing obvious `javascript:`/`file:` open redirects. The original URL is intentionally not rewritten or fetched by the server.
- The tracker receives metadata in a query string, so very large tag sets would increase URL length. The current digest item tag lists are bounded by existing item serialization; a POST/beacon endpoint can be added if that contract changes.

## 5. Commit

Local commit created after verification:

```text
feat(feedback): track public digest clicks and feed preferences
```

The commit was not pushed to GitHub.
