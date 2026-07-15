"""Command-line interface for MultiscribeAgent."""

from __future__ import annotations

import click

from multiscribe_agent import __version__


@click.group()
@click.version_option(
    version=__version__,
    prog_name="multiscribe-agent",
    message="%(prog)s %(version)s",
)
def main() -> None:
    """Manage the MultiscribeAgent service and evaluation tools."""


@main.group(invoke_without_command=True)
def serve() -> None:
    """Start the API service when server support is implemented."""
    raise click.ClickException("not implemented yet")


@main.group(name="eval", invoke_without_command=True)
def evaluate() -> None:
    """Run evaluations when evaluation support is implemented."""
    raise click.ClickException("not implemented yet")
