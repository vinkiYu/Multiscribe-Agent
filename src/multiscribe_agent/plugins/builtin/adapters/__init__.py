"""Built-in source adapters."""

from multiscribe_agent.plugins.builtin.adapters.github_trending import GitHubTrendingAdapter
from multiscribe_agent.plugins.builtin.adapters.rss import RSSAdapter

__all__ = ["GitHubTrendingAdapter", "RSSAdapter"]
