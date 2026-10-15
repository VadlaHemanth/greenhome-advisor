"""Pilot deployment controls with synthetic keys and no outbound calls."""
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from greenhome import api, explain
from greenhome.security import PilotBoundary, ServiceBusy, WorkSlots, enabled


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    for k in ("GEMINI_API_KEY", "GEMINI_KEY", "GREENHOME_PUBLIC_MODE",
              "GREENHOME_LIVE_GEMINI", "GREENHOME_GATEWAY_TOKEN",
              "GREENHOME_ALLOWED_HOSTS", "GREENHOME_ALLOWED_ORIGINS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(explain, "load_environment", lambda: None)


def test_public_live_requires_gateway(monkeypatch):
    monkeypatch.setenv("GREENHOME_PUBLIC_MODE", "true")
    monkeypatch.setenv("GREENHOME_LIVE_GEMINI", "true")
    with pytest.raises(RuntimeError):
        api.create_app(load_environment=False)


def test_boolean_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("GREENHOME_PUBLIC_MODE", "true ")
    assert enabled("GREENHOME_PUBLIC_MODE")
    monkeypatch.setenv("GREENHOME_PUBLIC_MODE", "tru")
    with pytest.raises(ValueError):
        api.create_app(load_environment=False)
    monkeypatch.setenv("GREENHOME_PUBLIC_MODE", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "FAKE-NEVER-CALL")
    assert TestClient(api.create_app(load_environment=False)).get("/api/health").json()["gemini_configured"] is False


def test_public_default_disables_live_and_schema(monkeypatch):
    monkeypatch.setenv("GREENHOME_PUBLIC_MODE", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "FAKE-DO-NOT-USE")
    c = TestClient(api.create_app(load_environment=False))
    assert c.get("/api/health").json()["gemini_configured"] is False
    assert c.get("/openapi.json").status_code == 404


def test_public_missing_token_never_invokes_provider(monkeypatch):
    monkeypatch.setenv("GREENHOME_PUBLIC_MODE", "true")
    monkeypatch.setenv("GREENHOME_LIVE_GEMINI", "true")
    monkeypatch.setenv("GREENHOME_GATEWAY_TOKEN", "x" * 40)
    monkeypatch.setattr(explain, "_sdk_transport", lambda *a: pytest.fail("No provider call permitted"))
    c = TestClient(api.create_app(load_environment=False))
    r = c.post("/api/what-if", json={"home": {}, "question": "Explain my score", "use_gemini": True})
    assert r.status_code == 403
    assert "x" * 40 not in r.text


def test_host_origin_content_type_controls():
    c = TestClient(api.create_app(load_environment=False))
    assert c.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    assert c.post("/api/assess", json={"home": {}}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/assess", content="{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert c.post("/api/assess", json={"home": {}}, headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_private_files_not_served():
    c = TestClient(api.create_app(load_environment=False))
    for path in ("/.env", "/models/energy_benchmark.joblib", "/greenhome/api.py",
                 "/api/not-a-route", "/assets/%2e%2e/%2e%2e/.env"):
        assert c.get(path).status_code in (404, 400)


def test_security_headers():
    r = TestClient(api.create_app(load_environment=False)).get("/api/health")
    assert r.headers["x-frame-options"] == "DENY"
    assert "object-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_compiled_asset_cache_and_private_api_cache():
    built = api.ROOT / "frontend" / "dist" / "assets"
    scripts = list(built.glob("index-*.js")) if built.is_dir() else []
    if not scripts:
        pytest.skip("Build the frontend to check the compiled asset policy.")
    c = TestClient(api.create_app(load_environment=False))
    response = c.get("/assets/" + scripts[0].name)
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]
    assert response.headers.get("content-encoding") == "gzip"
    assert c.get("/api/health").headers["cache-control"] == "no-store"


def test_rate_limiter_is_finite():
    guard = PilotBoundary(None, [])
    assert guard.allowed("client", "test", 2)
    assert guard.allowed("client", "test", 2)
    assert not guard.allowed("client", "test", 2)


def test_work_slots_reject_excess_without_queue():
    slots = WorkSlots(1)
    with slots.claim():
        with pytest.raises(ServiceBusy):
            with slots.claim():
                pass
    with slots.claim():
        pass


def test_provider_timeout_keeps_real_worker_slot(monkeypatch):
    monkeypatch.setattr(explain, "_PROVIDER_SLOTS", threading.BoundedSemaphore(1))
    release = threading.Event()
    ended = threading.Event()
    def delayed(*args):
        try:
            release.wait(2)
            return {}
        finally:
            ended.set()
    try:
        with pytest.raises(explain.RequestTimeout):
            explain._bounded_call(delayed, "", {}, time.monotonic() + .03)
        with pytest.raises(explain.ProviderBusy):
            explain._bounded_call(delayed, "", {}, time.monotonic() + .1)
    finally:
        release.set()
        ended.wait(2)


def test_quota_errors_are_safe():
    error = RuntimeError("SECRET PROVIDER DETAIL")
    error.code = 402
    assert explain._failure_status(error) == "fallback_quota"
    assert "SECRET" not in explain.STATUS_MESSAGES["fallback_quota"]


def test_thread_start_failure_does_not_consume_slots(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(explain, "_PROVIDER_SLOTS", slots)
    class BadThread:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            raise RuntimeError("cannot start thread")
    with monkeypatch.context() as m:
        m.setattr(explain.threading, "Thread", BadThread)
        for _ in range(2):
            with pytest.raises(RuntimeError):
                explain._bounded_call(lambda *args: {}, "", {}, time.monotonic()+1)
    assert explain._bounded_call(lambda *args: {"ok": True}, "", {}, time.monotonic()+1) == {"ok": True}


def test_slow_body_times_out_without_dispatch(monkeypatch):
    import asyncio
    monkeypatch.setattr(api, "BODY_READ_TIMEOUT_SECONDS", .025)
    sent = []
    async def target(*args):
        pytest.fail("Unfinished body must not reach routing")
    async def receive():
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"", "more_body": True}
    async def send(message):
        sent.append(message)
    asyncio.run(api.RequestBoundary(target)(
        {"type": "http", "method": "POST", "path": "/api/assess", "headers": []},
        receive, send))
    assert next(m for m in sent if m["type"] == "http.response.start")["status"] == 408
