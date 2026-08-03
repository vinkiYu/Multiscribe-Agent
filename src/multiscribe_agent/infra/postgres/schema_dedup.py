"""PostgreSQL DDL for daily-digest idempotency and workflow checkpoints."""

from __future__ import annotations

PUSHED_CONTENT_PG = """
CREATE TABLE IF NOT EXISTS pushed_content (
    content_hash TEXT NOT NULL,
    url TEXT NOT NULL,
    digest_date TEXT NOT NULL,
    pushed_at TEXT NOT NULL,
    title TEXT NOT NULL,
    PRIMARY KEY (content_hash, digest_date)
);
CREATE INDEX IF NOT EXISTS idx_pushed_content_pushed_at
    ON pushed_content(pushed_at DESC);
"""

PUBLISH_HISTORY_PG = """
CREATE TABLE IF NOT EXISTS publish_history (
    id TEXT PRIMARY KEY,
    publisher_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('success', 'error')),
    title TEXT NOT NULL,
    content_preview TEXT NOT NULL,
    result_data TEXT NOT NULL DEFAULT '{}',
    error_message TEXT,
    published_at TEXT NOT NULL,
    adapter_name TEXT,
    digest_date TEXT,
    content_hash TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_publish_history_publisher_date
    ON publish_history(publisher_id, digest_date);
CREATE INDEX IF NOT EXISTS idx_publish_history_publisher_published
    ON publish_history(publisher_id, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_publish_history_published
    ON publish_history(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_publish_history_content_hash
    ON publish_history(content_hash);
"""

WORKFLOW_ITERATIONS_PG = """
CREATE TABLE IF NOT EXISTS workflow_iterations (
    workflow_run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    round INTEGER NOT NULL,
    output TEXT NOT NULL DEFAULT '',
    score DOUBLE PRECISION,
    feedback TEXT,
    converged INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    recorded_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())),
    PRIMARY KEY (workflow_run_id, step_id, round)
);
CREATE INDEX IF NOT EXISTS idx_workflow_iterations_run
    ON workflow_iterations(workflow_run_id);
"""

ALL_SCHEMAS = (PUSHED_CONTENT_PG, PUBLISH_HISTORY_PG, WORKFLOW_ITERATIONS_PG)
