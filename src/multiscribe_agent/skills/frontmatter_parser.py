"""Minimal parser for the constrained SKILL.md frontmatter contract."""

from __future__ import annotations

import ast

from multiscribe_agent.domain.models import SkillFrontmatter


class SkillParseError(ValueError):
    """Raised when a SKILL.md frontmatter block is malformed."""


def parse_frontmatter(text: str) -> tuple[SkillFrontmatter, str]:
    """Extract constrained YAML frontmatter and the remaining Markdown body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillParseError("SKILL.md must begin with frontmatter delimiter")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise SkillParseError("SKILL.md frontmatter is not closed") from exc
    fields = _parse_fields(lines[1:end])
    name = _required_string(fields, "name")
    description = _required_string(fields, "description")
    bins = fields.get("bins", [])
    if not isinstance(bins, list) or not all(isinstance(item, str) for item in bins):
        raise SkillParseError("bins must be a string list")
    body = "\n".join(lines[end + 1 :]).strip()
    if not body:
        raise SkillParseError("SKILL.md body must not be empty")
    return SkillFrontmatter(name=name, description=description, bins=bins), body


def _parse_fields(lines: list[str]) -> dict[str, object]:
    """Parse the three supported scalar-or-list fields without a YAML dependency."""
    fields: dict[str, object] = {}
    active_list: str | None = None
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if active_list is None:
                raise SkillParseError("list item has no field")
            values = fields.setdefault(active_list, [])
            if not isinstance(values, list):
                raise SkillParseError("mixed scalar and list field")
            values.append(_unquote(stripped[2:].strip()))
            continue
        if ":" not in stripped:
            raise SkillParseError("frontmatter lines must be key-value pairs")
        key, raw_value = (part.strip() for part in stripped.split(":", 1))
        if key not in {"name", "description", "bins"}:
            raise SkillParseError(f"unsupported frontmatter field: {key}")
        if key in fields:
            raise SkillParseError(f"duplicate frontmatter field: {key}")
        active_list = key if key == "bins" and not raw_value else None
        if key == "bins":
            fields[key] = _parse_inline_list(raw_value) if raw_value else []
        else:
            fields[key] = _unquote(raw_value)
    return fields


def _parse_inline_list(value: str) -> list[str]:
    """Parse a bracketed string list using Python's safe literal parser."""
    if not value.startswith("[") or not value.endswith("]"):
        raise SkillParseError("bins must be an inline list or a block list")
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise SkillParseError("invalid inline bins list") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise SkillParseError("bins must be a string list")
    return parsed


def _required_string(fields: dict[str, object], key: str) -> str:
    """Return a required non-empty scalar field."""
    value = fields.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SkillParseError(f"{key} must be a non-empty string")
    return value


def _unquote(value: str) -> str:
    """Remove one matching quote pair and preserve escaped values."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise SkillParseError("invalid quoted frontmatter value") from exc
        if not isinstance(parsed, str):
            raise SkillParseError("frontmatter value must be a string")
        return parsed
    return value
