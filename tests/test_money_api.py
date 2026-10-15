"""Standalone router contract using the real HomeInput, without provider calls."""
import asyncio
from copy import deepcopy
from functools import partial
import inspect
import json
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pytest

from greenhome.api import HomeInput
from greenhome import engine, money_api
from greenhome.money_api import make_money_router
from greenhome.security import ServiceBusy
from greenhome.service import CalculationService


@pytest.fixture
def client():
    app = FastAPI()
    calculations = CalculationService(workers=1, capacity=8)
    app.include_router(make_money_router(HomeInput, run_calculation=calculations.run))
    try:
        with TestClient(app) as connection:
            yield connection
    finally:
        calculations.close()


def payload():
    return {
        "home": deepcopy(engine.demo_homes()[0]),
        "selected_retrofits": ["loft_insulation", "heat_pump"],
        "tariffs": {"electricity_pence": 25, "gas_pence": 7, "source": "illustrative"},
    }


def test_money_endpoint_has_validated_numeric_contract(client):
    response = client.post("/api/money-plan", json=payload())
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"money", "packages", "picks", "tariffs", "warnings"}
    assert result["money"]["total"] == {"before_gbp": 2040, "after_gbp": 1946, "saving_gbp": 94}
    assert result["money"]["electricity"]["saving_gbp"] == -578
    assert result["money"]["cost_gbp"] == [9800, 16600]
    assert result["tariffs"]["electricity_pence"] == 25
    assert response.headers["cache-control"] == "no-store"


