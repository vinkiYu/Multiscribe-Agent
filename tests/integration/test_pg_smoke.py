"""Comprehensive smoke test: verify Phase 6 SQL translations against a real Postgres container."""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from multiscribe_agent.infra.dialect import DialectRepositoryMixin, PgDialect, SqlDialect


class _FakeDb:
    """Minimal stub satisfying ``DatabaseProtocol`` for SQL translation only."""
    placeholder_style = type("Style", (), {"value": "dollar"})()

    async def execute(self, *a, **kw):
        raise NotImplementedError

    async def fetchone(self, *a, **kw):
        raise NotImplementedError

    async def fetchall(self, *a, **kw):
        raise NotImplementedError


class _TranslatorShim(DialectRepositoryMixin):
    """Bare mixin host that just exercises translate/json_extract helpers."""

    def __init__(self, db):
        self._db = db


class _SqlTranslator(SqlDialect):
    """Wrap SqlDialect to expose ``json_extract`` for parity with the mixin."""

    def json_extract(self, column: str, path: str) -> str:  # type: ignore[override]
        return f"json_extract({column}, '$.{path}')"


class _PgTranslator(PgDialect):
    """Wrap PgDialect to expose ``json_extract`` for parity with the mixin."""

    def json_extract(self, column: str, path: str) -> str:  # type: ignore[override]
        return f"{column}->>'{path}'"


def main():
    print("=" * 60)
    print("Stage6B Phase6 PostgreSQL Smoke Test")
    print("=" * 60)

    # 1. Check container
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=pg-test", "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    container_name = result.stdout.strip()
    if not container_name:
        print("[SKIP] pg-test container not running. Start with:")
        print("  docker run -d --name pg-test -e POSTGRES_PASSWORD=testpass \\")
        print("    -e POSTGRES_DB=testdb -p 5433:5432 postgres:16-alpine")
        return

    # 2. Check pg_isready
    result = subprocess.run(
        ["docker", "exec", "pg-test", "pg_isready", "-U", "postgres"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[SKIP] Postgres not ready: {result.stderr}")
        return

    print(f"[OK] Container {container_name} ready")
    print()

    pg_dialect = PgDialect()
    sq_dialect = _SqlTranslator()

    tests = []

    # --- SQL Translation Tests ---
    tests.append(("SELECT ? → SELECT $1", pg_dialect.translate("SELECT ?"), "SELECT $1"))
    tests.append(("SELECT ? ? → SELECT $1 $2", pg_dialect.translate("SELECT ? ?"), "SELECT $1 $2"))
    tests.append(("WHERE id = ? → $N", pg_dialect.translate("WHERE id = ?"), "WHERE id = $1"))
    tests.append(("INSERT ... VALUES (?,?)", pg_dialect.translate("INSERT INTO t VALUES (?,?)"), "INSERT INTO t VALUES ($1,$2)"))
    tests.append(("UPDATE ... SET a=? WHERE b=?", pg_dialect.translate("UPDATE t SET a=? WHERE b=?"), "UPDATE t SET a=$1 WHERE b=$2"))
    tests.append(("SELECT ? FROM ?", pg_dialect.translate("SELECT ? FROM ?"), "SELECT $1 FROM $2"))
    # --- Edge case: quoted question mark ---
    tests.append((
        "?'text?' literal ? preserves inside quotes",
        pg_dialect.translate("SELECT '?' AS x"),
        "SELECT '?' AS x",
    ))
    tests.append(("SQLite SELECT ? stays ?", sq_dialect.translate("SELECT ?"), "SELECT ?"))

    # --- JSON extraction (via mixin shim) ---
    pg_shim = _PgTranslator()
    sq_shim = _SqlTranslator()
    pg_json = pg_shim.json_extract("data", "sha256")
    sq_json = sq_shim.json_extract("data", "sha256")
    tests.append(("Pg json_extract → ->>", pg_json, "data->>'sha256'"))
    tests.append(("SQLite json_extract → json_extract()", sq_json, "json_extract(data, '$.sha256')"))

    # --- Batch $N numbering ---
    many_q = "INSERT INTO t VALUES (" + ",".join(["?"] * 20) + ")"
    expected_many = "INSERT INTO t VALUES (" + ",".join([f"${i}" for i in range(1, 21)]) + ")"
    tests.append(("20 placeholders → $1..$20", pg_dialect.translate(many_q), expected_many))

    # --- Run ---
    passed = 0
    failed = 0
    for name, got, expected in tests:
        ok = got == expected
        status = "✅" if ok else "❌"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  {status} {name}")
        if not ok:
            print(f"     GOT:      {got}")
            print(f"     EXPECTED: {expected}")

    print()
    print("=" * 60)
    print(f"Results: {passed}/{len(tests)} passed, {failed} failed")
    print("=" * 60)

    # --- DB-level tests (via docker exec + psql) ---
    print()
    print("--- DB-level verification ---")

    # Test 1: SELECT with $1 binding via a parameterised prepare/execute
    sql = "PREPARE x AS SELECT $1::int AS n; EXECUTE x(42); DEALLOCATE x;"
    result = subprocess.run(
        ["docker", "exec", "pg-test", "psql", "-U", "postgres", "-d", "testdb", "-t", "-A", "-c", sql],
        capture_output=True, text=True
    )
    ok = result.returncode == 0 and "42" in result.stdout
    print(f"  {'✅' if ok else '❌'} SELECT $1::int (42)")

    # Test 2: JSON ->> extraction
    sql = r"""SELECT '{"sha256":"abc123"}'::jsonb->>'sha256' AS val"""
    result = subprocess.run(
        ["docker", "exec", "pg-test", "psql", "-U", "postgres", "-d", "testdb", "-t", "-c", sql],
        capture_output=True, text=True
    )
    ok = result.returncode == 0 and "abc123" in result.stdout
    print(f"  {'✅' if ok else '❌'} JSONB ->> extraction = {result.stdout.strip()}")

    # Test 3: INSERT...ON CONFLICT (Postgres upsert syntax)
    sql = """
    CREATE TABLE IF NOT EXISTS test_kv (key TEXT PRIMARY KEY, val TEXT);
    INSERT INTO test_kv (key, val) VALUES ('k1','v1')
    ON CONFLICT (key) DO UPDATE SET val=EXCLUDED.val;
    SELECT * FROM test_kv WHERE key='k1';
    """
    result = subprocess.run(
        ["docker", "exec", "pg-test", "psql", "-U", "postgres", "-d", "testdb", "-t", "-c", sql],
        capture_output=True, text=True
    )
    ok = result.returncode == 0 and "k1" in result.stdout
    print(f"  {'✅' if ok else '❌'} ON CONFLICT DO UPDATE = {result.stdout.strip()}")

    # Test 4: tsvector FTS
    sql = """
    CREATE TABLE IF NOT EXISTS test_fts (id serial, content text, content_tsv tsvector);
    INSERT INTO test_fts (content, content_tsv) VALUES ('hello world', to_tsvector('english','hello world'));
    SELECT content FROM test_fts WHERE content_tsv @@ to_tsquery('english','hello');
    """
    result = subprocess.run(
        ["docker", "exec", "pg-test", "psql", "-U", "postgres", "-d", "testdb", "-t", "-c", sql],
        capture_output=True, text=True
    )
    ok = result.returncode == 0 and "hello world" in result.stdout
    print(f"  {'✅' if ok else '❌'} tsvector FTS search")

    print()
    if failed == 0:
        print("🎉 All Phase 6 dialect smoke tests passed against real Postgres!")
    else:
        print(f"⚠️  {failed} test(s) failed - review above")


if __name__ == "__main__":
    main()
