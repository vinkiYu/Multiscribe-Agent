"""Command-line interface for MultiscribeAgent."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import cast

import click
import uvicorn

from multiscribe_agent import __version__
from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import DEFAULT_CURATION_AGENT_ID, ServiceContext
from multiscribe_agent.config import SystemSettings, get_settings
from multiscribe_agent.domain.models import ScheduleTask

DEFAULT_RSS_URL = "https://hnews.dev/rss"


@click.group()
@click.version_option(
    version=__version__,
    prog_name="multiscribe-agent",
    message="%(prog)s %(version)s",
)
def main() -> None:
    """Manage the MultiscribeAgent service and evaluation tools."""


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
def serve(host: str, port: int) -> None:
    """Start the FastAPI service."""
    uvicorn.run(create_app(get_settings()), host=host, port=port)


@main.command()
@click.option(
    "--adapter",
    "adapters",
    multiple=True,
    help="RSS adapter ID; accepts rss or the configured rss-adapter alias.",
)
@click.option("--rss-url", default=DEFAULT_RSS_URL, show_default=True, help="Public RSS feed URL.")
@click.option("--top-n", type=click.IntRange(min=1), help="Maximum curated items to publish.")
@click.option(
    "--target",
    "targets",
    help="Comma-separated publisher IDs, for example feishu_bot,wecom_bot.",
)
def digest(adapters: tuple[str, ...], rss_url: str, top_n: int | None, targets: str | None) -> None:
    """Run one daily digest directly, recording a task-log lifecycle without HTTP."""
    try:
        result = asyncio.run(_run_digest(adapters, rss_url, top_n, targets))
    except (LookupError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(_result_summary(result))


async def _run_digest(
    adapters: Sequence[str], rss_url: str, top_n: int | None, targets: str | None
) -> dict[str, object]:
    """Build a default daily-digest task, run it, and preserve scheduler task logging."""
    settings = get_settings()
    adapter_ids = _resolve_adapter_ids(adapters or settings.default_digest_adapter_ids)
    target_ids = _resolve_targets(targets, settings.default_digest_targets, settings)
    provider = next(
        (
            item
            for item in settings.ai_providers
            if item.id == settings.default_curation_provider_id
        ),
        None,
    )
    if provider is None or not provider.api_key:
        raise ValueError("default curation provider has no API key; configure its key in .env")
    task = ScheduleTask(
        id="manual-daily-digest",
        name="Manual daily digest",
        task_type="daily_digest",
        cron="0 0 * * *",
        config={
            "curate_agent_id": DEFAULT_CURATION_AGENT_ID,
            "adapter_ids": adapter_ids,
            "adapter_configs": {"rss": {"rss_url": rss_url}},
            "fetch_days": settings.default_digest_fetch_days,
            "top_n": top_n or settings.default_digest_top_n,
            "targets": target_ids,
        },
    )
    context = ServiceContext(settings)
    await context.init()
    result: dict[str, object] | None = None

    async def execute(_: ScheduleTask) -> dict[str, object]:
        nonlocal result
        result = await context.run_daily_digest_task(task)
        return result

    try:
        if context.scheduler is None:
            raise RuntimeError("scheduler is unavailable")
        await context.scheduler.execute_task(task, execute)
        if result is None:
            raise RuntimeError("daily digest failed; inspect task logs for details")
        return result
    finally:
        await context.close()


def _resolve_adapter_ids(adapter_ids: Sequence[str]) -> list[str]:
    """Normalize the MVP settings alias to the RSS plugin's registered metadata ID."""
    normalized: list[str] = []
    for adapter_id in adapter_ids:
        candidate = adapter_id.strip()
        if candidate in {"rss", "rss-adapter"}:
            normalized.append("rss")
            continue
        raise ValueError(f"unsupported digest adapter: {candidate}")
    if not normalized:
        raise ValueError("at least one RSS adapter must be configured")
    return list(dict.fromkeys(normalized))


def _resolve_targets(
    raw_targets: str | None, default_targets: Sequence[str], settings: SystemSettings
) -> list[str]:
    """Select explicitly requested or enabled configured publisher destinations."""
    requested = (
        [target.strip() for target in raw_targets.split(",") if target.strip()]
        if raw_targets is not None
        else list(default_targets)
    )
    enabled = {publisher.id for publisher in settings.publishers if publisher.enabled}
    selected = [target for target in requested if target in enabled]
    if raw_targets is not None and len(selected) != len(requested):
        unavailable = sorted(set(requested) - enabled)
        raise ValueError(f"unconfigured digest targets: {', '.join(unavailable)}")
    if not selected:
        raise ValueError("no configured digest target; set FEISHU_WEBHOOK or WECOM_WEBHOOK")
    return list(dict.fromkeys(selected))


def _result_summary(result: dict[str, object]) -> str:
    """Produce a concise user-facing summary without emitting publisher response payloads."""
    target_results = result.get("targets")
    if not isinstance(target_results, Mapping):
        return f"Daily digest finished: {result.get('message', 'no summary')}"
    statuses: list[str] = []
    for target, raw_details in cast(Mapping[str, object], target_results).items():
        if not isinstance(raw_details, Mapping):
            continue
        details = cast(Mapping[str, object], raw_details)
        status = details.get("status")
        statuses.append(f"{target}={status if isinstance(status, str) else 'unknown'}")
    message = result.get("message", "no summary")
    return f"Daily digest finished: {message}; targets: {', '.join(statuses)}"


@main.group(name="eval", invoke_without_command=True)
def evaluate() -> None:
    """Run evaluations when evaluation support is implemented."""
    raise click.ClickException("not implemented yet")
