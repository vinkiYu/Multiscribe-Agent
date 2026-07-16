"""End-to-end agent workflows assembled from application services."""

from multiscribe_agent.agents.pipelines.daily_digest import (
    DailyDigestConfig,
    DailyDigestPipeline,
    build_daily_digest_workflow,
    register_daily_digest_executor,
)

__all__ = [
    "DailyDigestConfig",
    "DailyDigestPipeline",
    "build_daily_digest_workflow",
    "register_daily_digest_executor",
]
