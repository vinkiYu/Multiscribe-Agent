"""Command-line interface for MultiscribeAgent."""

from __future__ import annotations

import click
import uvicorn

from multiscribe_agent import __version__
from multiscribe_agent.app import create_app
from multiscribe_agent.config import get_settings


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


@main.group(name="eval", invoke_without_command=True)
def evaluate() -> None:
    """Run evaluations when evaluation support is implemented."""
    raise click.ClickException("not implemented yet")
