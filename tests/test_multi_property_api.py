"""Actual v2 HTTP routes, offline fictional inputs and temporary SQLite only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import json
import sqlite3

import pytest

from greenhome import engine
from greenhome.workspace_api import COOKIE_NAME
from greenhome.workspace_store import MAX_VERSION
from test_workspace_api import BASE, build, offline, payload, session  # shared boundary fixtures
from test_multi_property_migration import TOKEN, create_v1


def property_payload(customer, prop, **changes):
    data = {key: deepcopy(prop[key]) for key in
            ("version", "home", "preferences", "selected_retrofits", "review_status")}
    data["customer_version"] = customer["version"]
    data.update(changes)
    return data


def path(customer, prop):
    return f"{BASE}/customers/{customer['id']}/properties/{prop['id']}"


def save_property(client, customer, prop, **changes):
    return client.post(path(customer, prop), json=property_payload(customer, prop, **changes))


def complete_property(client, customer, prop, **changes):
    body = {"customer_version": customer["version"], "version": prop["version"], "kind": "completed",
            "retrofit_id": "loft_insulation", "completed_on": "2026-10-10", "confirmed": True}
    body.update(changes)
    return client.post(path(customer, prop) + "/events", json=body)


def settings(client, customer, **changes):
    body = {key: deepcopy(customer[key]) for key in
            ("version", "customer_preferences", "portfolio_budget_gbp", "legacy_completed_reserve_gbp")}
    body.update(changes)
    return client.post(f"{BASE}/customers/{customer['id']}/settings", json=body)


def add(client, customer, template_id="DEMO-01", **changes):
    body = {"customer_version": customer["version"], "template_id": template_id}
    body.update(changes)
    return client.post(f"{BASE}/customers/{customer['id']}/properties", json=body)


def with_properties(client, workspace, count):
    customer = workspace["customers"][0]
    for _ in range(1, count):
        response = add(client, customer)
        assert response.status_code == 200, response.text
        workspace = response.json()
        customer = workspace["customers"][0]
    return workspace, customer


@pytest.mark.parametrize("count", [1, 2, 4, 8])
def test_canonical_shapes_and_unique_property_identity_with_exactly_one_compatibility(session, count):
    client, _, initial = session
    workspace, customer = with_properties(client, initial, count)
    assert workspace["schema_version"] == 2
    assert len(customer["properties"]) == count
    assert len(workspace["customers"]) == 4
    assert workspace["customers"][1:] == initial["customers"][1:]
    all_props = [prop for owner in workspace["customers"] for prop in owner["properties"]]
    assert len({prop["id"] for prop in all_props}) == len(all_props)
    assert len({prop["home"]["property_id"] for prop in all_props}) == len(all_props)
    assert all(prop["id"] != prop["home"]["property_id"] for prop in all_props)
    for prop in customer["properties"]:
        assert prop["customer_id"] == customer["id"]
        assert client.get(path(customer, prop)).json() == workspace
    legacy_keys = {"home", "preferences", "selected_retrofits", "review_status", "baseline_status", "events"}
    assert (legacy_keys <= set(customer)) if count == 1 else not (legacy_keys & set(customer))
    if count > 1:
        old_payload = payload(initial["customers"][0], version=customer["version"])
        result = client.post(f"{BASE}/customers/{customer['id']}", json=old_payload)
        assert result.status_code == 409 and result.json()["detail"]["code"] == "property_required"
        event = {"version": customer["version"], "kind": "completed", "retrofit_id": "loft_insulation",
                 "completed_on": "2026-10-10", "confirmed": True}
        result = client.post(f"{BASE}/customers/{customer['id']}/events", json=event)
        assert result.status_code == 409 and result.json()["detail"]["code"] == "property_required"
    assert client.get(BASE + "/export").json() == workspace


def test_add_uses_four_templates_never_copies_edited_fuels_history_preferences(session):
    client, _, workspace = session
    customer = workspace["customers"][0]
    first = customer["properties"][0]
    prefs = deepcopy(first["preferences"])
    prefs.update(budget_gbp=2000, deferred_retrofits=["solar_pv"], priority="carbon")
    home = deepcopy(first["home"])
    home.update(electricity_kwh=999, gas_kwh=777)
    customer = save_property(client, customer, first, home=home, preferences=prefs,
                             selected_retrofits=["loft_insulation"]).json()["customers"][0]
    customer = complete_property(client, customer, customer["properties"][0]).json()["customers"][0]
    original = deepcopy(customer["properties"][0])
    for template in engine.demo_homes():
        customer = add(client, customer, template["property_id"]).json()["customers"][0]
        new = customer["properties"][-1]
        assert new["id"] != original["id"] and new["home"]["property_id"].startswith("PROP-")
        assert new["events"] == new["selected_retrofits"] == []
        assert new["preferences"] == {
            "budget_gbp": template["budget_gbp"], "deferred_retrofits": [],
            "priority": "energy", "disruption": "flexible",
        }
        assert new["version"] == 1 and new["baseline_status"] == "current"
        for field, value in template.items():
            if field != "property_id":
                assert new["home"][field] == value
        assert customer["properties"][0] == original
    while len(customer["properties"]) < 8:
        customer = add(client, customer).json()["customers"][0]
    before = client.get(BASE).json()
    rejected = add(client, customer)
    assert rejected.status_code == 409 and rejected.json()["detail"]["code"] == "property_limit"
    assert client.get(BASE).json() == before


@pytest.mark.parametrize("kind", ["same_workspace", "other_workspace", "unknown_customer", "unknown_property"])
def test_wrong_owner_is_404_for_get_save_and_event_even_with_valid_property(session, build, kind):
    client, _, initial = session
    workspace, customer = with_properties(client, initial, 2)
    prop = customer["properties"][0]
    if kind == "same_workspace":
        wrong = workspace["customers"][1]
    elif kind == "other_workspace":
        outsider, _ = build[0]()
        wrong = outsider.post(BASE, json={"consent": True}).json()["customers"][0]
    elif kind == "unknown_customer":
        wrong = {**customer, "id": "f"*32}
    else:
        wrong = customer
        prop = {**prop, "id": "f"*32}
    assert client.get(path(wrong, prop)).status_code == 404
    assert save_property(client, wrong, prop).status_code == 404
    assert complete_property(client, wrong, prop).status_code == 404
    assert client.get(BASE).json() == workspace


def test_property_identity_and_owner_cannot_be_supplied_or_transferred(session):
    client, _, initial = session
    workspace, customer = with_properties(client, initial, 2)
    a, b = customer["properties"]
    for key, value in (("customer_id", initial["customers"][1]["id"]), ("id", b["id"])):
        assert save_property(client, customer, a, **{key: value}).status_code == 422
        assert add(client, customer, **{key: value}).status_code == 422
    assert save_property(client, customer, a, template_id="DEMO-02").status_code == 422
    assert add(client, customer, template_id="DEMO-05").status_code == 422
    home = deepcopy(a["home"])
    home["property_id"] = b["home"]["property_id"]
    assert save_property(client, customer, a, home=home).status_code == 422
    assert client.get(BASE).json() == workspace


def test_both_versions_checked_and_only_target_version_changes(session):
    client, _, initial = session
    workspace, customer = with_properties(client, initial, 4)
    a, b = customer["properties"][:2]
    response = save_property(client, customer, a, review_status="ready")
    assert response.status_code == 200
    current = response.json()["customers"][0]
    assert current["version"] == customer["version"] + 1
    assert current["properties"][0]["version"] == a["version"] + 1
    assert current["properties"][1:] == customer["properties"][1:]
    assert save_property(client, customer, b).status_code == 409  # stale customer, unchanged property
    assert save_property(client, current, a).status_code == 409  # current customer, stale property
    assert complete_property(client, current, a).status_code == 409
    changed = save_property(client, current, b, review_status="deferred").json()["customers"][0]
    assert changed["properties"][0] == current["properties"][0]
    assert changed["properties"][1]["version"] == b["version"] + 1


def test_customer_union_keeps_raw_preferences_and_property_budgets_independent(session, build):
    client, _, initial = session
    workspace, customer = with_properties(client, initial, 2)
    a, b = customer["properties"]
    prefs = {**a["preferences"], "budget_gbp": 500, "deferred_retrofits": ["solar_pv"]}
    customer = save_property(client, customer, a, preferences=prefs,
                             selected_retrofits=["smart_controls"]).json()["customers"][0]
    before = deepcopy(customer["properties"])
    universal = {"deferred_retrofits": ["heat_pump"], "priority": "low_cost", "disruption": "minimal"}
    customer = settings(client, customer, customer_preferences=universal,
                        portfolio_budget_gbp=5000).json()["customers"][0]
    assert customer["customer_preferences"] == universal
    assert customer["properties"][0]["preferences"] == prefs
    assert customer["properties"][0]["home"]["excluded_retrofits"] == ["solar_pv", "heat_pump"]
    assert customer["properties"][1]["home"]["excluded_retrofits"] == ["heat_pump"]
    for old, new in zip(before, customer["properties"]):
        assert new["version"] == old["version"]
        assert new["preferences"] == old["preferences"]
        assert new["home"]["budget_gbp"] == old["home"]["budget_gbp"]
    # Settings change no child database state, even though effective read homes
    # now contain the union for the parent-owned assess/rank endpoints.
    with sqlite3.connect(build[1]) as db:
        stored = json.loads(db.execute("SELECT state_json FROM workspace_properties WHERE id=?", (b["id"],)).fetchone()[0])
        assert stored["home"]["excluded_retrofits"] == []
    a, b = customer["properties"]
    assert save_property(client, customer, a, selected_retrofits=["loft_insulation"]).status_code == 422
    assert save_property(client, customer, b, selected_retrofits=["heat_pump"]).status_code == 422
    ok = save_property(client, customer, b, selected_retrofits=["loft_insulation"])
    assert ok.status_code == 200
    assert ok.json()["customers"][0]["budget_summary"]["planned_upper_gbp"] == 1950


def test_customer_exclusions_conflict_is_atomic_no_silent_plan_deletion(session):
    client, _, initial = session
    _, customer = with_properties(client, initial, 2)
    for index in range(2):
        customer = save_property(client, customer, customer["properties"][index],
                                 selected_retrofits=["loft_insulation"]).json()["customers"][0]
    before = client.get(BASE).json()
    result = settings(client, customer, customer_preferences={
        "deferred_retrofits": ["loft_insulation"], "priority": "energy", "disruption": "flexible",
    })
    assert result.status_code == 409 and result.json()["detail"]["code"] == "exclusion_conflict"
    assert client.get(BASE).json() == before


def test_portfolio_cap_sums_siblings_completed_reservations_and_manual_reserve(session):
    client, _, initial = session
    _, customer = with_properties(client, initial, 2)
    customer = settings(client, customer, portfolio_budget_gbp=4000,
                        legacy_completed_reserve_gbp=800, confirm_legacy_reserve=True).json()["customers"][0]
    for index in range(2):
        response = save_property(client, customer, customer["properties"][index], selected_retrofits=["loft_insulation"])
        assert response.status_code == 200
        customer = response.json()["customers"][0]
    assert customer["budget_summary"] == {
        "planned_upper_gbp": 3200, "completed_reserved_gbp": 800,
        "total_reserved_gbp": 4000, "remaining_gbp": 0, "status": "within_budget",
    }
    sibling = deepcopy(customer["properties"][1])
    customer = complete_property(client, customer, customer["properties"][0]).json()["customers"][0]
    assert customer["properties"][1] == sibling
    assert customer["budget_summary"] == {
        "planned_upper_gbp": 1600, "completed_reserved_gbp": 2400,
        "total_reserved_gbp": 4000, "remaining_gbp": 0, "status": "within_budget",
    }
    before = client.get(BASE).json()
    assert settings(client, customer, portfolio_budget_gbp=3999).status_code == 409
    result = save_property(client, customer, sibling, selected_retrofits=["loft_insulation", "smart_controls"])
    assert result.status_code == 409 and result.json()["detail"]["code"] == "portfolio_budget_exceeded"
    assert client.get(BASE).json() == before
    customer = settings(client, customer, portfolio_budget_gbp=None).json()["customers"][0]
    assert customer["budget_summary"]["total_reserved_gbp"] == 4000
    assert customer["budget_summary"]["status"] == "unlimited"
    assert customer["budget_summary"]["remaining_gbp"] is None


def test_legacy_cap_and_new_property_routes_share_the_same_allocation_checks(session):
    client, _, initial = session
    customer = initial["customers"][0]
    customer = settings(client, customer, portfolio_budget_gbp=1600).json()["customers"][0]
    result = client.post(f"{BASE}/customers/{customer['id']}", json=payload(
        customer, selected_retrofits=["loft_insulation", "smart_controls"]))
    assert result.status_code == 409
    result = client.post(f"{BASE}/customers/{customer['id']}", json=payload(
        customer, selected_retrofits=["loft_insulation"]))
    assert result.status_code == 200
    customer = result.json()["customers"][0]
    assert customer["properties"][0]["version"] == 2
    # Adding doesn't spend, but changing a newly added property cannot evade
    # the allocation made through the deprecated single-property adapter.
    customer = add(client, customer).json()["customers"][0]
    assert save_property(client, customer, customer["properties"][1],
                         selected_retrofits=["smart_controls"]).status_code == 409


def test_concurrent_sibling_http_saves_only_one_can_spend_last_allocation(session, build):
    client, _, initial = session
    _, customer = with_properties(client, initial, 2)
    customer = settings(client, customer, portfolio_budget_gbp=1600).json()["customers"][0]
    other, _ = build[0]()
    other.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(save_property, who, customer, prop, selected_retrofits=["loft_insulation"])
                   for who, prop in zip((client, other), customer["properties"])]
        results = [future.result() for future in futures]
    assert sorted(result.status_code for result in results) == [200, 409]
    current = client.get(BASE).json()["customers"][0]
    assert current["budget_summary"]["total_reserved_gbp"] == 1600
    assert sum(prop["selected_retrofits"] == ["loft_insulation"] for prop in current["properties"]) == 1
    loser = next(prop for prop in current["properties"] if not prop["selected_retrofits"])
    assert save_property(client, current, loser, selected_retrofits=["loft_insulation"]).status_code == 409


@pytest.mark.parametrize("race", ["completion", "settings", "add"])
def test_sibling_save_and_other_mutations_share_customer_version_lock(session, build, race):
    client, _, initial = session
    _, customer = with_properties(client, initial, 2)
    customer = save_property(client, customer, customer["properties"][0],
                             selected_retrofits=["loft_insulation"]).json()["customers"][0]
    customer = settings(client, customer, portfolio_budget_gbp=1950).json()["customers"][0]
    other, _ = build[0]()
    other.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(save_property, client, customer, customer["properties"][1],
                            selected_retrofits=["smart_controls"])
        if race == "completion":
            second = pool.submit(complete_property, other, customer, customer["properties"][0])
        elif race == "settings":
            second = pool.submit(settings, other, customer, portfolio_budget_gbp=1600)
        else:
            second = pool.submit(add, other, customer)
        results = [first.result(), second.result()]
    assert sorted(result.status_code for result in results) == [200, 409]
    current = client.get(BASE).json()["customers"][0]
    assert current["budget_summary"]["total_reserved_gbp"] <= current["portfolio_budget_gbp"]
    assert current["version"] == customer["version"] + 1


def test_pending_completion_does_not_reassess_unknown_fuels_or_clear_sibling(session, monkeypatch):
    client, _, initial = session
    _, customer = with_properties(client, initial, 2)
    customer = save_property(client, customer, customer["properties"][0],
                             selected_retrofits=["loft_insulation", "smart_controls"]).json()["customers"][0]
    customer = settings(client, customer, portfolio_budget_gbp=1950).json()["customers"][0]
    customer = complete_property(client, customer, customer["properties"][0]).json()["customers"][0]
    sibling = deepcopy(customer["properties"][1])
    assert customer["properties"][0]["selected_retrofits"] == ["smart_controls"]

    def forbidden(*args, **kwargs):
        pytest.fail("Do not reassess the saved unfinished package against now-unknown fuels.")

    monkeypatch.setattr(engine, "assess", forbidden)
    response = complete_property(client, customer, customer["properties"][0], retrofit_id="smart_controls")
    assert response.status_code == 200
    customer = response.json()["customers"][0]
    assert customer["budget_summary"]["total_reserved_gbp"] == 1950
    assert customer["budget_summary"]["planned_upper_gbp"] == 0
    assert customer["properties"][1] == sibling
    assert customer["properties"][0]["home"]["electricity_kwh"] is None
    assert customer["properties"][0]["home"]["gas_kwh"] is None
    assert not any("saving" in key for event in customer["properties"][0]["events"] for key in event)


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("rid,feature,bad,better", [
    ("loft_insulation", "insulation", "poor", "good"),
    ("double_glazing", "glazing", "single", "triple"),
    ("smart_controls", "smart_controls", False, True),
    ("solar_pv", "solar_kwp", 0, 4.5),
    ("heat_pump", "heating", "gas_boiler", "heat_pump"),
])
def test_completed_feature_cannot_regress_or_be_selected_after_baseline_restore(session, legacy, rid, feature, bad, better):
    client, _, initial = session
    customer = initial["customers"][0]
    customer = save_property(client, customer, customer["properties"][0], selected_retrofits=[rid]).json()["customers"][0]
    customer = complete_property(client, customer, customer["properties"][0], retrofit_id=rid).json()["customers"][0]
    before = client.get(BASE).json()
    home = deepcopy(customer["properties"][0]["home"])
    home.update(electricity_kwh=2500, gas_kwh=0)
    home[feature] = bad

    def attempt(home, selection):
        changes = dict(home=home, selected_retrofits=selection, baseline_confirmed_after_completion=True)
        if legacy:
            return client.post(f"{BASE}/customers/{customer['id']}", json=payload(customer, **changes))
        return save_property(client, customer, customer["properties"][0], **changes)

    assert attempt(home, [rid]).status_code == 422
    assert attempt(home, []).status_code == 422
    assert client.get(BASE).json() == before
    home[feature] = better
    assert attempt(home, [rid]).status_code == 422
    response = attempt(home, [])
    assert response.status_code == 200, response.text
    current = response.json()["customers"][0]["properties"][0]
    assert current["home"][feature] == better and current["baseline_status"] == "current"
    assert current["events"] == customer["properties"][0]["events"]


@pytest.mark.parametrize("now,date_,status", [
    ("2026-10-10T22:59:59+00:00", "2026-10-11", 422),
    ("2026-10-10T23:00:00+00:00", "2026-10-11", 200),
    ("2026-10-11T00:00:00+00:00", "2026-10-12", 422),
    ("2026-10-26T23:30:00+00:00", "2026-10-27", 422),
])
def test_new_completion_utc_timestamp_london_calendar_future_guard(session, now, date_, status):
    client, store, initial = session
    store.clock = lambda: datetime.fromisoformat(now).timestamp()
    customer = initial["customers"][0]
    customer = save_property(client, customer, customer["properties"][0],
                             selected_retrofits=["loft_insulation"]).json()["customers"][0]
    response = complete_property(client, customer, customer["properties"][0], completed_on=date_)
    assert response.status_code == status
    if status == 200:
        event = response.json()["customers"][0]["properties"][0]["events"][0]
        assert event["created_at"] == now.replace("+00:00", "Z")
        assert event["completed_on"] == date_


def test_migrated_unknown_reserve_requires_explicit_confirmation_zero_allowed(build):
    factory, db_path = build
    db_path.parent.mkdir(parents=True)
    create_v1(db_path)
    client, store = factory()
    store.warm()
    client.cookies.set(COOKIE_NAME, TOKEN)
    current = client.get(BASE).json()
    customer = current["customers"][0]
    assert customer["legacy_completed_reserve_gbp"] is None
    assert customer["budget_summary"] == {
        "planned_upper_gbp": 350, "completed_reserved_gbp": None, "total_reserved_gbp": None,
        "remaining_gbp": None, "status": "needs_cost_evidence",
    }
    assert settings(client, customer, portfolio_budget_gbp=10000).status_code == 409
    assert settings(client, customer, portfolio_budget_gbp=350, legacy_completed_reserve_gbp=0).status_code == 422
    assert settings(client, customer, portfolio_budget_gbp=350, legacy_completed_reserve_gbp=0,
                    confirm_legacy_reserve=1).status_code == 422
    assert client.get(BASE).json() == current
    response = settings(client, customer, portfolio_budget_gbp=350, legacy_completed_reserve_gbp=0,
                        confirm_legacy_reserve=True)
    assert response.status_code == 200
    customer = response.json()["customers"][0]
    assert customer["properties"] == current["customers"][0]["properties"]
    assert customer["budget_summary"]["total_reserved_gbp"] == 350
    assert "planning_cost_upper_gbp" not in customer["properties"][0]["events"][0]
    response = complete_property(client, customer, customer["properties"][0], retrofit_id="smart_controls")
    assert response.status_code == 200
    customer = response.json()["customers"][0]
    assert customer["budget_summary"]["completed_reserved_gbp"] == 350
    assert customer["budget_summary"]["remaining_gbp"] == 0
    assert settings(client, customer, portfolio_budget_gbp=349).status_code == 409
    assert settings(client, customer, legacy_completed_reserve_gbp=None).status_code == 422


@pytest.mark.parametrize("field", ["customer_version", "version", "home", "preferences", "selected_retrofits", "review_status"])
def test_new_save_requires_all_fields(session, field):
    client, _, initial = session
    customer = initial["customers"][0]
    prop = customer["properties"][0]
    body = property_payload(customer, prop)
    del body[field]
    assert client.post(path(customer, prop), json=body).status_code == 422
    assert client.get(BASE).json() == initial


@pytest.mark.parametrize("field,value", [
    ("portfolio_budget_gbp", True), ("portfolio_budget_gbp", -1),
    ("portfolio_budget_gbp", "100"), ("portfolio_budget_gbp", 1e10),
    ("legacy_completed_reserve_gbp", True), ("confirm_legacy_reserve", "true"),
    ("customer_preferences", {"deferred_retrofits": ["solar_pv", "solar_pv"], "priority": "energy", "disruption": "flexible"}),
])
def test_customer_settings_strict_validation(session, field, value):
    client, _, initial = session
    assert settings(client, initial["customers"][0], **{field: value}).status_code == 422
    assert client.get(BASE).json() == initial


def test_export_delete_cascade_all_properties_and_foreign_key_enforced(session, build):
    client, store, initial = session
    workspace, customer = with_properties(client, initial, 8)
    with sqlite3.connect(build[1]) as db:
        db.execute("PRAGMA foreign_keys=ON")
        fk = db.execute("PRAGMA foreign_key_list(workspace_properties)").fetchall()
        assert any(row[2] == "workspace_customers" and row[6] == "CASCADE" for row in fk)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE workspace_properties SET customer_id=?", ("f"*32,))
    assert client.get(BASE + "/export").json() == workspace
    assert client.post(BASE + "/delete", json={"confirm": True}).status_code == 200
    with sqlite3.connect(build[1]) as db:
        assert db.execute("SELECT count(*) FROM workspace_properties").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM workspace_customers").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM workspaces").fetchone() == (0,)
    assert client.get(path(customer, customer["properties"][0])).status_code == 401
