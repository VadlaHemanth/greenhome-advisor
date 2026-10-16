"""Public catalogue routing and unchanged private workspace boundaries."""
from fastapi.testclient import TestClient
import pytest

from greenhome import api, engine


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("GREENHOME_PUBLIC_MODE", "false")
    monkeypatch.setenv("GREENHOME_LIVE_GEMINI", "false")
    monkeypatch.setenv("GREENHOME_LIVE_LLM", "false")
    monkeypatch.setenv("GREENHOME_WORKSPACE_DATABASE_URL", f"sqlite:///{tmp_path}/workspace.sqlite3")
    with TestClient(api.create_app(load_environment=False)) as connection:
        yield connection


def test_catalogue_is_public_bounded_and_keeps_original_seed_endpoint(client):
    response = client.get("/api/demo-catalogue")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 200 and len(data["entries"]) == 12
    assert data["provenance"]["synthetic"] is True
    assert "no-store" in response.headers["cache-control"]
    assert client.get("/api/demo-homes").json() == engine.demo_homes()


def test_catalogue_does_not_enlarge_or_create_saved_workspaces(client):
    assert client.get("/api/workspace/session").json() is None
    response = client.get("/api/demo-catalogue?page=17")
    assert response.status_code == 200
    assert len(response.json()["entries"]) == 8
    assert client.get("/api/workspace/session").json() is None
    saved = client.post("/api/workspace", json={"consent": True})
    assert saved.status_code == 200
    assert len(saved.json()["customers"]) == 4
    assert all(len(c["properties"]) == 1 for c in saved.json()["customers"])


def test_arbitrary_ranking_limit_remains_100_and_catalogue_queries_are_bounded(client):
    homes = [{**engine.demo_homes()[0], "property_id": f"CHECK-{i}"} for i in range(101)]
    assert client.post("/api/rank-homes", json={"homes": homes}).status_code == 422
    for path in ("?page_size=25", "?page=0", "?q=" + "x" * 101, "?property_type=Castle"):
        assert client.get("/api/demo-catalogue" + path).status_code == 422
