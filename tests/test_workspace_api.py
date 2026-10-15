"""Offline fictional memory integration; no main-app edits or provider calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import sqlite3
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from greenhome import engine, explain
from greenhome.api import HomeInput
from greenhome.workspace_api import COOKIE_NAME, PUBLIC_COOKIE_NAME, create_workspace_router
from greenhome.workspace_store import TTL_SECONDS

BASE = "/api/workspace"
NOW = int(datetime(2026, 10, 10, 12, tzinfo=timezone.utc).timestamp())


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setitem(sys.modules, "greenhome.ml", SimpleNamespace(
        predict_energy_benchmark=lambda home: None,
        predict_value_impact=lambda home, selected: {
            "status": "unavailable", "low_gbp": None, "high_gbp": None,
            "low_percent": None, "high_percent": None, "note": "Offline fictional test.",
        },
    ))

    def forbidden(*args, **kwargs):
        pytest.fail("Workspace memory must not call Gemini.")

    monkeypatch.setattr(explain, "_sdk_transport", forbidden)


@pytest.fixture
def build(monkeypatch, tmp_path):
    path = tmp_path / "state" / "workspaces.sqlite3"
    monkeypatch.setenv("GREENHOME_WORKSPACE_DATABASE_URL", f"sqlite:///{path}")
    monkeypatch.setenv("GREENHOME_WORKSPACE_MAX_WORKSPACES", "1000")
    monkeypatch.setenv("GREENHOME_WORKSPACE_MAX_CREATIONS_PER_DAY", "1000")
    routers = []

    def factory(*, public=False):
        monkeypatch.setenv("GREENHOME_PUBLIC_MODE", str(public).lower())
        app = FastAPI()

        def not_a_persistence_calculation(homes):
            pytest.fail("Persistence must not persist derived rankings or make duplicate ranking calls.")

        router = create_workspace_router(HomeInput, not_a_persistence_calculation)
        router.workspace_store.clock = lambda: NOW
        routers.append(router)
        app.include_router(router)
        return TestClient(app, base_url="https://testserver" if public else "http://testserver"), router.workspace_store

    yield factory, path
    for router in routers:
        router.workspace_store.close()


@pytest.fixture
def session(build):
    factory, _ = build
    client, store = factory()
    with client:
        response = client.post(BASE, json={"consent": True})
        assert response.status_code == 200
        yield client, store, response.json()


def payload(customer, **changes):
    result = {key: deepcopy(customer[key]) for key in (
        "version", "home", "preferences", "selected_retrofits", "review_status",
    )}
    result.update(changes)
    return result


def save(client, customer, **changes):
    return client.post(f"{BASE}/customers/{customer['id']}", json=payload(customer, **changes))


def completion(client, customer, **changes):
    data = {"version": customer["version"], "kind": "completed",
            "retrofit_id": "loft_insulation", "completed_on": "2026-10-10", "confirmed": True}
    data.update(changes)
    return client.post(f"{BASE}/customers/{customer['id']}/events", json=data)


def test_session_probe_is_nullable_but_private_reads_still_require_cookie(build):
    factory, _ = build
    client, _ = factory()
    assert client.get(BASE + "/session").status_code == 200
    assert client.get(BASE + "/session").json() is None
    assert client.get(BASE).status_code == 401
    assert client.get(BASE + "/export").status_code == 401
    saved = client.post(BASE, json={"consent": True}).json()
    assert client.get(BASE + "/session").json() == saved
    client.post(BASE + "/delete", json={"confirm": True})
    assert client.get(BASE + "/session").json() is None


def test_session_probe_clears_invalid_cookie_without_disclosing_records(build):
    factory, _ = build
    client, _ = factory()
    response = client.get(BASE + "/session", headers={"cookie":f"{COOKIE_NAME}=unrecognised"})
    assert response.status_code == 200 and response.json() is None
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_explicit_opt_in_only_and_exact_public_schema(build):
    factory, path = build
    with factory()[0] as client:
        assert client.get(BASE).status_code == 401
        assert client.get(BASE + "/export").status_code == 401
        for consent in (False, 1, "true", None):
            assert client.post(BASE, json={"consent": consent}).status_code == 422
        assert client.post(BASE, json={}).status_code == 422
        assert not path.exists()
        response = client.post(BASE, json={"consent": True})
        assert response.status_code == 200
        workspace = response.json()
        assert set(workspace) == {"id", "schema_version", "mode", "expires_at", "customers", "note"}
        assert workspace["schema_version"] == 2
        assert workspace["mode"] == "fictional_demo"
        assert len(workspace["customers"]) == 4
        for i, customer in enumerate(workspace["customers"], 1):
            assert set(customer) == {
                "id", "label", "version", "home", "preferences", "selected_retrofits",
                "review_status", "baseline_status", "events", "updated_at",
                "customer_preferences", "portfolio_budget_gbp", "legacy_completed_reserve_gbp",
                "budget_summary", "properties",
            }
            assert len(customer["properties"]) == 1
            prop = customer["properties"][0]
            assert prop["customer_id"] == customer["id"]
            for field in ("home", "preferences", "selected_retrofits", "review_status", "baseline_status", "events"):
                assert prop[field] == customer[field]
            assert customer["label"] == f"Example household {i}"
            assert customer["home"]["property_id"] == f"DEMO-0{i}"
            assert customer["home"]["data_kind"] == "synthetic_demo"
            assert customer["version"] == 1
            assert customer["events"] == []
            assert customer["baseline_status"] == "current"
        assert client.post(BASE, json={"consent": True}).json() == workspace
        assert len(client.cookies.get(COOKIE_NAME)) == 43
        assert path.stat().st_mode & 0o777 == 0o600
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1


def test_cookie_flags_hash_only_and_fixed_ttl(build):
    factory, path = build
    with factory()[0] as client:
        response = client.post(BASE, json={"consent": True})
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert "Max-Age=2592000" in cookie and "Path=/api/workspace" in cookie
        assert "Secure" not in cookie and "Domain=" not in cookie
        token = client.cookies.get(COOKIE_NAME)
        with sqlite3.connect(path) as db:
            stored = db.execute("SELECT token_hash, created_at, expires_at FROM workspaces").fetchone()
            dump = "\n".join(db.iterdump())
        assert stored[0] == hashlib.sha256(token.encode("ascii")).hexdigest()
        assert stored[2] - stored[1] == TTL_SECONDS
        assert token not in dump + response.text
        assert "token_hash" not in response.text
        assert "set-cookie" not in client.post(BASE, json={"consent": True}).headers
        for route in (BASE, BASE + "/export"):
            result = client.get(route)
            assert result.headers["cache-control"] == "no-store"
            assert result.headers["x-content-type-options"] == "nosniff"


def test_public_secure_host_cookie_and_no_http_access(build):
    factory, _ = build
    client, _ = factory(public=True)
    with client:
        response = client.post(BASE, json={"consent": True})
        assert response.status_code == 200
        assert response.headers["set-cookie"].startswith(PUBLIC_COOKIE_NAME + "=")
        assert all(flag in response.headers["set-cookie"] for flag in
                   ("Secure", "HttpOnly", "SameSite=strict", "Path=/", "Max-Age=2592000"))
        assert "Domain=" not in response.headers["set-cookie"]
        assert client.get("http://testserver" + BASE).status_code == 403
        deleted = client.post(BASE + "/delete", json={"confirm": True})
        assert deleted.status_code == 200
        assert "Secure" in deleted.headers["set-cookie"]
        assert "Path=/" in deleted.headers["set-cookie"] and "Max-Age=0" in deleted.headers["set-cookie"]


def test_two_private_clients_are_isolated_and_ids_are_not_credentials(build):
    factory, _ = build
    with factory()[0] as first, factory()[0] as second, factory()[0] as outsider:
        a = first.post(BASE, json={"consent": True}).json()
        b = second.post(BASE, json={"consent": True}).json()
        assert a["id"] != b["id"]
        assert first.get(BASE).json() == a
        assert second.get(BASE + "/export").json() == b
        customer_path = f"{BASE}/customers/{a['customers'][0]['id']}"
        assert first.get(customer_path).json() == a
        assert second.get(customer_path).status_code == 404
        assert outsider.get(customer_path).status_code == 401
        assert save(second, a["customers"][0]).status_code == 404
        assert completion(second, a["customers"][0]).status_code == 404
        assert save(outsider, a["customers"][0]).status_code == 401
        assert outsider.get(BASE, params={"id": a["id"]}).status_code == 422
        outsider.cookies.set(COOKIE_NAME, a["id"])
        assert outsider.get(BASE).status_code == 401
        assert second.post(BASE + "/delete", json={"confirm": True}).status_code == 200
        assert first.get(BASE).json() == a


def test_restart_restore_export_and_delete_remove_all_scoped_rows(build):
    factory, path = build
    first, store = factory()
    with first:
        workspace = first.post(BASE, json={"consent": True}).json()
        updated = save(first, workspace["customers"][0], review_status="reviewing").json()
        token = first.cookies.get(COOKIE_NAME)
    store.close()
    with factory()[0] as restarted:
        restarted.cookies.set(COOKIE_NAME, token)
        assert restarted.get(BASE).json() == updated
        export = restarted.get(BASE + "/export")
        assert export.json() == updated
        assert export.headers["content-type"] == "application/json"
        assert export.headers["content-disposition"] == 'attachment; filename="greenhome-fictional-workspace.json"'
        assert restarted.post(BASE + "/delete", json={"confirm": False}).status_code == 422
        assert restarted.get(BASE).json() == updated
        response = restarted.post(BASE + "/delete", json={"confirm": True})
        assert response.json() == {"deleted": True}
        assert "Max-Age=0" in response.headers["set-cookie"]
        assert restarted.get(BASE).status_code == 401
        restarted.cookies.set(COOKIE_NAME, token)
        assert restarted.get(BASE + "/export").status_code == 401
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM workspace_customers").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 0


def test_ttl_not_sliding_expired_cookie_revoked_without_get_writes(session, build):
    client, store, data = session
    _, path = build
    store.clock = lambda: NOW + TTL_SECONDS - 1
    assert client.get(BASE).json()["expires_at"] == data["expires_at"]
    assert save(client, data["customers"][0]).status_code == 200
    store.clock = lambda: NOW + TTL_SECONDS
    response = client.get(BASE)
    assert response.status_code == 401 and "Max-Age=0" in response.headers["set-cookie"]
    with sqlite3.connect(path) as db:
        # Expiry is immediate but physical GC is deliberately off the GET path.
        assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1
    assert store.prune_expired() == 1
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM workspace_customers").fetchone()[0] == 0
    assert client.get(BASE).status_code == 401


@pytest.mark.parametrize("trusted", [True, False, "true", 1, None])
def test_public_loopback_proxy_requires_exact_verified_scope_flag(build, trusted):
    factory, _ = build
    public, _ = factory(public=True)

    class VerifiedGatewayStub:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            # Parent owns authentication itself; this tests only the scope contract.
            scope["greenhome.authenticated_gateway"] = trusted
            await self.app(scope, receive, send)

    with TestClient(VerifiedGatewayStub(public.app), base_url="http://testserver") as client:
        response = client.post(BASE, json={"consent": True})
        assert response.status_code == (200 if trusted is True else 403)
        if trusted is True:
            assert response.headers["set-cookie"].startswith(PUBLIC_COOKIE_NAME + "=")
            assert all(flag in response.headers["set-cookie"] for flag in
                       ("Secure", "HttpOnly", "SameSite=strict", "Path=/"))
            # Browser reaches the gateway over TLS; TestClient's internal HTTP
            # link needs an explicit Cookie header to model that terminated hop.
            cookie = response.headers["set-cookie"].split(";")[0]
            assert client.get(BASE, headers={"cookie": cookie}).json() == response.json()


def test_raw_forwarded_headers_do_not_bypass_public_https_guard(build):
    factory, _ = build
    public, _ = factory(public=True)
    with TestClient(public.app, base_url="http://testserver") as client:
        response = client.post(BASE, json={"consent": True}, headers={
            "x-forwarded-proto": "https", "x-forwarded-for": "127.0.0.1",
            "forwarded": "proto=https;for=127.0.0.1",
            "greenhome.authenticated_gateway": "true",
        })
        assert response.status_code == 403
        assert PUBLIC_COOKIE_NAME not in client.cookies


def test_preferences_projection_engine_exclusions_and_per_customer_scope(session):
    client, _, workspace = session
    customer = workspace["customers"][0]
    preferences = {"budget_gbp": 5000, "deferred_retrofits": ["solar_pv", "loft_insulation"],
                   "priority": "carbon", "disruption": "minimal"}
    response = save(client, customer, preferences=preferences, selected_retrofits=["smart_controls"],
                    review_status="ready")
    assert response.status_code == 200
    result = response.json()
    changed = result["customers"][0]
    assert changed["version"] == 2
    assert changed["preferences"] == preferences
    assert changed["home"]["budget_gbp"] == 5000
    assert changed["home"]["excluded_retrofits"] == preferences["deferred_retrofits"]
    assert not set(engine.assess(changed["home"])["selected_retrofits"]) & set(preferences["deferred_retrofits"])
    assert result["customers"][1:] == workspace["customers"][1:]
    from greenhome.ranking import rank_homes
    ranked = rank_homes([changed["home"]])
    assert not set(ranked["rows"][0]["selected_retrofits"]) & set(preferences["deferred_retrofits"])
    assert changed["preferences"]["priority"] == "carbon"  # Ranking policy is still the mandated energy metric.


def test_stale_version_and_atomic_parallel_update(session, build):
    client, _, workspace = session
    factory, _ = build
    customer = workspace["customers"][0]
    token = client.cookies.get(COOKIE_NAME)
    with factory()[0] as other:
        other.cookies.set(COOKIE_NAME, token)
        with ThreadPoolExecutor(2) as pool:
            a = pool.submit(save, client, customer, review_status="ready")
            b = pool.submit(save, other, customer, review_status="deferred")
            results = [a.result(), b.result()]
    assert sorted(response.status_code for response in results) == [200, 409]
    winner = next(response.json() for response in results if response.status_code == 200)
    assert client.get(BASE).json() == winner
    assert winner["customers"][0]["version"] == 2
    assert save(client, customer).status_code == 409


def test_concurrent_delete_and_save_never_resurrects_workspace(session, build):
    client, _, workspace = session
    factory, path = build
    with factory()[0] as other:
        other.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
        with ThreadPoolExecutor(2) as pool:
            saving = pool.submit(save, other, workspace["customers"][0], review_status="ready")
            deleting = pool.submit(client.post, BASE + "/delete", json={"confirm": True})
            assert deleting.result().status_code == 200
            assert saving.result().status_code in (200, 401)
        assert other.get(BASE).status_code == 401
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM workspace_customers").fetchone()[0] == 0


def test_concurrent_completion_and_save_have_one_atomic_winner(session, build):
    client, _, workspace = session
    factory, _ = build
    selected = save(client, workspace["customers"][0], selected_retrofits=["loft_insulation"]).json()["customers"][0]
    with factory()[0] as other:
        other.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
        with ThreadPoolExecutor(2) as pool:
            completing = pool.submit(completion, client, selected)
            saving = pool.submit(save, other, selected, review_status="ready")
            results = [completing.result(), saving.result()]
    assert sorted(response.status_code for response in results) == [200, 409]
    winner = next(response.json() for response in results if response.status_code == 200)
    assert client.get(BASE).json() == winner
    assert winner["customers"][0]["version"] == 3
    if winner["customers"][0]["events"]:
        assert winner["customers"][0]["baseline_status"] == "needs_update"
        assert winner["customers"][0]["home"]["gas_kwh"] is None


@pytest.mark.parametrize("field", ["version", "home", "preferences", "selected_retrofits", "review_status"])
def test_all_update_fields_required(session, field):
    client, _, workspace = session
    customer = workspace["customers"][0]
    request = payload(customer)
    del request[field]
    assert client.post(f"{BASE}/customers/{customer['id']}", json=request).status_code == 422
    assert client.get(BASE).json() == workspace


@pytest.mark.parametrize("where,key,value", [
    ("top", "unexpected", "PRIVATE-MARKER"),
    ("home", "address", "PRIVATE-MARKER"),
    ("home", "data_kind", "user_entered"),
    ("home", "property_id", "ARBITRARY-REAL-HOUSE"),
    ("home", "property_id", "DEMO-02"),
    ("home", "excluded_retrofits", ["solar_pv", "solar_pv"]),
    ("home", "excluded_retrofits", ["unknown"]),
    ("preferences", "notes", "PRIVATE-MARKER"),
    ("preferences", "budget_gbp", True),
    ("preferences", "budget_gbp", -1),
    ("preferences", "budget_gbp", 1e10),
    ("preferences", "deferred_retrofits", ["unknown"]),
    ("preferences", "deferred_retrofits", ["solar_pv", "solar_pv"]),
    ("preferences", "priority", "market_value"),
    ("preferences", "disruption", "high"),
    ("top", "selected_retrofits", ["solar_pv", "solar_pv"]),
    ("top", "selected_retrofits", ["PRIVATE-MARKER"]),
    ("top", "selected_retrofits", ["solar_pv"] * 6),
    ("top", "review_status", "published"),
    ("top", "version", True),
    ("top", "version", 0),
    ("top", "version", 1.0),
    ("top", "baseline_confirmed_after_completion", "true"),
])
def test_invalid_fields_rejected_without_reflection_or_persistence(session, where, key, value, caplog):
    client, _, workspace = session
    customer = workspace["customers"][0]
    request = payload(customer)
    target = request if where == "top" else request[where]
    target[key] = value
    response = client.post(f"{BASE}/customers/{customer['id']}", json=request)
    assert response.status_code == 422
    assert "PRIVATE-MARKER" not in response.text + caplog.text
    assert client.get(BASE).json() == workspace


@pytest.mark.parametrize("case", ["deferred", "infeasible", "package_budget"])
def test_selection_engine_validation_and_deferrals(session, case):
    client, _, workspace = session
    customer = workspace["customers"][0]
    request = payload(customer)
    if case == "deferred":
        request["preferences"]["deferred_retrofits"] = ["solar_pv"]
        request["selected_retrofits"] = ["solar_pv"]
    elif case == "infeasible":
        request["home"]["roof_access"] = False
        request["selected_retrofits"] = ["loft_insulation"]
    else:
        request["preferences"]["budget_gbp"] = 1600
        request["selected_retrofits"] = ["loft_insulation", "smart_controls"]
    assert client.post(f"{BASE}/customers/{customer['id']}", json=request).status_code == 422
    assert client.get(BASE).json() == workspace


@pytest.mark.parametrize("rid,key,value", [
    ("loft_insulation", "insulation", "good"), ("double_glazing", "glazing", "double"),
    ("smart_controls", "smart_controls", True), ("solar_pv", "solar_kwp", 3.0),
    ("heat_pump", "heating", "heat_pump"),
])
def test_completion_updates_only_justified_feature_and_invalidates_fuels(session, rid, key, value):
    client, _, workspace = session
    old = workspace["customers"][0]
    selected = save(client, old, selected_retrofits=[rid]).json()["customers"][0]
    response = completion(client, selected, retrofit_id=rid)
    assert response.status_code == 200
    current = response.json()["customers"][0]
    expected = deepcopy(selected["home"])
    expected.update({key: value, "electricity_kwh": None, "gas_kwh": None})
    assert current["home"] == expected
    assert current["home"]["epc_rating"] == old["home"]["epc_rating"]
    assert current["baseline_status"] == "needs_update"
    assert current["version"] == 3
    assert current["selected_retrofits"] == []
    assert len(current["events"]) == 1
    event = current["events"][0]
    assert set(event) == {"id", "kind", "retrofit_id", "completed_on", "created_at", "planning_cost_upper_gbp"}
    assert event["planning_cost_upper_gbp"] == engine.RETROFITS[rid]["cost_gbp"][1]
    assert event["retrofit_id"] == rid and event["completed_on"] == "2026-10-10"
    assert client.get(BASE + "/export").json() == response.json()


def test_explicit_replacement_baseline_and_partial_fuels(session):
    client, _, workspace = session
    original = workspace["customers"][0]
    selected = save(client, original, selected_retrofits=["loft_insulation"]).json()["customers"][0]
    current = completion(client, selected).json()["customers"][0]
    replacement = deepcopy(current["home"])
    replacement.update(electricity_kwh=3000, gas_kwh=0)
    rejected = save(client, current, home=replacement)
    assert rejected.status_code == 422
    assert "post-completion" in rejected.text
    assert client.get(BASE).json()["customers"][0] == current
    partial = deepcopy(replacement)
    partial["gas_kwh"] = None
    assert save(client, current, home=partial, baseline_confirmed_after_completion=True).status_code == 422
    current = save(client, current, home=partial).json()["customers"][0]
    assert current["baseline_status"] == "needs_update"
    assert save(client, current, home=replacement, baseline_confirmed_after_completion=False).status_code == 422
    response = save(client, current, home=replacement, baseline_confirmed_after_completion=True)
    assert response.status_code == 200
    confirmed = response.json()["customers"][0]
    assert confirmed["baseline_status"] == "current"
    assert confirmed["home"]["gas_kwh"] == 0
    assert confirmed["events"] == current["events"]


def test_completing_rest_of_previously_validated_package_does_not_invent_baseline(session):
    client, _, workspace = session
    selected = save(client, workspace["customers"][0],
                    selected_retrofits=["loft_insulation", "smart_controls"]).json()["customers"][0]
    first = completion(client, selected).json()["customers"][0]
    assert first["selected_retrofits"] == ["smart_controls"]
    second = completion(client, first, retrofit_id="smart_controls")
    assert second.status_code == 200
    current = second.json()["customers"][0]
    assert len(current["events"]) == 2 and current["selected_retrofits"] == []
    assert current["home"]["electricity_kwh"] is None and current["home"]["gas_kwh"] is None


@pytest.mark.parametrize("change", [
    {"confirmed": False}, {"confirmed": 1}, {"confirmed": "true"}, {"kind": "note"},
    {"completed_on": "2026-10-11"}, {"completed_on": "2026-02-30"},
    {"completed_on": "10/10/2026"}, {"retrofit_id": "unknown"}, {"notes": "PRIVATE-MARKER"},
])
def test_completion_rejects_bad_confirmation_dates_and_fields(session, change):
    client, _, workspace = session
    customer = save(client, workspace["customers"][0], selected_retrofits=["loft_insulation"]).json()["customers"][0]
    assert completion(client, customer, **change).status_code == 422
    assert client.get(BASE).json()["customers"][0] == customer


def test_completion_uses_uk_calendar_date_at_bst_midnight(session):
    client, store, workspace = session
    # During BST the UK calendar date is already the 11th while UTC is the 10th.
    store.clock = lambda: datetime(2026, 10, 10, 23, 30, tzinfo=timezone.utc).timestamp()
    customer = save(client, workspace["customers"][0], selected_retrofits=["loft_insulation"]).json()["customers"][0]
    assert completion(client, customer, completed_on="2026-10-11").status_code == 200


def test_unselected_duplicate_and_stale_completions_rejected(session):
    client, _, workspace = session
    customer = workspace["customers"][0]
    assert completion(client, customer).status_code == 422
    selected = save(client, customer, selected_retrofits=["loft_insulation"]).json()["customers"][0]
    assert completion(client, selected).status_code == 200
    assert completion(client, selected).status_code == 409
    current = client.get(BASE).json()["customers"][0]
    assert completion(client, current).status_code == 422
    assert len(client.get(BASE).json()["customers"][0]["events"]) == 1


def test_bounded_events_and_body(session, monkeypatch):
    from greenhome import workspace_api
    client, _, workspace = session
    selected = save(client, workspace["customers"][0], selected_retrofits=["loft_insulation", "smart_controls"]).json()["customers"][0]
    first = completion(client, selected).json()["customers"][0]
    monkeypatch.setattr(workspace_api, "MAX_EVENTS", 1)
    assert completion(client, first, retrofit_id="smart_controls").status_code == 409
    assert client.get(BASE).json()["customers"][0] == first
    response = client.post(BASE, content=b'{"consent":true,"extra":"' + b"x" * 17_000 + b'"}',
                           headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("headers,status", [
    ({"origin": "https://evil.example"}, 403),
    ({"origin": "null"}, 403),
    ({"sec-fetch-site": "cross-site"}, 403),
    ({"content-type": "text/plain"}, 415),
    ({"content-type": "application/x-www-form-urlencoded"}, 415),
])
def test_csrf_defences_are_router_local(session, headers, status):
    client, _, workspace = session
    response = client.post(BASE + "/delete", json={"confirm": True}, headers=headers)
    assert response.status_code == status
    assert client.get(BASE).json() == workspace


def test_json_parse_errors_and_sql_errors_are_private(session, monkeypatch, caplog):
    client, store, _ = session
    response = client.post(BASE, content="{broken", headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert "{broken" not in response.text

    def broken(*args):
        raise RuntimeError("PRIVATE-MARKER-driver-url-or-token")

    monkeypatch.setattr(store, "get", broken)
    failed = client.get(BASE)
    assert failed.status_code == 503
    assert "PRIVATE-MARKER" not in failed.text + caplog.text


def test_global_quota_repeated_create_is_idempotent_and_delete_does_not_reset_daily_limit(build):
    factory, _ = build
    first, store = factory()
    store.max_workspaces = 1
    store.max_creations_per_day = 1
    with first:
        created = first.post(BASE, json={"consent": True}).json()
        assert first.post(BASE, json={"consent": True}).json() == created
        with TestClient(first.app) as other:
            assert other.post(BASE, json={"consent": True}).status_code == 429
            assert first.post(BASE + "/delete", json={"confirm": True}).status_code == 200
            assert other.post(BASE, json={"consent": True}).status_code == 429
            store.clock = lambda: NOW + 86400
            assert other.post(BASE, json={"consent": True}).status_code == 200


def test_openapi_uses_injected_strict_home_and_requires_all_update_fields(build):
    factory, _ = build
    with factory()[0] as client:
        document = client.get("/openapi.json").json()
        schema = document["components"]["schemas"]["WorkspaceCustomerUpdate"]
        assert set(schema["required"]) == {"version", "home", "preferences", "selected_retrofits", "review_status"}
        assert schema["additionalProperties"] is False
        home = document["components"]["schemas"]["WorkspaceHome"]
        assert home["additionalProperties"] is False
        assert home["properties"]["data_kind"]["const"] == "synthetic_demo"
        assert "excluded_retrofits" in home["properties"]
