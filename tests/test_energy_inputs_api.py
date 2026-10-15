from datetime import date

from fastapi.testclient import TestClient
import pytest

from greenhome import api


def csv_text():
    return "month,electricity_kwh,gas_kwh\n" + "\n".join(
        f"2025-{month:02d},100,200" for month in range(1,13)
    )


def test_energy_input_preview_does_not_save_home_or_call_provider(monkeypatch):
    monkeypatch.setattr(api, "xkiro_transport", lambda *a: pytest.fail("No provider on ingestion"))
    c=TestClient(api.create_app(load_environment=False))
    response=c.post("/api/energy-inputs",json={"csv_text":csv_text(),"end_month":"2025-12"})
    assert response.status_code==200
    out=response.json()
    assert out["electricity_kwh"]==1200
    assert out["gas_kwh"]==2400 and out["purchased_kwh"]==3600
    assert out["status"]=="complete"
    assert len(out["months"])==12
    assert c.get("/api/workspace/session").json() is None


@pytest.mark.parametrize("change", [
    {"end_month":"2025-13"}, {"end_month":"2999-12"}, {"csv_text":"month,secret\n2025-01,1"},
    {"csv_text":csv_text()+"\n2025-01,1,2"}, {"csv_text":csv_text().replace("100","=SECRET()",1)},
    {"csv_text":csv_text(),"untrusted":"extra"},
])
def test_bad_import_has_sanitised_error(change):
    c=TestClient(api.create_app(load_environment=False))
    r=c.post("/api/energy-inputs",json={"csv_text":csv_text(),"end_month":"2025-12",**change})
    assert r.status_code==422
    assert "SECRET()" not in r.text


def test_partial_import_returns_unknown_not_zero():
    c=TestClient(api.create_app(load_environment=False))
    text=csv_text().replace("2025-04,100,200","2025-04,100,")
    r=c.post("/api/energy-inputs",json={"csv_text":text,"end_month":"2025-12"}).json()
    assert r["status"]=="partial" and r["gas_kwh"] is None
    assert r["electricity_kwh"]==1200 and r["purchased_kwh"] is None
    assert r["coverage"]["gas_months"]==11
