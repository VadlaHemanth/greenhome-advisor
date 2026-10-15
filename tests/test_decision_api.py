from fastapi.testclient import TestClient
from greenhome.api import create_app
from greenhome.engine import demo_homes


def test_decision_route_complete_and_missing():
    client = TestClient(create_app(load_environment=False))
    h = {**demo_homes()[0], "budget_gbp": 7350}
    r = client.post("/api/decision-check", json={"home": h})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "available"
    assert 1 <= d["feasible_package_count"] <= 32
    assert d["scenario_count"] in (27, 28)
    assert d["regret_kwh"] >= 0
    assert isinstance(d["next_check"]["question"], str)
    missing = client.post("/api/decision-check", json={"home": {**h, "gas_kwh": None}})
    assert missing.status_code == 200
    assert missing.json()["status"] == "unavailable"
    assert missing.json()["recommended_package"] is None
