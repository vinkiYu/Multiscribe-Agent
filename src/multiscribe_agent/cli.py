"""Command-line interface for MultiscribeAgent."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import click
import uvicorn

from multiscribe_agent import __version__
from multiscribe_agent.app import create_app
from multiscribe_agent.bootstrap import DEFAULT_CURATION_AGENT_ID, ServiceContext
from multiscribe_agent.config import SystemSettings, get_settings
from multiscribe_agent.domain.models import ScheduleTask
from multiscribe_agent.eval.benchmark import run_benchmark
from multiscribe_agent.eval.dataset import load_dataset
from multiscribe_agent.llm.provider import AIProvider, create_provider
from multiscribe_agent.mcp.server import run_sse_server, run_stdio_server

DEFAULT_RSS_URL = "https://feeds.bbci.co.uk/news/rss.xml"


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


@main.command(name="mcp")
@click.option("--transport", default="stdio", type=click.Choice(["stdio", "sse"]))
@click.option("--host", default=None)
@click.option("--port", default=None, type=int)
def mcp(transport: str, host: str | None, port: int | None) -> None:
    """Run the authenticated MCP server for local or remote clients."""
    settings = get_settings()
    if transport == "stdio":
        asyncio.run(run_stdio_server())
        return
    asyncio.run(
        run_sse_server(
            host=host or settings.mcp_default_host,
            port=port if port is not None else settings.mcp_default_port,
        )
    )


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


@main.command(name="eval")
@click.option(
    "--dataset",
    "dataset_name",
    required=True,
    help="数据集名 (不含扩展名, 位于 data/eval/datasets/)。",
)
@click.option("--agent", default="default-curation-agent", show_default=True)
@click.option(
    "--datasets-dir",
    default="data/eval/datasets",
    show_default=True,
    type=click.Path(exists=True, file_okay=False),
)
@click.option("--reports-dir", default="data/eval/reports", show_default=True)
@click.option("--baseline", default="data/eval/baselines/last.json", show_default=True)
@click.option("--regression-threshold", default=0.10, show_default=True, type=float)
def evaluate(
    dataset_name: str,
    agent: str,
    datasets_dir: str,
    reports_dir: str,
    baseline: str,
    regression_threshold: float,
) -> None:
    """运行 LLM-as-Judge 评估并生成 Markdown 报告。"""
    del agent  # Pipeline state is replayed directly; agent is retained for CLI compatibility.
    settings = get_settings()
    provider = _resolve_eval_provider(settings)
    dataset_path = _resolve_dataset_path(Path(datasets_dir), dataset_name)
    try:
        dataset = load_dataset(dataset_path)
        summary = asyncio.run(
            run_benchmark(
                provider,
                dataset,
                preferred_tags=[],
                reports_dir=Path(reports_dir),
                baseline_path=Path(baseline) if baseline else None,
                regression_threshold=regression_threshold,
            )
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"OK {summary.dataset_name} overall={summary.overall:.2f}")


def _resolve_dataset_path(datasets_dir: Path, dataset_name: str) -> Path:
    """Resolve dataset names while accepting hyphen and underscore aliases."""
    direct = datasets_dir / f"{dataset_name}.yaml"
    if direct.is_file() or "-" not in dataset_name:
        return direct
    alias = datasets_dir / f"{dataset_name.replace('-', '_')}.yaml"
    return alias if alias.is_file() else direct


def _resolve_eval_provider(settings: SystemSettings) -> AIProvider:
    """Create the configured curation provider without initializing the service graph."""
    config = next(
        (
            item
            for item in settings.ai_providers
            if item.id == settings.default_curation_provider_id
        ),
        None,
    )
    if config is None or not config.api_key:
        raise click.ClickException("default curation provider has no API key; configure its key")
    try:
        return create_provider(
            config,
            model=settings.default_curation_model,
            temperature=settings.default_curation_temperature,
            proxy=settings.http_proxy or None,
        )
    except (NotImplementedError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
