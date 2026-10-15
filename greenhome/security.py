"""Bounded pilot resource controls. Not a replacement for a production gateway."""
from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
import os
import ipaddress
import secrets
import threading
import time

from starlette.responses import JSONResponse


class ServiceBusy(Exception):
    pass


class AuthenticatedGatewayContext:
    """Recognise the configured loopback gateway, never arbitrary proxy headers.

    The public tunnel strips/injects this token only after its authentication.
    This flag describes that trusted ingress, not a customer identity or role.
    """
    def __init__(self, app, token: str, active: bool):
        self.app, self.token, self.active = app, token, active

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope)
            scope["greenhome.authenticated_gateway"] = False
            peer = (scope.get("client") or ("", 0))[0]
            try:
                local = ipaddress.ip_address(peer).is_loopback
            except ValueError:
                local = False
            supplied = dict(scope.get("headers", [])).get(b"x-greenhome-gateway", b"")
            if self.active and local and len(self.token) >= 32:
                scope["greenhome.authenticated_gateway"] = secrets.compare_digest(
                    supplied, self.token.encode(),
                )
        await self.app(scope, receive, send)


def enabled(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, str(default)).strip().lower()
    if value in ("1", "true", "yes"):
        return True
    if value in ("0", "false", "no"):
        return False
    raise ValueError(f"{name} must be an explicit true or false value.")


class WorkSlots:
    def __init__(self, capacity=4):
        self.slots = threading.BoundedSemaphore(capacity)

    @contextmanager
    def claim(self):
        if not self.slots.acquire(blocking=False):
            raise ServiceBusy()
        try:
            yield
        finally:
            self.slots.release()


class PilotBoundary:
    """Per-process, finite-window rate limits and browser origin checks."""
    def __init__(self, app, allowed_origins, general_limit=120):
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)
        self.general_limit = general_limit
        self.buckets = defaultdict(deque)
        self.lock = threading.Lock()

    def allowed(self, client, category, maximum):
        now = time.monotonic()
        with self.lock:
            # Bound the table rather than retaining arbitrary client identifiers.
            if len(self.buckets) >= 2048:
                expired = [k for k, q in self.buckets.items() if not q or q[-1] <= now - 60]
                for k in expired:
                    del self.buckets[k]
                if len(self.buckets) >= 2048 and (client, category) not in self.buckets:
                    return False
            q = self.buckets[(client, category)]
            while q and q[0] <= now - 60:
                q.popleft()
            if len(q) >= maximum:
                return False
            q.append(now)
            return True

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        headers = dict(scope.get("headers", []))
        if path.startswith("/api/") and scope.get("method") == "POST":
            origin = headers.get(b"origin")
            if origin and origin.decode("latin1") not in self.allowed_origins:
                return await JSONResponse(
                    {"detail": {"code": "origin_not_allowed", "message": "This browser origin is not allowed."}},
                    status_code=403,
                )(scope, receive, send)
            content_type = headers.get(b"content-type", b"").split(b";")[0].strip().lower()
            # Let absent content type reach existing strict validation (422).
            if content_type and content_type != b"application/json":
                return await JSONResponse(
                    {"detail": {"code": "json_required", "message": "Use application/json."}}, status_code=415
                )(scope, receive, send)
        if path.startswith("/api/") and scope.get("method") != "OPTIONS":
            client = (scope.get("client") or ("unknown", 0))[0]
            limit = 10 if path == "/api/what-if" else 30 if path == "/api/decision-check" else self.general_limit
            category = path if path in ("/api/what-if", "/api/decision-check") else "general"
            if not self.allowed(client, category, limit):
                return await JSONResponse(
                    {"detail": {"code": "rate_limited", "message": "Too many requests. Try again in a minute."}},
                    status_code=429, headers={"Retry-After": "60"},
                )(scope, receive, send)

        async def security_send(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []),
                    (b"x-frame-options", b"DENY"), (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"),
                ]}
            await send(message)
        await self.app(scope, receive, security_send)
