"""Loopback-only, password-protected gateway for the temporary Cloudflare demo.

Pages supplies a separate proxy secret. Both that secret and the user's Basic
login must pass before the gateway injects the existing application credential.
This is a shared demonstration login, not customer identity or production auth.
"""
from __future__ import annotations

import base64
import binascii
from contextlib import asynccontextmanager
from dataclasses import dataclass
import os
import secrets
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
import httpx
from starlette.responses import JSONResponse, Response

MAX_BODY = 262_144
MAX_RESPONSE = 16 * 1024 * 1024
FETCH_VARY = "Origin, Sec-Fetch-Site, Sec-Fetch-Mode, Sec-Fetch-Dest"
PASS_HEADERS = {"accept", "content-type", "cookie", "origin", "sec-fetch-site"}
DROP_RESPONSE = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "content-length",
    "content-encoding",
}


@dataclass(frozen=True, repr=False)
class GatewayConfig:
    public_origin: str
    proxy_secret: str
    username: str
    password: str
    gateway_token: str
    backend_url: str = "http://127.0.0.1:8002"

    def __post_init__(self):
        public = urlsplit(self.public_origin)
        backend = urlsplit(self.backend_url)
        if (
            public.scheme != "https" or not public.hostname
            or not public.hostname.endswith(".pages.dev")
            or public.username or public.password or public.port
            or public.path or public.query or public.fragment
        ):
            raise ValueError("An exact HTTPS Pages origin is required.")
        if (
            backend.scheme != "http" or backend.hostname != "127.0.0.1"
            or not backend.port or backend.path or backend.query
            or backend.fragment or backend.username or backend.password
        ):
            raise ValueError("The backend must be a fixed loopback HTTP origin.")
        if (
            len(self.proxy_secret) < 32 or len(self.gateway_token) < 32
            or len(self.password) < 12 or not self.username or ":" in self.username
        ):
            raise ValueError("Private gateway credentials are missing or invalid.")


def _error(status: int, code: str, *, challenge: bool = False):
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Vary": FETCH_VARY,
    }
    if challenge:
        headers["WWW-Authenticate"] = 'Basic realm="GreenHome Team 225", charset="UTF-8"'
    return JSONResponse({"detail": {"code": code}}, status_code=status, headers=headers)


def create_gateway(config: GatewayConfig, *, transport=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(45, connect=5, pool=5),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            follow_redirects=False, trust_env=False, transport=transport,
        ) as client:
            app.state.client = client
            yield

    app = FastAPI(
        docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan,
    )

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
    async def proxy(request: Request, path: str):
        raw = request.scope["headers"]
        # Duplicate credential/origin headers are ambiguous and always rejected.
        for name in (
            b"authorization", b"x-greenhome-proxy", b"origin", b"content-length",
            b"sec-fetch-site", b"sec-fetch-mode", b"sec-fetch-dest",
        ):
            if sum(key.lower() == name for key, _ in raw) > 1:
                return _error(400, "ambiguous_headers")
        supplied = request.headers.get("x-greenhome-proxy", "").encode()
        if not secrets.compare_digest(supplied, config.proxy_secret.encode()):
            return _error(403, "protected_origin")
        try:
            kind, encoded = request.headers.get("authorization", "").split(" ", 1)
            if kind.lower() != "basic":
                raise ValueError
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            return _error(401, "authentication_required", challenge=True)
        expected = f"{config.username}:{config.password}".encode()
        if not secrets.compare_digest(decoded, expected):
            return _error(401, "authentication_required", challenge=True)
        origin = request.headers.get("origin")
        # Mirror the Worker exception, without turning external API access into
        # an allowed request or weakening the shared-login/proxy-secret checks.
        landing_navigation = (
            request.method in {"GET", "HEAD"}
            and path == ""
            and request.headers.get("sec-fetch-mode") == "navigate"
            and request.headers.get("sec-fetch-dest") == "document"
        )
        if (
            (origin and origin != config.public_origin)
            or (
                request.headers.get("sec-fetch-site") == "cross-site"
                and not landing_navigation
            )
        ):
            return _error(403, "origin_not_allowed")
        if request.method not in {"GET", "HEAD", "POST"}:
            return _error(405, "method_not_allowed")
        if path and not path.startswith(("api/", "assets/")):
            return _error(404, "not_found")
        if request.method == "POST" and not path.startswith("api/"):
            return _error(405, "method_not_allowed")
        length = request.headers.get("content-length")
        if length is not None:
            try:
                if int(length) < 0 or int(length) > MAX_BODY:
                    return _error(413, "body_too_large")
            except ValueError:
                return _error(400, "invalid_length")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return _error(413, "body_too_large")
        headers = {
            key: value for key, value in request.headers.items()
            if key.lower() in PASS_HEADERS
        }
        # Never forward user-supplied authorization, gateway or proxy headers.
        headers["x-greenhome-gateway"] = config.gateway_token
        raw_path = request.scope.get("raw_path", b"/")
        query = request.scope.get("query_string", b"")
        target = httpx.URL(config.backend_url).copy_with(
            raw_path=raw_path + (b"?" + query if query else b""),
        )
        # FastAPI's landing handler is GET-only. Serve HEAD with the same
        # authenticated representation, but without returning a response body.
        upstream_method = "GET" if request.method == "HEAD" and path == "" else request.method
        try:
            async with app.state.client.stream(
                upstream_method, target, headers=headers, content=bytes(body),
            ) as upstream:
                # Do not let credentials or cookies follow a redirect.
                if 300 <= upstream.status_code < 400 and upstream.status_code != 304:
                    return _error(502, "unexpected_upstream_redirect")
                content = bytearray()
                async for chunk in upstream.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE:
                        return _error(502, "upstream_response_too_large")
                response = Response(
                    b"" if request.method == "HEAD" else bytes(content),
                    status_code=upstream.status_code,
                )
                response.raw_headers = [
                    (key, value) for key, value in upstream.headers.raw
                    if key.decode("ascii").lower() not in DROP_RESPONSE
                    and key.decode("ascii").lower() != "cache-control"
                ]
                response.headers["Cache-Control"] = "no-store"
                response.headers["Vary"] = ", ".join(dict.fromkeys([
                    *[value.strip() for value in response.headers.get("Vary", "").split(",") if value.strip()],
                    *FETCH_VARY.split(", "),
                ]))
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["Referrer-Policy"] = "no-referrer"
                return response
        except httpx.HTTPError:
            return _error(502, "upstream_unavailable")

    return app


def app_factory():
    """Uvicorn factory; the launcher supplies only the required private values."""
    return create_gateway(GatewayConfig(
        public_origin=os.environ["GREENHOME_CF_PUBLIC_ORIGIN"],
        proxy_secret=os.environ["GREENHOME_CF_PROXY_SECRET"],
        username=os.environ["GREENHOME_DEMO_USERNAME"],
        password=os.environ["GREENHOME_DEMO_PASSWORD"],
        gateway_token=os.environ["GREENHOME_GATEWAY_TOKEN"],
        backend_url=os.environ.get("GREENHOME_CF_BACKEND", "http://127.0.0.1:8002"),
    ))
