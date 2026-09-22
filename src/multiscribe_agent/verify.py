"""Unified local verification gate: ruff lint + format check + mypy + pytest.

`uv run verify` is the single entry point for the repository's full local
quality gate. It represents what is verifiable in a normal dev environment;
it does NOT stand in for staging or production acceptance.

Exit code: 0 when every step passes; 1 on the first failing step.

Known scope exclusions (documented debt, not silent skips):

- ``ruff check`` gates ``src`` only. ``scripts/`` carries lint debt (E501 on
  long Chinese rationale strings in P57-era one-off eval tooling).
- ``pytest`` excludes ``tests/api``. Six tests there fail for pre-existing
  reasons unrelated to code under test: ``test_frontend_static.py`` (4) mounts
  the removed ``frontend/dist`` (app.py `_mount_frontend` needs a decision on
  how the migrated prototype is served); ``test_settings.py`` (2) depends on
  the operator's local ``.env`` overrides.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# pytest wipes ``--basetemp`` at session start; under Windows that rmtree
# intermittently fails on a polluted in-repo directory (file locks, long
# paths) and kills every tmp_path test at setup (observed: 86 setup errors).
# Use a short OS-temp location and pre-clean with errors ignored so the
# session always starts from a fresh, writable directory.
_BASETEMP = Path(tempfile.gettempdir()) / "ms-verify-tmp"

# Hermetic test env: loading sentence-transformers triggers an online
# HuggingFace revision check that hangs on networks where HF is unreachable
# (observed: test_api_kb froze >45s at KB ingestion). The model is cached
# locally; offline flags force cache-only loads. Haystack telemetry pings an
# external endpoint as well.
_OFFLINE_ENV: dict[str, str] = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HAYSTACK_TELEMETRY_ENABLED": "false",
}

STEPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ruff check src", (sys.executable, "-m", "ruff", "check", "src")),
    (
        "ruff format --check src tests",
        (sys.executable, "-m", "ruff", "format", "--check", "src", "tests"),
    ),
    ("mypy src", (sys.executable, "-m", "mypy", "src")),
    (
        "pytest (hermetic scope)",
        (
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--ignore=tests/api",
            f"--basetemp={_BASETEMP}",
            "-q",
        ),
    ),
)


def main() -> int:
    """Run each gate in order, stopping at the first failure."""
    shutil.rmtree(_BASETEMP, ignore_errors=True)
    env = {**os.environ, **_OFFLINE_ENV}
    for name, command in STEPS:
        print(f"\n=== verify: {name} ===", flush=True)
        completed = subprocess.run(command, env=env)  # noqa: S603 - fixed argv, no shell
        if completed.returncode != 0:
            print(f"\nverify FAILED at: {name}", flush=True)
            return 1
        print(f"=== verify PASS: {name} ===", flush=True)
    print("\nverify: ALL GREEN", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