def test_missing_unit_fields_are_valid_unknowns_and_do_not_select_bills(client):
    body = payload()
    body["tariffs"] = {}
    response = client.post("/api/money-plan", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["money"]["total"] == {"before_gbp": None, "after_gbp": None, "saving_gbp": None}
    assert data["picks"]["bills"] is None
    assert data["tariffs"]["source"] == "user_entered"


def test_zero_and_dated_user_entered_tariffs_remain_explicit(client):
    body = payload()
    body["tariffs"] = {"electricity_pence": 0, "gas_pence": 0,
                       "source": "user_entered", "as_of": "2026-10-15"}
    response = client.post("/api/money-plan", json=body)
    assert response.status_code == 200
    assert response.json()["money"]["status"] == "available"
    assert response.json()["money"]["total"]["before_gbp"] == 0
    assert response.json()["tariffs"]["as_of"] == "2026-10-15"


@pytest.mark.parametrize("field,value", [
    ("electricity_pence", True), ("gas_pence", "7"), ("gas_pence", -1),
    ("electricity_pence", 201), ("source", "current_price_cap"),
    ("as_of", "2026-02-30"), ("as_of", 123),
    ("gas_standing_after_pence_per_day", 1001),
    ("electricity_standing_before_pence_per_day", False),
    ("PRIVATE_FIELD_MUST_NOT_ECHO", "PRIVATE_VALUE_MUST_NOT_ECHO"),
])
def test_tariff_errors_are_safe_422s_without_echoing_input(client, field, value):
    body = payload()
    body["tariffs"][field] = value
    response = client.post("/api/money-plan", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_money_input"
    assert "PRIVATE_" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_numbers_are_rejected_safely(client, bad):
    body = json.dumps(payload()).replace('"electricity_pence": 25', '"electricity_pence": ' + bad)
    response = client.post("/api/money-plan", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_money_input"
    assert bad not in response.text


@pytest.mark.parametrize("field,value", [
    ("electricity_kwh", True), ("electricity_kwh", "4800"),
    ("budget_gbp", -1), ("floor_area_m2", 0),
    ("property_id", "PRIVATE_VALUE_MUST_NOT_ECHO /"),
    ("PRIVATE_FIELD_MUST_NOT_ECHO", "PRIVATE_VALUE_MUST_NOT_ECHO"),
])
def test_home_validation_reuses_existing_strict_home_model(client, field, value):
    body = payload()
    body["home"][field] = value
    response = client.post("/api/money-plan", json=body)
    assert response.status_code == 422
    assert "PRIVATE_" not in response.text


@pytest.mark.parametrize("selected", [None, "heat_pump", ["unknown"], ["heat_pump"] * 6, [True]])
def test_selection_reuses_existing_bounded_package_schema(client, selected):
    body = payload()
    body["selected_retrofits"] = selected
    assert client.post("/api/money-plan", json=body).status_code == 422


@pytest.mark.parametrize("field", ["home", "tariffs", "selected_retrofits"])
def test_request_requires_each_top_level_field(client, field):
    body = payload()
    del body[field]
    assert client.post("/api/money-plan", json=body).status_code == 422


def test_infeasible_or_overbudget_selection_returns_safe_domain_error(client):
    body = payload()
    body["home"]["budget_gbp"] = 1000
    response = client.post("/api/money-plan", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_scenario"
    assert "DEMO-01" not in response.text


def test_duplicate_selection_matches_engine_normalization(client):
    body = payload()
    body["selected_retrofits"] = ["heat_pump", "loft_insulation", "heat_pump"]
    result = client.post("/api/money-plan", json=body)
    assert result.status_code == 200
    assert result.json()["money"]["cost_gbp"] == [9800, 16600]


def test_empty_home_keeps_unknown_energy_and_payback(client):
    response = client.post("/api/money-plan", json={
        "home": {}, "selected_retrofits": [], "tariffs": payload()["tariffs"],
    })
    assert response.status_code == 200
    result = response.json()
    assert result["money"]["status"] == "unavailable"
    assert result["money"]["payback_years"] is None
    assert result["picks"]["bills"] is None


def test_malformed_json_uses_same_safe_error_shape(client):
    response = client.post("/api/money-plan", content='{"PRIVATE_VALUE_MUST_NOT_ECHO"',
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "PRIVATE_" not in response.text
    assert response.json()["detail"]["code"] == "invalid_money_input"


def test_factory_exposes_openapi_response_schema_without_circular_api_import(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/money-plan"]["post"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert "MoneyPlanResponse" in schema["components"]["schemas"]


def test_openapi_tariffs_advertise_only_numbers_or_null_with_real_bounds(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    tariff = schemas["TariffInput"]["properties"]
    for field, schema in tariff.items():
        if "pence" not in field:
            continue
        assert {variant["type"] for variant in schema["anyOf"]} == {"number", "null"}
        number = next(variant for variant in schema["anyOf"] if variant["type"] == "number")
        assert number["minimum"] == 0
        assert number["maximum"] == (1000 if "standing" in field else 200)


def test_requests_never_use_model_loading_or_provider_transport(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Money endpoint must not use the model-loading assess path.")

    monkeypatch.setattr(engine, "assess", forbidden)
    assert client.post("/api/money-plan", json=payload()).json()["money"]["total"]["saving_gbp"] == 94


def test_standalone_admission_denial_never_enters_money_calculation(monkeypatch):
    entered = []
    admitted_services = []
    real_money = money_api.money_plan

    def observed_money(*args):
        entered.append(True)
        return real_money(*args)

    async def denied(service, function, *args, **kwargs):
        admitted_services.append(service)
        raise ServiceBusy("PRIVATE_CAPACITY_DETAIL")

    monkeypatch.setattr(money_api, "money_plan", observed_money)
    monkeypatch.setattr(CalculationService, "run", denied)
    app = FastAPI()
    app.include_router(make_money_router(HomeInput))
    with TestClient(app) as connection:
        response = connection.post("/api/money-plan", json=payload())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "service_busy"
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE_" not in response.text
    assert entered == []
    assert len(admitted_services) == 1
    assert admitted_services[0].closed


def test_injected_runner_is_awaited_off_event_loop_and_remains_parent_owned(monkeypatch):
    service = CalculationService(workers=1, capacity=1)
    threads = []
    real_money = money_api.money_plan

    def observed_money(*args):
        threads.append(threading.current_thread().name)
        return real_money(*args)

    monkeypatch.setattr(money_api, "money_plan", observed_money)
    router = make_money_router(HomeInput, run_calculation=service.run)
    app = FastAPI()
    app.include_router(router)
    try:
        with TestClient(app) as connection:
            response = connection.post("/api/money-plan", json=payload())
        assert response.status_code == 200
        assert response.json()["money"]["total"]["saving_gbp"] == 94
        assert inspect.iscoroutinefunction(router.routes[0].endpoint)
        assert len(threads) == 1 and threads[0].startswith("home-calc")
        assert not service.closed
        assert service.pending == 0
    finally:
        service.close()


@pytest.mark.parametrize("capacity", [1, 2], ids=["admission-denied", "queued-deadline"])
def test_busy_or_queued_timeout_does_not_enter_money_calculation(monkeypatch, capacity):
    release, started = threading.Event(), threading.Event()
    entered = []
    real_money = money_api.money_plan

    def occupy_worker():
        started.set()
        assert release.wait(5), "Test did not release its worker."

    def observed_money(*args):
        entered.append(True)
        return real_money(*args)

    monkeypatch.setattr(money_api, "money_plan", observed_money)

    async def exercise():
        service = CalculationService(workers=1, capacity=capacity)
        active = asyncio.create_task(service.run(occupy_worker))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            app = FastAPI()
            app.include_router(make_money_router(
                HomeInput, run_calculation=partial(service.run, timeout=0.02),
            ))
            async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as connection:
                response = await connection.post("/api/money-plan", json=payload())
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "service_busy"
            assert response.headers["cache-control"] == "no-store"
            assert entered == []
            assert service.pending == 1
        finally:
            release.set()
            await active
            service.close()
        # A timed-out queued calculation must not start when the worker frees.
        assert entered == []

    asyncio.run(exercise())


def test_active_timeout_retains_admission_until_money_finishes(monkeypatch):
    release, started = threading.Event(), threading.Event()
    entered = []
    real_money = money_api.money_plan

    def slow_money(*args):
        entered.append(True)
        started.set()
        assert release.wait(5), "Test did not release its calculator."
        return real_money(*args)

    monkeypatch.setattr(money_api, "money_plan", slow_money)

    async def exercise():
        service = CalculationService(workers=1, capacity=1)
        try:
            app = FastAPI()
            app.include_router(make_money_router(
                HomeInput, run_calculation=partial(service.run, timeout=0.05),
            ))
            async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as connection:
                first = await connection.post("/api/money-plan", json=payload())
                assert started.is_set() and service.pending == 1
                second = await connection.post("/api/money-plan", json=payload())
            assert first.status_code == second.status_code == 503
            assert first.json()["detail"]["code"] == second.json()["detail"]["code"] == "service_busy"
            assert entered == [True]
            assert service.pending == 1
        finally:
            release.set()
            for _ in range(200):
                if service.pending == 0:
                    break
                await asyncio.sleep(0.01)
            service.close()
        assert service.pending == 0

    asyncio.run(exercise())


def test_standalone_pool_is_bounded_and_closed_with_router_lifespan(monkeypatch):
    services = []
    original_run = CalculationService.run

    async def observed_run(service, function, *args, **kwargs):
        services.append(service)
        return await original_run(service, function, *args, **kwargs)

    monkeypatch.setattr(CalculationService, "run", observed_run)
    app = FastAPI()
    app.include_router(make_money_router(HomeInput))
    with TestClient(app) as connection:
        response = connection.post("/api/money-plan", json=payload())
        assert response.status_code == 200
        assert response.json()["money"]["total"]["saving_gbp"] == 94
        assert len(services) == 1 and services[0].capacity == 8
        assert not services[0].closed
    assert services[0].closed
