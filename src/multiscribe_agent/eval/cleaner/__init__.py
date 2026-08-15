"""Evaluation cleaning components (P64.2 T8): normalize, validate, dedup, audit."""

from multiscribe_agent.eval.cleaner.dedup_hasher import DedupHasher
from multiscribe_agent.eval.cleaner.fixture_draft import (
    bad_case_ids,
    build_fixture_draft,
    unified_fixture_diff,
)
from multiscribe_agent.eval.cleaner.label_auditor import DisputeRecord, LabelAuditor
from multiscribe_agent.eval.cleaner.label_normalizer import LabelNormalizer
from multiscribe_agent.eval.cleaner.schema_validator import SchemaValidator

__all__ = [
    "DedupHasher",
    "DisputeRecord",
    "LabelAuditor",
    "LabelNormalizer",
    "SchemaValidator",
    "bad_case_ids",
    "build_fixture_draft",
    "unified_fixture_diff",
]
