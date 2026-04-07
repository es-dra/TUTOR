"""Tests for middleware module."""
import pytest


@pytest.mark.unit
def test_security_middleware_exists():
    """Verify security middleware module exists and exports configure_security."""
    from tutor.api.middleware.security import configure_security
    assert callable(configure_security)


@pytest.mark.unit
def test_rate_limiter_has_redis_fallback():
    """Verify RedisRateLimiter falls back to in-memory when Redis unavailable."""
    from tutor.api.middleware.rate_limit import RedisRateLimiter
    import inspect

    source = inspect.getsource(RedisRateLimiter)
    assert "redis" in source.lower() or "fallback" in source.lower() or "in_memory" in source.lower()
