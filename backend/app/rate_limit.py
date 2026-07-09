"""Simple in-memory sliding-window rate limiter (production hygiene).

Limits request-heavy endpoints (/chat, /chat/stream, /simulate, /voice) per
client IP. Implemented as a **pure ASGI middleware** (not BaseHTTPMiddleware) so
it never wraps or buffers the response body — critical for SSE and WebSocket
streaming, which BaseHTTPMiddleware is known to break. In a multi-instance
deployment swap the in-memory store for Redis. Complements the per-session cost
cap enforced inside the agent loop (app/agent/graph.py).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

LIMITED_PREFIXES = ("/chat", "/simulate")
WINDOW_SECONDS = 60
MAX_REQUESTS = 40  # per IP per window across limited endpoints


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(LIMITED_PREFIXES):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        ip = client[0] if client else "unknown"
        now = time.time()
        q = self._hits[ip]
        while q and q[0] < now - WINDOW_SECONDS:
            q.popleft()
        if len(q) >= MAX_REQUESTS:
            resp = JSONResponse(
                status_code=429,
                content={"error": "rate_limited", "detail": "Too many requests; slow down a moment."},
            )
            await resp(scope, receive, send)
            return
        q.append(now)
        await self.app(scope, receive, send)
