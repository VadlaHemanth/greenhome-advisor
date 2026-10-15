from fastapi.testclient import TestClient
import pytest

from greenhome import api, readiness


@pytest.mark.parametrize("ready", [True, False])
def test_readiness_route_has_meaningful_http_status(monkeypatch, ready):
    result = {
        "status": "ready" if ready else "not_ready",
        "checks": {"frontend": ready, "model_integrity": ready, "local_inference": ready},
        "live_provider_tested": False,
        "note": "Local deployment checks only.",
    }
    class Checker:
        def check(self):
            return result
    monkeypatch.setattr(readiness, "Readiness", Checker)
    c = TestClient(api.create_app(load_environment=False))
    response = c.get("/api/readiness")
    assert response.status_code == (200 if ready else 503)
    assert response.json() == result
