"""Optional Docker-backed PostgreSQL fixtures for manual integration runs."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL only when explicitly requested with ``INTEGRATION=1``."""
    if os.getenv("INTEGRATION") != "1":
        pytest.skip("set INTEGRATION=1 to run Docker-backed PostgreSQL tests")
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers is unavailable: {exc}")

    manager = PostgresContainer("postgres:16-alpine")
    try:
        container = manager.__enter__()
    except Exception as exc:
        pytest.skip(f"PostgreSQL container is unavailable: {exc}")
    try:
        yield container
    finally:
        manager.__exit__(None, None, None)
