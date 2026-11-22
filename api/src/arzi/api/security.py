"""HTTP hardening: security headers, a request-size cap and per-client rate limits.

The API and the SPA share one origin (ADR-0007), so there is no CORS middleware at all: a browser
on any other origin cannot read responses. The rate limiter is an in-memory token bucket keyed by
an HMAC of the client address (no raw IP is kept); with up to three Cloud Run instances the
effective limit is up to three times the configured one, which is acceptable at this scale.
"""

import hashlib
import hmac
import math
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from arzi.api.errors import problem_response

Clock = Callable[[], float]
Handler = Callable[[Request], Awaitable[Response]]

# 'unsafe-inline' for styles only: Radix positions popovers with inline style attributes.
# Images, audio and connections may reach Cloud Storage for V4 signed document URLs.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https://storage.googleapis.com",
        "media-src 'self' data: blob: https://storage.googleapis.com",
        "font-src 'self' data:",
        "connect-src 'self' https://storage.googleapis.com",
        "worker-src 'self' blob:",
        "frame-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # Family links carry their token in the path: never send it to another site.
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

_EXEMPT = ("/health", "/healthz", "/readyz")


async def security_headers_middleware(request: Request, call_next: Handler) -> Response:
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


def body_limit_middleware(max_bytes: int) -> Callable[[Request, Handler], Awaitable[Response]]:
    """Refuse a declared body over the cap before reading it (uploads are also checked per file)."""

    async def middleware(request: Request, call_next: Handler) -> Response:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            return problem_response(
                request, 413, "request-too-large", "The request is larger than allowed."
            )
        return await call_next(request)

    return middleware


class TokenBucketLimiter:
    """``rate`` requests per minute per client with bursts up to ``burst``; LRU-bounded."""

    def __init__(
        self,
        key: bytes,
        *,
        rate_per_minute: int,
        burst: int,
        clock: Clock = time.monotonic,
        max_clients: int = 10_000,
    ) -> None:
        self._key = key
        self._rate = rate_per_minute / 60.0
        self._burst = float(burst)
        self._clock = clock
        self._max = max_clients
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()

    def _client(self, address: str) -> str:
        return hmac.new(self._key, address.encode(), hashlib.sha256).hexdigest()[:24]

    def take(self, address: str) -> float:
        """0 if the request may proceed, else the seconds to wait before retrying."""
        client, now = self._client(address), self._clock()
        tokens, seen = self._buckets.pop(client, (self._burst, now))
        tokens = min(self._burst, tokens + (now - seen) * self._rate)
        wait = 0.0
        if tokens >= 1:
            tokens -= 1
        else:
            wait = (1 - tokens) / self._rate
        self._buckets[client] = (tokens, now)
        while len(self._buckets) > self._max:
            self._buckets.popitem(last=False)
        return wait


def rate_limit_middleware(
    limiter: TokenBucketLimiter,
) -> Callable[[Request, Handler], Awaitable[Response]]:
    async def middleware(request: Request, call_next: Handler) -> Response:
        path = request.url.path
        if not path.startswith("/api/") or path.startswith(_EXEMPT):
            return await call_next(request)
        wait = limiter.take(request.client.host if request.client else "unknown")
        if wait:
            response = problem_response(
                request, 429, "rate-limited", "Too many requests. Please slow down and retry."
            )
            response.headers["Retry-After"] = str(math.ceil(wait))
            return response
        return await call_next(request)

    return middleware
