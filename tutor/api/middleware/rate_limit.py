"""Rate limiting middleware with Redis support and in-memory fallback.

Provides distributed rate limiting using Redis when available,
with automatic fallback to in-memory rate limiting.
"""

import logging
import os
import time
from collections import defaultdict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """Redis-backed rate limiter with in-memory fallback.

    Uses sliding window algorithm for accurate rate limiting.
    Automatically falls back to in-memory if Redis is unavailable.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10,
        redis_url: Optional[str] = None,
    ):
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")

        self._redis_client = None
        self._use_redis = False
        self._in_memory_requests: Dict[str, List[float]] = defaultdict(list)
        self._in_memory_last_cleanup = time.time()

        # Try to connect to Redis
        self._init_redis()

    def _init_redis(self) -> None:
        """Initialize Redis connection if available."""
        try:
            import redis
            self._redis_client = redis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            self._redis_client.ping()
            self._use_redis = True
            logger.info("Redis rate limiter initialized successfully")
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory rate limiter: {e}")
            self._use_redis = False
            self._redis_client = None

    def _cleanup_in_memory_old_entries(self) -> None:
        """Clean up old entries from in-memory storage."""
        now = time.time()
        if now - self._in_memory_last_cleanup < 300:  # 5 minutes
            return

        self._in_memory_last_cleanup = now
        minute_ago = now - 60

        inactive_clients = [
            cid for cid, timestamps in self._in_memory_requests.items()
            if not timestamps or max(timestamps) < minute_ago
        ]
        for cid in inactive_clients:
            del self._in_memory_requests[cid]

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed for given client ID."""
        if self._use_redis:
            return self._is_allowed_redis(client_id)
        return self._is_allowed_in_memory(client_id)

    def _is_allowed_redis(self, client_id: str) -> bool:
        """Check rate limit using Redis (sliding window)."""
        try:
            key = f"rate_limit:{client_id}"
            now = time.time()
            window_start = now - 60

            pipe = self._redis_client.pipeline()
            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)
            # Count current entries
            pipe.zcard(key)
            # Add new entry
            pipe.zadd(key, {f"{now}": now})
            # Set expiry
            pipe.expire(key, 120)

            results = pipe.execute()
            count = results[1]

            return count < self.requests_per_minute
        except redis.RedisError as e:
            logger.warning(f"Redis error, falling back to in-memory: {e}")
            self._use_redis = False
            return self._is_allowed_in_memory(client_id)

    def _is_allowed_in_memory(self, client_id: str) -> bool:
        """Check rate limit using in-memory storage."""
        now = time.time()
        minute_ago = now - 60

        # Clean old requests
        self._in_memory_requests[client_id] = [
            t for t in self._in_memory_requests[client_id] if t > minute_ago
        ]

        # Check limit
        if len(self._in_memory_requests[client_id]) >= self.requests_per_minute:
            return False

        # Record request
        self._in_memory_requests[client_id].append(now)
        self._cleanup_in_memory_old_entries()
        return True

    def get_retry_after(self, client_id: str) -> int:
        """Get seconds to wait before retry."""
        if self._use_redis:
            return self._get_retry_after_redis(client_id)
        return self._get_retry_after_in_memory(client_id)

    def _get_retry_after_redis(self, client_id: str) -> int:
        """Get retry-after from Redis."""
        try:
            key = f"rate_limit:{client_id}"
            oldest = self._redis_client.zrange(key, 0, 0, withscores=True)
            if not oldest:
                return 0
            oldest_time = oldest[0][1]
            wait_time = 60 - (time.time() - oldest_time)
            return max(1, int(wait_time))
        except Exception:
            return self._get_retry_after_in_memory(client_id)

    def _get_retry_after_in_memory(self, client_id: str) -> int:
        """Get retry-after from in-memory storage."""
        if client_id not in self._in_memory_requests or not self._in_memory_requests[client_id]:
            return 0
        oldest = min(self._in_memory_requests[client_id])
        wait_time = 60 - (time.time() - oldest)
        return max(1, int(wait_time))


# Global rate limiter instance
_rate_limiter: Optional[RedisRateLimiter] = None


def get_rate_limiter() -> RedisRateLimiter:
    """Get or create global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        requests_per_minute = int(os.environ.get("TUTOR_RATE_LIMIT", "60"))
        _rate_limiter = RedisRateLimiter(requests_per_minute=requests_per_minute)
    return _rate_limiter


class RateLimitMiddleware:
    """Rate limiting middleware for FastAPI."""

    def __init__(self, app, rate_limiter: Optional[RedisRateLimiter] = None):
        self.app = app
        self.rate_limiter = rate_limiter or get_rate_limiter()

    async def __call__(self, request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/health/live", "/health/ready", "/metrics"]:
            return await call_next(request)

        client_id = request.client.host if request.client else "unknown"

        if not self.rate_limiter.is_allowed(client_id):
            from fastapi.responses import JSONResponse
            retry_after = self.rate_limiter.get_retry_after(client_id)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "detail": f"Rate limit exceeded. Retry after {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        return response
