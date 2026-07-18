"""Mocked HTTP and HTML-fixture tests for the GitHub Trending adapter."""

from __future__ import annotations

import httpx
import pytest
import respx

from multiscribe_agent.plugins.builtin.adapters.github_trending import GitHubTrendingAdapter
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import AdapterRegistry

TRENDING_URL = "https://github.com/trending"
TYPESCRIPT_TRENDING_URL = "https://github.com/trending/typescript"
SAMPLE_HTML = """
<html><body>
<article class="Box-row">
  <h2><a href="/psf/requests">psf/requests</a></h2>
  <p>Python HTTP for Humans.</p>
  <span itemprop="programmingLanguage">Python</span>
  <a href="/psf/requests/stargazers">52,000</a>
</article>
<article class="Box-row">
  <h2><a href="/microsoft/vscode">microsoft/vscode</a></h2>
  <p>Visual Studio Code.</p>
  <span itemprop="programmingLanguage">TypeScript</span>
  <a href="/microsoft/vscode/stargazers">95,000</a>
</article>
<article class="Box-row">
  <h2><a href="/example/new-project">example/new-project</a></h2>
  <p>A small but promising repository.</p>
  <span itemprop="programmingLanguage">Python</span>
  <a href="/example/new-project/stargazers">99</a>
</article>
</body></html>
"""


@pytest.mark.asyncio
async def test_fetch_and_transform_returns_unified_data() -> None:
    """A mocked Trending response produces complete canonical repository entries."""
    adapter = GitHubTrendingAdapter()
    with respx.mock:
        respx.get(TRENDING_URL).mock(return_value=httpx.Response(200, text=SAMPLE_HTML))
        items = await adapter.fetch_and_transform({})

    assert len(items) == 3
    assert items[0].id == "github:psf/requests"
    assert items[0].source == "github_trending"
    assert items[0].metadata["stars"] == 52_000


@pytest.mark.asyncio
async def test_language_filter_uses_language_endpoint_and_filters_results() -> None:
    """Language configuration builds GitHub's language route and keeps matching items."""
    adapter = GitHubTrendingAdapter()
    with respx.mock:
        respx.get(TYPESCRIPT_TRENDING_URL).mock(return_value=httpx.Response(200, text=SAMPLE_HTML))
        items = await adapter.fetch_and_transform({"language": "typescript"})

    assert [item.id for item in items] == ["github:microsoft/vscode"]


@pytest.mark.asyncio
async def test_stars_min_filter_excludes_lower_star_repositories() -> None:
    """The minimum-star setting is applied after parsing each repository entry."""
    adapter = GitHubTrendingAdapter()
    with respx.mock:
        respx.get(TRENDING_URL).mock(return_value=httpx.Response(200, text=SAMPLE_HTML))
        items = await adapter.fetch_and_transform({"stars_min": 60_000})

    assert [item.id for item in items] == ["github:microsoft/vscode"]


@pytest.mark.asyncio
async def test_max_items_limits_normalized_results() -> None:
    """The maximum-item setting stops parsing once the requested count is reached."""
    adapter = GitHubTrendingAdapter()
    with respx.mock:
        respx.get(TRENDING_URL).mock(return_value=httpx.Response(200, text=SAMPLE_HTML))
        items = await adapter.fetch_and_transform({"max_items": 1})

    assert [item.id for item in items] == ["github:psf/requests"]


def test_github_trending_adapter_is_discovered() -> None:
    """The metadata-bearing adapter is available through standard plugin discovery."""
    result = scan_and_register()

    assert (
        "multiscribe_agent.plugins.builtin.adapters.github_trending.GitHubTrendingAdapter"
        in result.registered
    )
    metadata = AdapterRegistry.get_instance().list_metadata()
    assert any(item.id == "github_trending" for item in metadata)
