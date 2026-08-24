"""
Rate limiting - a fixed-window counter, kept in memory.

JAVA: Bucket4j, or Spring Cloud Gateway's RequestRateLimiter.

WARNING, and this matters in production: this counter lives inside ONE process.
Run 4 uvicorn workers and each gets its own counter, so the real limit becomes
4x what you configured. For anything serious, move the counter to Redis
(the `slowapi` or `fastapi-limiter` packages do this) or enforce it at nginx /
the load balancer, which is where it belongs anyway.

It is here because a bad rate limiter beats none on the login endpoint:
without it, /auth/token is an open door for credential stuffing.
"""

import time
from collections import defaultdict

from fastapi import HTTPException, status


class FixedWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        # key -> (window_start_timestamp, count_in_window)
        self._hits: dict[str, tuple[float, int]] = defaultdict(lambda: (0.0, 0))

    def check(self, key: str) -> None:
        now = time.monotonic()          # monotonic: immune to clock changes
        start, count = self._hits[key]

        if now - start >= self.window:
            self._hits[key] = (now, 1)  # new window
            return

        if count >= self.max_requests:
            retry_after = int(self.window - (now - start)) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={"Retry-After": str(retry_after)},
            )

        self._hits[key] = (start, count + 1)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


# Login is brute-forceable, so it gets a much tighter limit than the API.
login_limiter = FixedWindowLimiter(max_requests=5, window_seconds=60)
api_limiter = FixedWindowLimiter(max_requests=60, window_seconds=60)
