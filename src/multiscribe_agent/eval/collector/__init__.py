"""Evaluation collection components (P64.2 T7): pools, bad cases, trace sinks."""

from multiscribe_agent.eval.collector.bad_case import BadCaseCollector, BadCaseRecord
from multiscribe_agent.eval.collector.random_pool import (
    RandomPoolCollector,
    SourceRow,
)
from multiscribe_agent.eval.collector.trace_sink import TraceSink

__all__ = [
    "BadCaseCollector",
    "BadCaseRecord",
    "RandomPoolCollector",
    "SourceRow",
    "TraceSink",
]
