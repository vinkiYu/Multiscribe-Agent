"""Load and render sectioned Markdown prompts."""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

SECTION_PATTERN = re.compile(r"^## \[([^]]+)]\s*$", re.MULTILINE)


class PromptService:
    """Read ``## [Section]`` blocks from Jinja-enabled Markdown templates."""

    def __init__(self, prompt_directory: Path | None = None) -> None:
        """Create a prompt loader rooted at package resources by default."""
        directory = prompt_directory or Path(__file__).parents[1] / "resources" / "prompts"
        self._loader = FileSystemLoader(directory)
        self._environment = Environment(
            loader=self._loader,
            autoescape=False,  # noqa: S701 - prompts are plain text, never HTML responses.
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )

    def get_section(self, template_name: str, section_name: str) -> str:
        """Return one named raw template section without rendering variables.

        Raises:
            KeyError: If the requested section does not exist.
            FileNotFoundError: If the template file does not exist.
        """
        try:
            source, _, _ = self._loader.get_source(
                self._environment, self._normalize_name(template_name)
            )
        except TemplateNotFound as exc:
            raise FileNotFoundError(f"prompt template not found: {template_name}") from exc
        matches = list(SECTION_PATTERN.finditer(source))
        for index, match in enumerate(matches):
            if match.group(1) != section_name:
                continue
            end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
            return source[match.end() : end].strip()
        raise KeyError(f"prompt section not found: {template_name}#{section_name}")

    def render(self, template_name: str, section_name: str, **variables: object) -> str:
        """Render one named section with strict Jinja variables."""
        return self._environment.from_string(self.get_section(template_name, section_name)).render(
            **variables
        )

    @staticmethod
    def _normalize_name(template_name: str) -> str:
        return template_name if template_name.endswith(".md") else f"{template_name}.md"
