"""Frozen v1 DDL/state fixtures, not v2-created substitutes for migration proof."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import multiprocessing
import sqlite3
import stat

import pytest
from sqlalchemy import event

from greenhome import engine, workspace_migration
from greenhome.workspace_store import TTL_SECONDS, WorkspaceError, WorkspaceStore, iso_utc, token_hash

NOW = 1_791_590_400
TOKEN = "a" * 43
WORKSPACE_ID = "a" * 32

# This is the exact three-table schema emitted by the original schema-1 Core
# definitions (ad06fbc). Keep it independent of the current metadata.
V1_DDL = """
CREATE TABLE workspace_control (
 id INTEGER NOT NULL, schema_version INTEGER NOT NULL,
 creation_day VARCHAR(10) NOT NULL, creations INTEGER NOT NULL,
 PRIMARY KEY (id), CHECK (id = 1 AND schema_version = 1),
 CHECK (creations >= 0 AND creations <= 1000));
CREATE TABLE workspaces (
 id VARCHAR(32) NOT NULL, token_hash VARCHAR(64) NOT NULL,
 created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL,
 PRIMARY KEY (id), CHECK (expires_at = created_at + 2592000), UNIQUE (token_hash));
CREATE INDEX ix_workspaces_expires_at ON workspaces (expires_at);
CREATE TABLE workspace_customers (
 id VARCHAR(32) NOT NULL, workspace_id VARCHAR(32) NOT NULL, slot INTEGER NOT NULL,
 version INTEGER NOT NULL, state_json TEXT NOT NULL, updated_at BIGINT NOT NULL,
 PRIMARY KEY (id), UNIQUE (workspace_id, slot),
 CHECK (slot >= 1 AND slot <= 4),
 CHECK (version >= 1 AND version <= 2147483647),
 CHECK (length(state_json) <= 16384),
 FOREIGN KEY(workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE);
CREATE INDEX ix_workspace_customers_workspace_id ON workspace_customers (workspace_id);
"""


def v1_states(variant="pending"):
    states = []
    for home in engine.demo_homes():
        home["excluded_retrofits"] = []
        states.append({
            "home": home,
            "preferences": {"budget_gbp": home["budget_gbp"], "deferred_retrofits": [],
                            "priority": "energy", "disruption": "flexible"},
            "selected_retrofits": [], "review_status": "new", "baseline_status": "current", "events": [],
        })
    # Neither the individual budget nor exclusions may become universal.
    states[0]["home"]["budget_gbp"] = 2100
    states[0]["preferences"].update(budget_gbp=2100, deferred_retrofits=["solar_pv"],
                                    priority="carbon", disruption="minimal")
    states[0]["home"]["excluded_retrofits"] = ["solar_pv"]
    if variant != "pristine":
        states[0]["home"].update(insulation="good", electricity_kwh=None, gas_kwh=None)
        states[0].update(baseline_status="needs_update", review_status="reviewing",
                         selected_retrofits=["smart_controls"])
        states[0]["events"] = [{
            "id": "e" * 32, "kind": "completed", "retrofit_id": "loft_insulation",
            "completed_on": iso_utc(NOW - 200_000)[:10], "created_at": iso_utc(NOW - 80),
        }]
    if variant == "restored":
        states[0]["home"].update(electricity_kwh=1200, gas_kwh=0, roof_access=None,
                                 listed_building=True, consent_confirmed=True, heat_pump_ready=None)
        states[0]["baseline_status"] = "current"
    if variant == "all_completed":
        home = states[0]["home"]
        home.update(glazing="triple", smart_controls=True, solar_kwp=4.5, heating="heat_pump")
        home["budget_gbp"] = None
        home["excluded_retrofits"] = []
        states[0]["preferences"].update(budget_gbp=None, deferred_retrofits=[])
        states[0]["selected_retrofits"] = []
        states[0]["events"] = [{
            "id": f"{300 + i:032x}", "kind": "completed", "retrofit_id": rid,
            "completed_on": iso_utc(NOW - 100_000)[:10], "created_at": iso_utc(NOW - 80 + i),
        } for i, rid in enumerate(engine.RETROFITS)]
    return states


def create_v1(path, variant="pending", *, expired=False):
    states = v1_states(variant)
    offset = TTL_SECONDS + 100 if expired else 0
    if offset:
        for state in states:
            for item in state["events"]:
                item["created_at"] = iso_utc(NOW - 80 - offset)
                item["completed_on"] = iso_utc(NOW - 200_000 - offset)[:10]
    with sqlite3.connect(path) as db:
        db.executescript(V1_DDL)
        db.execute("INSERT INTO workspace_control VALUES(1,1,?,23)", (iso_utc(NOW)[:10],))
        db.execute("INSERT INTO workspaces VALUES(?,?,?,?)",
                   (WORKSPACE_ID, token_hash(TOKEN), NOW - 100 - offset, NOW - 100 - offset + TTL_SECONDS))
        for i, state in enumerate(states, 1):
            # Whitespace/key order are deliberately retained in the moved JSON.
            db.execute("INSERT INTO workspace_customers VALUES(?,?,?,?,?,?)", (
                f"{100 + i:032x}", WORKSPACE_ID, i, [7, 3, 2, 1][i-1],
                json.dumps(state, indent=2, allow_nan=False), NOW - 50 - offset,
            ))
    return states


def snapshot(path):
    with sqlite3.connect(path) as db:
        return {
            "schema": db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall(),
            "control": db.execute("SELECT * FROM workspace_control").fetchall(),
            "workspaces": db.execute("SELECT * FROM workspaces ORDER BY id").fetchall(),
            "customers": db.execute("SELECT * FROM workspace_customers ORDER BY id").fetchall(),
        }


@pytest.mark.parametrize("variant", ["pristine", "pending", "restored", "all_completed"])
def test_exact_v1_state_cookie_ids_expiry_versions_and_backup_survive_v2_restart(tmp_path, variant):
    path = tmp_path / "legacy.sqlite3"
    old_states = create_v1(path, variant)
    original = snapshot(path)
    store = WorkspaceStore(f"sqlite:///{path}", clock=lambda: NOW)
    store.warm()
    backup = store.last_migration_backup
    assert backup is not None and stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert snapshot(backup) == original
    result = store.get(TOKEN)
    assert result["id"] == WORKSPACE_ID and result["schema_version"] == 2
    assert result["expires_at"] == iso_utc(NOW - 100 + TTL_SECONDS)
    for i, (customer, old) in enumerate(zip(result["customers"], old_states), 1):
        prior_row = original["customers"][i - 1]
        assert customer["id"] == prior_row[0]
        assert customer["label"] == f"Example household {i}"
        assert customer["version"] == prior_row[3]
        assert customer["updated_at"] == iso_utc(prior_row[5])
        assert customer["portfolio_budget_gbp"] is None
        assert customer["customer_preferences"] == {
            "deferred_retrofits": [], "priority": "energy", "disruption": "flexible",
        }
        expected_reserve = None if old["events"] else 0
        assert customer["legacy_completed_reserve_gbp"] == expected_reserve
        prop = customer["properties"][0]
        assert prop["version"] == customer["version"]
        assert prop["customer_id"] == customer["id"]
        assert prop["id"] == hashlib.sha256(
            ("greenhome:property:v2:" + customer["id"]).encode("ascii")
        ).hexdigest()[:32]
        for key, value in old.items():
            assert prop[key] == value == customer[key]
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT state_json FROM workspace_properties WHERE id=?", (prop["id"],)).fetchone()[0] == prior_row[4]
    assert snapshot(path)["workspaces"] == original["workspaces"]
    assert snapshot(path)["control"] == [(1, 2, iso_utc(NOW)[:10], 23)]
    store.close()
    restarted = WorkspaceStore(f"sqlite:///{path}", clock=lambda: NOW)
    restarted.warm()
    restarted.warm()
    assert restarted.get(TOKEN) == result
    assert restarted.last_migration_backup is None
    assert len(list(tmp_path.glob("*.schema1-*.sqlite3"))) == 1
    restarted.close()


def test_expired_v1_rows_preserved_during_upgrade_not_implicitly_pruned(tmp_path):
    path = tmp_path / "expired.sqlite3"
    create_v1(path, expired=True)
    before = snapshot(path)
    store = WorkspaceStore(f"sqlite:///{path}", clock=lambda: NOW)
    store.warm()
    assert snapshot(path)["workspaces"] == before["workspaces"]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM workspace_properties").fetchone() == (4,)
    with pytest.raises(WorkspaceError) as error:
        store.get(TOKEN)
    assert error.value.status == 401
    assert store.prune_expired() == 1
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM workspace_properties").fetchone() == (0,)


@pytest.mark.parametrize("corruption", [
    "invalid_json", "duplicate_json_key", "unknown_field", "missing_field", "private_home",
    "invalid_feature", "completed_selected", "future_occurrence", "recorded_after_update",
    "duplicate_event", "unknown_retrofit", "nonfinite", "bad_version", "wrong_workspace",
    "missing_customer", "duplicate_home", "unknown_schema", "extra_column",
])
def test_every_invalid_v1_row_or_schema_aborts_without_changes(tmp_path, corruption):
    path = tmp_path / "invalid.sqlite3"
    create_v1(path)
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT id,state_json FROM workspace_customers ORDER BY slot").fetchone()
        state = json.loads(row[1])
        if corruption == "invalid_json":
            raw = "{not-json"
        elif corruption == "duplicate_json_key":
            raw = row[1][:-1] + ',"events":[]}'
        else:
            if corruption == "unknown_field": state["notes"] = "NOT_ALLOWED"
            if corruption == "missing_field": del state["preferences"]
            if corruption == "private_home": state["home"]["data_kind"] = "user_entered"
            if corruption == "invalid_feature": state["home"]["insulation"] = "poor"
            if corruption == "completed_selected": state["selected_retrofits"] = ["loft_insulation"]
            if corruption == "future_occurrence": state["events"][0]["completed_on"] = "2099-01-01"
            if corruption == "recorded_after_update": state["events"][0]["created_at"] = iso_utc(NOW)
            if corruption == "duplicate_event": state["events"] *= 2
            if corruption == "unknown_retrofit": state["selected_retrofits"] = ["unknown"]
            if corruption == "nonfinite": state["home"]["solar_kwp"] = float("nan")
            raw = json.dumps(state)
        db.execute("UPDATE workspace_customers SET state_json=? WHERE id=?", (raw, row[0]))
        db.execute("PRAGMA ignore_check_constraints=ON")
        if corruption == "bad_version":
            db.execute("UPDATE workspace_customers SET version=0 WHERE slot=4")
        if corruption == "wrong_workspace":
            db.execute("UPDATE workspace_customers SET workspace_id=? WHERE slot=4", ("f"*32,))
        if corruption == "missing_customer":
            db.execute("DELETE FROM workspace_customers WHERE slot=4")
        if corruption == "duplicate_home":
            state4 = json.loads(db.execute("SELECT state_json FROM workspace_customers WHERE slot=4").fetchone()[0])
            state4["home"]["property_id"] = "DEMO-01"
            db.execute("UPDATE workspace_customers SET state_json=? WHERE slot=4", (json.dumps(state4),))
        if corruption == "unknown_schema":
            db.execute("UPDATE workspace_control SET schema_version=99")
        if corruption == "extra_column":
            db.execute("ALTER TABLE workspace_customers ADD COLUMN unexpected TEXT")
    before = snapshot(path)
    store = WorkspaceStore(f"sqlite:///{path}", clock=lambda: NOW)
    with pytest.raises(WorkspaceError) as error:
        store.warm()
    assert error.value.code == "workspace_unavailable"
    assert store._engine is None and snapshot(path) == before
    assert not list(tmp_path.glob("*.schema1-*.sqlite3"))


def test_failure_after_ddl_and_partial_copy_rolls_back_every_row_and_constraint(tmp_path, monkeypatch):
    path = tmp_path / "rollback.sqlite3"
    create_v1(path)
    before = snapshot(path)
    real_validate = workspace_migration.validate_rows

    def fail_after_copy(conn, version):
        if version == 2:
            assert conn.exec_driver_sql("SELECT count(*) FROM workspace_properties").scalar() == 4
            assert conn.exec_driver_sql("SELECT schema_version FROM workspace_control").scalar() == 2
            raise ValueError("Injected post-copy validation failure.")
        return real_validate(conn, version)

    monkeypatch.setattr(workspace_migration, "validate_rows", fail_after_copy)
    store = WorkspaceStore(f"sqlite:///{path}", clock=lambda: NOW)
    with pytest.raises(WorkspaceError):
        store.warm()
    assert snapshot(path) == before
    backups = list(tmp_path.glob("*.schema1-*.sqlite3"))
    assert len(backups) == 1 and snapshot(backups[0]) == before
    monkeypatch.setattr(workspace_migration, "validate_rows", real_validate)
    store.warm()
    assert store.get(TOKEN)["schema_version"] == 2


def _warm_worker(url, barrier, output):
    store = WorkspaceStore(url, clock=lambda: NOW)
    try:
        barrier.wait(20)
        store.warm()
        output.put(store.get(TOKEN))
    except Exception as exc:
        output.put(type(exc).__name__)
    finally:
        store.close()


def test_independent_process_warmers_migrate_only_once(tmp_path):
    path = tmp_path / "race.sqlite3"
    create_v1(path)
    ctx = multiprocessing.get_context("spawn")
    barrier, output = ctx.Barrier(3), ctx.Queue()
    workers = [ctx.Process(target=_warm_worker, args=(f"sqlite:///{path}", barrier, output)) for _ in range(3)]
    try:
        for worker in workers:
            worker.start()
        results = [output.get(timeout=30) for _ in workers]
        for worker in workers:
            worker.join(30)
            assert worker.exitcode == 0
        assert all(isinstance(result, dict) and result["schema_version"] == 2 for result in results)
        assert results[0] == results[1] == results[2]
        assert len(list(tmp_path.glob("*.schema1-*.sqlite3"))) == 1
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT count(*) FROM workspace_properties").fetchone() == (4,)
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join()
        output.close()


def test_v2_restart_validates_corrupt_property_not_only_table_columns(tmp_path):
    path = tmp_path / "v2.sqlite3"
    create_v1(path)
    store = WorkspaceStore(f"sqlite:///{path}", clock=lambda: NOW)
    store.warm()
    store.close()
    with sqlite3.connect(path) as db:
        db.execute("UPDATE workspace_properties SET state_json='{}' WHERE slot=1")
    new_worker = WorkspaceStore(f"sqlite:///{path}", clock=lambda: NOW)
    with pytest.raises(WorkspaceError):
        new_worker.warm()
