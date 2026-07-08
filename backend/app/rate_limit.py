"""Simple in-memory sliding-window rate limiter (production hygiene).

Limits request-heavy endpoints (/chat, /chat/stream, /simulate) per client IP.
In a multi-instance deployment swap the in-memory store for Redis; the
middleware interface stays the same. This complements the per-session cost cap
enforced inside the agent loop (app/agent/graph.py).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

LIMITED_PREFIXES = ("/chat", "/simulate")
WINDOW_SECONDS = 60
MAX_REQUESTS = 40  # per IP per window across limited endpoints


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith(LIMITED_PREFIXES):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        now = time.time()
        q = self._hits[ip]
        while q and q[0] < now - WINDOW_SECONDS:
            q.popleft()
        if len(q) >= MAX_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited", "detail": "Too many requests; slow down a moment."},
            )
        q.append(now)
        return await call_next(request)
