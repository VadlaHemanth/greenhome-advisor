"""Offline gateway checks. No Cloudflare, model, provider or saved-state calls."""
import base64
from dataclasses import replace

from fastapi.testclient import TestClient
import httpx
import pytest

from greenhome.cloudflare_gateway import GatewayConfig, MAX_BODY, create_gateway

CONFIG = GatewayConfig(
    "https://greenhome.pages.dev", "p" * 40, "team225", "test-password-only",
    "g" * 40,
)
AUTH = "Basic " + base64.b64encode(b"team225:test-password-only").decode()
HEADERS = {"X-GreenHome-Proxy": CONFIG.proxy_secret, "Authorization": AUTH}


def client_for(handler):
    return TestClient(create_gateway(CONFIG, transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("headers,status", [
    ({}, 403),
    ({"X-GreenHome-Proxy": "wrong"}, 403),
    ({"X-GreenHome-Proxy": CONFIG.proxy_secret}, 401),
    ({**HEADERS, "Authorization": "Bearer wrong"}, 401),
    ({**HEADERS, "Authorization": "Basic !!"}, 401),
    ({**HEADERS, "Authorization": "Basic d3Jvbmc="}, 401),
    ({**HEADERS, "Origin": "https://untrusted.example"}, 403),
    ({**HEADERS, "Sec-Fetch-Site": "cross-site"}, 403),
])
def test_reject_before_backend(headers, status):
    def forbidden(request):
        pytest.fail("Unauthenticated or cross-origin request reached backend")
    with client_for(forbidden) as client:
        response = client.get("/api/health", headers=headers)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert CONFIG.proxy_secret not in response.text
    assert CONFIG.gateway_token not in response.text
    if status == 401:
        assert response.headers["www-authenticate"].startswith("Basic ")


def test_forward_safe_headers_query_and_multiple_cookies():
    def backend(request):
        assert str(request.url) == "http://127.0.0.1:8002/api/workspace/session?check=1"
        assert request.headers["x-greenhome-gateway"] == CONFIG.gateway_token
        assert request.headers["origin"] == CONFIG.public_origin
        assert request.headers["cookie"] == "__Host-greenhome_workspace=fictional"
        for field in ("authorization", "x-greenhome-proxy", "forwarded", "x-forwarded-proto"):
            assert field not in request.headers
        return httpx.Response(200, json={"ok": True}, headers=[
            ("Set-Cookie", "__Host-a=a; Secure; HttpOnly; Path=/; SameSite=Strict"),
            ("Set-Cookie", "__Host-b=b; Secure; HttpOnly; Path=/; SameSite=Strict"),
        ])
    with client_for(backend) as client:
        response = client.get("/api/workspace/session?check=1", headers={
            **HEADERS, "Origin": CONFIG.public_origin,
            "Cookie": "__Host-greenhome_workspace=fictional",
            "X-GreenHome-Gateway": "attacker", "Forwarded": "spoof",
            "X-Forwarded-Proto": "https",
        })
    assert response.status_code == 200
    assert len(response.headers.get_list("set-cookie")) == 2


@pytest.mark.parametrize("path", ["/.env", "/models/model.joblib", "/greenhome/api.py", "/openapi.json"])
def test_private_path_block(path):
    with client_for(lambda r: pytest.fail("private path forwarded")) as client:
        assert client.get(path, headers=HEADERS).status_code == 404


def test_body_bounds_and_duplicate_credentials():
    with client_for(lambda r: pytest.fail("invalid body forwarded")) as client:
        assert client.post("/api/assess", headers=HEADERS, content=b"x" * (MAX_BODY + 1)).status_code == 413
        assert client.get("/api/health", headers=[*HEADERS.items(), ("Authorization", AUTH)]).status_code == 400
        assert client.delete("/api/workspace", headers=HEADERS).status_code == 405


def test_upstream_redirect_and_transport_error_sanitized():
    with client_for(lambda r: httpx.Response(302, headers={"Location": "https://untrusted.example"})) as client:
        assert client.get("/", headers=HEADERS).status_code == 502
    def broken(request):
        raise httpx.ConnectError(CONFIG.gateway_token, request=request)
    with client_for(broken) as client:
        response = client.get("/", headers=HEADERS)
        assert response.status_code == 502
        assert CONFIG.gateway_token not in response.text


def test_post_body_preserved():
    def backend(request):
        assert request.content == b'{"consent":true}'
        assert request.headers["content-type"] == "application/json"
        return httpx.Response(200, json={"accepted": True})
    with client_for(backend) as client:
        assert client.post("/api/workspace", headers={**HEADERS, "Content-Type": "application/json"}, content=b'{"consent":true}').json() == {"accepted": True}


@pytest.mark.parametrize("change", [
    {"backend_url": "https://untrusted.example"},
    {"backend_url": "http://127.0.0.1:8002/path"},
    {"public_origin": "http://greenhome.pages.dev"},
    {"public_origin": "https://greenhome.pages.dev/path"},
    {"proxy_secret": "short"},
    {"password": "short"},
    {"username": "invalid:name"},
])
def test_invalid_configuration(change):
    with pytest.raises(ValueError):
        replace(CONFIG, **change)


EXTERNAL_NAVIGATION = {
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
}


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_authenticated_external_landing_navigation(method):
    def backend(request):
        assert request.url.path == "/"
        assert request.method == "GET"
        assert request.headers["x-greenhome-gateway"] == CONFIG.gateway_token
        assert request.headers["sec-fetch-site"] == "cross-site"
        return httpx.Response(200, text="GreenHome", headers={"Vary": "Accept-Encoding"})
    with client_for(backend) as client:
        response = client.request(method, "/", headers={**HEADERS, **EXTERNAL_NAVIGATION})
    assert response.status_code == 200
    assert response.content == (b"" if method == "HEAD" else b"GreenHome")
    assert "Accept-Encoding" in response.headers["vary"]
    assert "Sec-Fetch-Dest" in response.headers["vary"]


@pytest.mark.parametrize("changes,status", [
    ({"X-GreenHome-Proxy": ""}, 403),
    ({"Authorization": ""}, 401),
    ({"Authorization": "Basic d3Jvbmc="}, 401),
])
def test_external_navigation_does_not_bypass_authentication(changes, status):
    with client_for(lambda r: pytest.fail("Authentication bypass")) as client:
        response = client.get("/", headers={**HEADERS, **EXTERNAL_NAVIGATION, **changes})
    assert response.status_code == status


@pytest.mark.parametrize("path,method,changes", [
    ("/api/workspace", "GET", {}),
    ("/assets/app.js", "GET", {}),
    ("/", "POST", {}),
    ("/api/workspace", "POST", {}),
    ("/", "GET", {"Sec-Fetch-Dest": "iframe"}),
    ("/", "GET", {"Sec-Fetch-Dest": "object"}),
    ("/", "GET", {"Sec-Fetch-Dest": "embed"}),
    ("/", "GET", {"Sec-Fetch-Dest": "image"}),
    ("/", "GET", {"Sec-Fetch-Mode": "cors"}),
    ("/", "GET", {"Sec-Fetch-Mode": ""}),
    ("/", "GET", {"Sec-Fetch-Dest": ""}),
    ("/", "GET", {"Origin": "https://other.example"}),
    ("/", "GET", {"Origin": "null"}),
])
def test_external_requests_outside_landing_exception_stay_blocked(path, method, changes):
    with client_for(lambda r: pytest.fail("Cross-site request reached backend")) as client:
        response = client.request(method, path, headers={**HEADERS, **EXTERNAL_NAVIGATION, **changes})
    assert response.status_code == 403


@pytest.mark.parametrize("header,value", [
    ("Sec-Fetch-Site", "same-origin"),
    ("Sec-Fetch-Mode", "navigate"),
    ("Sec-Fetch-Dest", "document"),
])
def test_duplicate_fetch_metadata_rejected(header, value):
    with client_for(lambda r: pytest.fail("Ambiguous metadata forwarded")) as client:
        response = client.get("/", headers=[
            *HEADERS.items(), *EXTERNAL_NAVIGATION.items(), (header, value),
        ])
    assert response.status_code == 400
