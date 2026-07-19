"""Coverage for the intentionally constrained SKILL.md parser."""

from __future__ import annotations

import pytest

from multiscribe_agent.skills.frontmatter_parser import SkillParseError, parse_frontmatter


def test_parse_frontmatter_supports_inline_and_quoted_values() -> None:
    """Supported scalar values and inline bins map to the domain model."""
    frontmatter, body = parse_frontmatter(
        "---\nname: 'Weekly'\ndescription: \"A report\"\nbins: ['tool']\n---\n\n# Steps"
    )
    assert frontmatter.name == "Weekly"
    assert frontmatter.bins == ["tool"]
    assert body == "# Steps"


def test_parse_frontmatter_supports_block_bins() -> None:
    """The parser accepts the documented multiline list representation."""
    frontmatter, _ = parse_frontmatter(
        "---\nname: One\ndescription: Two\nbins:\n- alpha\n- beta\n---\n\nBody"
    )
    assert frontmatter.bins == ["alpha", "beta"]


@pytest.mark.parametrize("text", ["# No metadata", "---\nname: Missing\n---\nBody"])
def test_parse_frontmatter_rejects_invalid_documents(text: str) -> None:
    """Missing delimiters or required fields use a dedicated parse error."""
    with pytest.raises(SkillParseError):
        parse_frontmatter(text)
