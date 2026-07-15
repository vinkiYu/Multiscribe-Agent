# MultiscribeAgent

MultiscribeAgent is a Python platform for declarative agents, workflow orchestration, and
automated multi-channel content publishing.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

## Development

```bash
uv sync --extra dev
uv run python -m multiscribe_agent --version
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv run pre-commit run --all-files
```

Project requirements and architecture are documented in [`docs/`](docs/). Start with the
[`MVP`](docs/MVP.md) and [`architecture`](docs/ARCHITECTURE.md) documents.
