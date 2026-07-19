import pytest

from multiscribe_agent.services.interop_rate_limit import RateLimitExceeded, SlidingWindowLimiter


def test_sliding_window_enforces_limit() -> None:
    limiter = SlidingWindowLimiter(window_seconds=60)
    limiter.check("key", 2)
    limiter.check("key", 2)
    with pytest.raises(RateLimitExceeded):
        limiter.check("key", 2)


def test_sliding_window_isolated_by_key() -> None:
    limiter = SlidingWindowLimiter(window_seconds=60)
    limiter.check("a", 1)
    limiter.check("b", 1)
    limiter.reset()
    limiter.check("a", 1)
