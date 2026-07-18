"""Built-in source adapters."""

from multiscribe_agent.plugins.builtin.adapters.ai_search import AISearchAdapter
from multiscribe_agent.plugins.builtin.adapters.github_trending import GitHubTrendingAdapter
from multiscribe_agent.plugins.builtin.adapters.rss import RSSAdapter

__all__ = ["AISearchAdapter", "GitHubTrendingAdapter", "RSSAdapter"]
