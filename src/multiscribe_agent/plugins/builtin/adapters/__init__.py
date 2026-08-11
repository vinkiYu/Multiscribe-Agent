"""Built-in source adapters."""

from multiscribe_agent.plugins.builtin.adapters.ai_search import AISearchAdapter
from multiscribe_agent.plugins.builtin.adapters.follow import FollowAdapter
from multiscribe_agent.plugins.builtin.adapters.github_trending import GitHubTrendingAdapter
from multiscribe_agent.plugins.builtin.adapters.hacker_news import HackerNewsAdapter
from multiscribe_agent.plugins.builtin.adapters.hf_daily_papers import HFDailyPapersAdapter
from multiscribe_agent.plugins.builtin.adapters.last_week_in_ai import LastWeekInAIAdapter
from multiscribe_agent.plugins.builtin.adapters.rss import RSSAdapter
from multiscribe_agent.plugins.builtin.adapters.tldr_ai import TLDRAIAdapter

__all__ = [
    "AISearchAdapter",
    "FollowAdapter",
    "GitHubTrendingAdapter",
    "HFDailyPapersAdapter",
    "HackerNewsAdapter",
    "LastWeekInAIAdapter",
    "RSSAdapter",
    "TLDRAIAdapter",
]
