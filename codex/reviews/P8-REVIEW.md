# Review: `P8-Enterprise WeCom Bot`

**Execution package:** `docs/phases/P8-企业微信机器人.md`
**Completed:** 2026-07-16
**Executor:** Codex

## 1. Scope verification

| File | Change | Purpose |
| :--- | :--- | :--- |
| `src/multiscribe_agent/plugins/builtin/publishers/wecom.py` | Added | Enterprise WeCom webhook publisher. |
| `src/multiscribe_agent/renderers/wecom_markdown.py` | Added | WeCom-compatible Markdown and plain-text rendering. |
| `tests/plugins/test_wecom_publisher.py` | Added | Mocked URL, payload, retry, error, discovery, and e2e-marker coverage. |
| `tests/renderers/test_wecom_markdown.py` | Added | Markdown structure, truncation, and fallback tests. |
| `codex/reviews/P8-REVIEW.md` | Added | Required phase review artifact. |

- [x] Functional source and test changes are all within the P8 whitelist.
- [x] The review file is the mandatory execution artifact under the established `codex/reviews/` convention.
- [x] `plugins/base.py` and `feishu.py` were not modified; no AES callback implementation or real webhook unit test was added.

## 2. Acceptance criteria

| # | Criterion | Status | Evidence |
| :--- | :--- | :--- |
| 1 | Markdown uses only compatible WeCom constructs. | Pass | `test_render_digest_markdown_uses_supported_heading_quote_and_links` asserts heading, bold, quote, and link output, with no base64/table syntax. |
| 2 | Full webhook URL and key-only configuration are correct. | Pass | `test_publish_accepts_full_webhook_and_markdown` and `test_publish_accepts_key_only_and_text_fallback` target the exact normalized URL. |
| 3 | Success, WeCom error code, and retry behavior work. | Pass | `test_publish_retries_and_surfaces_wecom_error` verifies 500 recovery and final `errcode` failure with `errmsg`; code retries using 1/2/4-second backoff. |
| 4 | Publisher is automatically discovered. | Pass | `test_wecom_publisher_is_discovered` checks discovery result and `PublisherRegistry` metadata. |
| 5 | Full tests pass with no default real network. | Pass | Full suite: `93 passed, 3 deselected`; real webhook test is `@pytest.mark.e2e`. |

## 3. Tests and quality gates

### 3.1 `python -m ruff check .`
```text
All checks passed!
```

### 3.2 `python -m ruff format --check .`
```text
75 files already formatted
```

### 3.3 `python -m mypy src`
```text
Success: no issues found in 49 source files
```

### 3.4 P8 targeted tests
```text
.......                                                                  [100%]
7 passed, 1 deselected in 0.28s
```

### 3.5 `python -m pytest -q -p no:cacheprovider`
```text
........................................................................ [ 77%]
.....................                                                    [100%]
93 passed, 3 deselected in 7.53s
```

### 3.6 `pre-commit run --all-files`
```text
Recorded by the commit hook after staging this review.
```

## 4. Detailed task completion

- **T1:** `wecom_markdown.py` reuses P7 `DigestItem`, produces heading/bold/quote/link Markdown only, bounds one summary at 300 characters with `...`, and provides plain-text fallback.
- **T2:** `WeComPublisher` accepts full URL or key-only webhook configuration, posts Markdown by default and text on explicit option, validates `errcode == 0`, and raises `PublisherError` after exponential retries. The rate-limit ownership is documented as P11 caller responsibility.
- **T3:** All HTTP calls use `respx`; no real webhook is exercised. Tests cover renderer boundaries, URL forms, payloads, response failures, retry recovery, discovery, and manual-only e2e marker.

## 5. Convention compliance

- [x] Type annotations, docstrings, strict mypy, and Ruff pass.
- [x] HTTP is asynchronous `httpx.AsyncClient` with 10-second timeout.
- [x] Retry logs contain only attempt number and error type, never webhook content or configuration.
- [x] No credential is hardcoded; real e2e remains opt-in.

## 6. New dependencies

None.

## 7. Risks and follow-ups

- Real WeCom e2e was not run because no webhook key was supplied; it is deliberately opt-in.
- The 300-character summary limit follows P6's existing content bound; it prevents an individual item from dominating one bot message.
- Publisher-side rate limiting is deliberately deferred to P11 fan-out scheduling; WeCom's 20-message-per-minute limit is documented in the publisher docstring.
- AES-encrypted callback support and non-text/Markdown message types remain outside MVP scope.

## 8. Blocked items

None.

## 9. Notes for later phases

P11 can render the same `DigestItem` list through `render_digest_markdown` and pass it to `WeComPublisher` with its configured webhook key.

## 10. Self-assessment

P8 satisfies the package acceptance criteria with mocked WeCom protocol evidence, full regression coverage, and zero default real-network calls.
