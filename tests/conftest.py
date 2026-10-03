"""Repository-wide PostgreSQL test configuration."""

from __future__ import annotations

import pytest

from tests.db import get_test_database_url


@pytest.fixture
def test_database_url() -> str:
    """Return the local TEST_DATABASE_URL or the lazily managed PG container DSN."""
    return get_test_database_url()
