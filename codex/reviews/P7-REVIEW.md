# Review: `P7-Feishu Bot`

**Execution package:** `docs/phases/P7-飞书机器人.md`
**Completed:** 2026-07-16
**Executor:** Codex

## 1. Scope verification

### 1.1 Changed files

| File | Change | Purpose |
| :--- | :--- | :--- |
| `src/multiscribe_agent/plugins/builtin/publishers/__init__.py` | Modified | Exports the built-in Feishu publisher. |
| `src/multiscribe_agent/plugins/builtin/publishers/feishu.py` | Added | Implements signed Feishu custom-bot webhook publishing and retries. |
| `src/multiscribe_agent/renderers/__init__.py` | Added | Exports the renderer public API. |
| `src/multiscribe_agent/renderers/feishu_card.py` | Added | Defines `DigestItem` and Feishu interactive-card/plain-text rendering. |
| `tests/plugins/test_feishu_publisher.py` | Added | Mocked webhook, signing, retry, error, discovery, and opt-in e2e coverage. |
| `tests/renderers/test_feishu_card.py` | Added | Card structure and plain-text fallback coverage. |
| `codex/reviews/P7-REVIEW.md` | Added | Required phase review artifact. |

### 1.2 Whitelist compliance

- [x] All implementation and test files are in the P7 whitelist.
- [x] `codex/reviews/P7-REVIEW.md` is the mandatory execution artifact, following the established `codex/reviews/` convention.
- [x] No dependency change was required: `httpx` was introduced and locked by P6; `respx` is already a development dependency.
- [x] `plugins/base.py` was not changed, no WeCom publisher was introduced, and default tests use only `respx` mocks.

## 2. Acceptance criteria

| # | Criterion | Status | Evidence |
| :--- | :--- | :--- |
| 1 | Feishu signature algorithm is correct. | Pass | `test_publish_text_with_correct_feishu_signature` freezes the timestamp and compares `gen_sign` with a separately calculated HMAC-SHA256/base64 value. `gen_sign` is in `feishu.py`. |
| 2 | Card rendering follows Feishu `header` + `elements` + markdown structure. | Pass | `test_render_digest_card_has_header_markdown_items_and_footer` verifies header, one markdown element per item, link format, and footer; empty/sparse inputs are covered separately. |
| 3 | Webhook POST success, failure, and retry behavior are correct. | Pass | `test_publish_card_without_signature`, `test_publish_retries_after_server_errors`, and `test_publish_raises_after_all_failures` use `respx`; two 500 responses followed by 200 produce success after delays 1s/2s, and persistent failure raises `PublisherError`. |
| 4 | `FeishuPublisher` is automatically registered by discovery. | Pass | `test_feishu_publisher_is_discovered` asserts both the discovered class path and `PublisherRegistry.list_metadata()` metadata. |
| 5 | Full tests pass with no default real-network activity. | Pass | Full suite: `86 passed, 2 deselected`; the real webhook test is explicitly marked `@pytest.mark.e2e` and is deselected by project defaults. |

## 3. Tests and quality gates

Commands were run from the locked project environment. `-p no:cacheprovider` avoids the Windows sandbox permission issue in pytest's cache provider and does not deselect ordinary tests.

### 3.1 `python -m ruff check .`

```text
All checks passed!
```

### 3.2 `python -m ruff format --check .`

```text
71 files already formatted
```

### 3.3 `python -m mypy src`

```text
Success: no issues found in 47 source files
```

### 3.4 P7 targeted tests

```text
........                                                                 [100%]
8 passed, 1 deselected in 0.38s
```

### 3.5 `python -m pytest -q -p no:cacheprovider`

```text
........................................................................ [ 83%]
..............                                                           [100%]
86 passed, 2 deselected in 7.56s
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

- **T1 Card renderer:** `DigestItem` is a frozen slots dataclass with `title`, `summary`, `url`, `source`, and optional score. `render_digest_card` creates a Feishu card with a plain-text header and one markdown element per item; `render_digest_text` provides a readable fallback.
- **T2 FeishuPublisher:** accepts card mappings and text, wraps them in Feishu webhook envelopes, optionally signs with the official timestamp/HMAC/base64 algorithm, posts via `httpx.AsyncClient` with a 10-second timeout, and retries external failures with 1/2/4-second exponential backoff. It recognizes both `StatusCode: 0` and `code: 0` success responses and raises `PublisherError` after retries.
- **T3 Tests:** all HTTP interactions are mocked. Tests cover unsigned card, signed text, retry recovery, final failure, discovery, card boundary cases, text fallback, and an explicit manual-only e2e placeholder.

## 5. Convention compliance

- [x] Public classes and functions have type annotations and docstrings; `mypy src` passes.
- [x] Webhook I/O is asynchronous and uses `httpx.AsyncClient` with a bounded timeout.
- [x] External failures are handled as `httpx.HTTPError` or `PublisherError`; retry logging stores only attempt number and exception type, not webhook or secret values.
- [x] No webhook, secret, token, or other credential is hardcoded, returned, or logged.
- [x] The new renderer has no external dependency; the plugin depends only on existing domain/core/plugin contracts.
- [x] Default unit tests make no real network calls.

## 6. New dependencies

None.

## 7. Risks, follow-ups, and trade-offs

- **Live integration:** a real Feishu webhook e2e is deliberately opt-in and was not run because no webhook/secret was provided and task-package tests must not use the real network. The package recommends a manual card send and screenshot, but it is optional.
- **Retry duration:** persistent failures wait a maximum of 7 seconds before the final fourth attempt (1s + 2s + 4s). This follows the requested exponential schedule and can be made configurable by a future configuration phase.
- **Content contract:** mappings are sent as Feishu interactive cards; strings are sent as Feishu text. Other content types fail fast with `PublisherError`.
- **Not implemented:** WeCom publishing is intentionally deferred to P8; no schedule or digest pipeline integration is included.

## 8. Blocked items

None.

## 9. Notes for later phases

- P8 can reuse the `DigestItem` list and `render_digest_text` output for a Markdown-based publisher.
- P11 can supply curated `DigestItem` values to `render_digest_card`, then fan out the returned card mapping to `FeishuPublisher`.

## 10. Self-assessment

The P7 implementation satisfies the package acceptance criteria with deterministic signing assertions, mocked webhook evidence, discovery coverage, full regression coverage, and zero default real-network calls.
