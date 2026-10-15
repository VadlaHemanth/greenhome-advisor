"""Strict, transactional schema 1 -> 2 upgrade; no app/provider imports.

Operators must stop old workers before warmup. SQLite BEGIN IMMEDIATE (or the
PostgreSQL advisory lock) is already held by the caller throughout this module.
Validation never recomputes a historic plan or rewrites evidence.
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import CheckConstraint, UniqueConstraint, inspect, insert, select, update

from greenhome import engine
from greenhome.workspace_store import (
    CUSTOMERS_PER_WORKSPACE, ID_PATTERN, MAX_EVENTS, MAX_PROPERTIES, MAX_STATE_BYTES,
    MAX_VERSION, TTL_SECONDS, _state_json, check_allocation, control, customer_owner_index,
    customers, metadata, neutral_settings, properties, workspaces,
)

PROPERTY_KEYS = {"home", "preferences", "selected_retrofits", "review_status", "baseline_status", "events"}
PREFERENCE_KEYS = {"deferred_retrofits", "priority", "disruption"}
HOME_KEYS = set(engine.demo_homes()[0]) | {"excluded_retrofits"}
HOME_ID = re.compile(r"^(DEMO-0[1-4]|PROP-[a-f0-9]{32})$")


def require(value):
    if not value:
        raise ValueError("Invalid workspace storage schema or row.")


def number(value, maximum=1_000_000_000):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum


def retrofit_list(value):
    require(isinstance(value, list) and len(value) <= len(engine.RETROFITS))
    require(all(isinstance(rid, str) and rid in engine.RETROFITS for rid in value))
    require(len(set(value)) == len(value))


def preferences(value, *, property_scope=False):
    require(isinstance(value, dict))
    require(set(value) == PREFERENCE_KEYS | ({"budget_gbp"} if property_scope else set()))
    retrofit_list(value["deferred_retrofits"])
    require(value["priority"] in ("energy", "carbon", "low_cost"))
    require(value["disruption"] in ("flexible", "minimal"))
    if property_scope:
        require(value["budget_gbp"] is None or number(value["budget_gbp"]))


def utc_timestamp(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value))
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def completed_features_valid(home, events):
    """No corrections/de-installations in this release; never count work twice."""
    installed = {
        "loft_insulation": lambda: home.get("insulation") == "good",
        "double_glazing": lambda: home.get("glazing") in ("double", "triple"),
        "smart_controls": lambda: home.get("smart_controls") is True,
        "solar_pv": lambda: number(home.get("solar_kwp"), 10_000) and home["solar_kwp"] > 0,
        "heat_pump": lambda: home.get("heating") == "heat_pump",
    }
    return all(installed[item["retrofit_id"]]() for item in events)


def validate_property(state, *, legacy=False):
    require(isinstance(state, dict) and set(state) == PROPERTY_KEYS)
    home = state["home"]
    require(isinstance(home, dict) and set(home) <= HOME_KEYS)
    require(isinstance(home.get("property_id"), str) and HOME_ID.fullmatch(home["property_id"]))
    if legacy:
        require(home["property_id"] in {f"DEMO-0{i}" for i in range(1, 5)})
    require(home.get("data_kind") == "synthetic_demo" and not engine.validate_home(home))
    require(home.get("property_type") in (
        None, "Detached", "Semi detached", "Mid terrace", "End terrace", "Bungalow", "Flat",
    ))
    require(home.get("age_band") is None or
            (type(home["age_band"]) is int and 1 <= home["age_band"] <= 5))
    require(home.get("region") in [None, "W92000004"] + [f"E1200000{i}" for i in range(1, 10)])
    preferences(state["preferences"], property_scope=True)
    # Missing keys stay missing in an exact v1 state. Present projections must
    # agree; the migration may not silently overwrite conflicting permissions.
    if "budget_gbp" in home:
        require(home["budget_gbp"] == state["preferences"]["budget_gbp"])
    if "excluded_retrofits" in home:
        require(home["excluded_retrofits"] == state["preferences"]["deferred_retrofits"])
    retrofit_list(state["selected_retrofits"])
    require(not set(state["selected_retrofits"]) & set(state["preferences"]["deferred_retrofits"]))
    require(state["review_status"] in ("new", "reviewing", "ready", "deferred"))
    require(state["baseline_status"] in ("current", "needs_update"))
    require(isinstance(state["events"], list) and len(state["events"]) <= MAX_EVENTS)
    event_ids, measures = set(), set()
    previous_created = -1
    for item in state["events"]:
        required = {"id", "kind", "retrofit_id", "completed_on", "created_at"}
        require(isinstance(item, dict) and required <= set(item)
                and set(item) <= required | {"planning_cost_upper_gbp"})
        require(isinstance(item["id"], str) and ID_PATTERN.fullmatch(item["id"]))
        require(item["id"] not in event_ids and item["retrofit_id"] not in measures)
        require(item["kind"] == "completed" and item["retrofit_id"] in engine.RETROFITS)
        event_ids.add(item["id"])
        measures.add(item["retrofit_id"])
        created = utc_timestamp(item["created_at"])
        require(created >= previous_created)
        previous_created = created
        require(isinstance(item["completed_on"], str)
                and re.fullmatch(r"\d{4}-\d\d-\d\d", item["completed_on"]))
        completed = date.fromisoformat(item["completed_on"])
        # Occurrence may be backdated but cannot have been known in the future
        # at recording time. London today may be UTC tomorrow during BST.
        require(completed <= datetime.fromtimestamp(created, ZoneInfo("Europe/London")).date())
        if "planning_cost_upper_gbp" in item:
            require(number(item["planning_cost_upper_gbp"]))
    require(not measures.intersection(state["selected_retrofits"]))
    require(completed_features_valid(home, state["events"]))
    if state["baseline_status"] == "needs_update":
        require(bool(state["events"]))
        require(home.get("electricity_kwh") is None or home.get("gas_kwh") is None)


def validate_settings(state):
    require(isinstance(state, dict) and set(state) == {
        "customer_preferences", "portfolio_budget_gbp", "legacy_completed_reserve_gbp",
    })
    preferences(state["customer_preferences"])
    for key in ("portfolio_budget_gbp", "legacy_completed_reserve_gbp"):
        require(state[key] is None or number(state[key]))


def load_state(raw):
    require(isinstance(raw, str) and len(raw.encode("utf-8")) <= MAX_STATE_BYTES)

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError("Invalid workspace JSON number.")

    return json.loads(raw, object_pairs_hook=object_pairs, parse_constant=bad_constant)


def _normal_sql(value):
    return re.sub(r'[\s()"]', "", value).lower()


def validate_schema(conn, version):
    inspector = inspect(conn)
    tables = [control, workspaces, customers] + ([properties] if version == 2 else [])
    owned = {name for name in inspector.get_table_names()
             if name == "workspaces" or name.startswith("workspace_")}
    require(owned == {table.name for table in tables})
    for table in tables:
        actual = [(c["name"], str(c["type"].compile(dialect=conn.dialect)), c["nullable"])
                  for c in inspector.get_columns(table.name)]
        expected = [(c.name, str(c.type.compile(dialect=conn.dialect)), c.nullable) for c in table.columns]
        require(actual == expected)
        require(inspector.get_pk_constraint(table.name)["constrained_columns"] ==
                [column.name for column in table.primary_key])
        actual_checks = {_normal_sql(c["sqltext"]) for c in inspector.get_check_constraints(table.name)}
        expected_checks = {_normal_sql(str(c.sqltext).replace("schema_version = 2", f"schema_version = {version}"))
                           for c in table.constraints if isinstance(c, CheckConstraint)}
        require(actual_checks == expected_checks)
        actual_unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints(table.name)}
        expected_unique = {tuple(col.name for col in c.columns) for c in table.constraints
                           if isinstance(c, UniqueConstraint)}
        require(actual_unique == expected_unique)
        actual_fk = {(tuple(c["constrained_columns"]), c["referred_table"],
                      tuple(c["referred_columns"]), c.get("options", {}).get("ondelete", "").upper())
                     for c in inspector.get_foreign_keys(table.name)}
        expected_fk = {(tuple(c.column_keys), c.elements[0].column.table.name,
                        tuple(e.column.name for e in c.elements), (c.ondelete or "").upper())
                       for c in table.foreign_key_constraints}
        require(actual_fk == expected_fk)
        actual_indexes = {(c["name"], tuple(c["column_names"]), bool(c["unique"]))
                          for c in inspector.get_indexes(table.name)
                          if not c.get("duplicates_constraint")}
        expected_indexes = {(c.name, tuple(col.name for col in c.columns), bool(c.unique))
                            for c in table.indexes if version == 2 or c is not customer_owner_index}
        require(actual_indexes == expected_indexes)


def validate_rows(conn, version):
    counters = conn.execute(select(control)).mappings().all()
    require(len(counters) == 1 and counters[0]["id"] == 1 and counters[0]["schema_version"] == version)
    counter = counters[0]
    require(type(counter["creations"]) is int and 0 <= counter["creations"] <= 1000)
    require(date.fromisoformat(counter["creation_day"]).isoformat() == counter["creation_day"])
    owners = conn.execute(select(workspaces)).mappings().all()
    parents = conn.execute(select(customers)).mappings().all()
    by_owner = {row["id"]: row for row in owners}
    require(len(by_owner) == len(owners) <= 1000)
    digests = set()
    for owner in owners:
        require(isinstance(owner["id"], str) and ID_PATTERN.fullmatch(owner["id"]))
        require(isinstance(owner["token_hash"], str) and re.fullmatch(r"[a-f0-9]{64}", owner["token_hash"]))
        require(owner["token_hash"] not in digests)
        digests.add(owner["token_hash"])
        require(type(owner["created_at"]) is int and owner["created_at"] >= 0)
        require(type(owner["expires_at"]) is int and owner["expires_at"] == owner["created_at"] + TTL_SECONDS)
        datetime.fromtimestamp(owner["expires_at"], timezone.utc)
    require(Counter(row["workspace_id"] for row in parents) ==
            Counter({key: CUSTOMERS_PER_WORKSPACE for key in by_owner}))
    slots = defaultdict(list)
    for row in parents:
        slots[row["workspace_id"]].append(row["slot"])
    for owner_id in by_owner:
        require(sorted(slots[owner_id]) == [1, 2, 3, 4])
    by_parent = {row["id"]: row for row in parents}
    seen_homes, seen_events = set(), set()

    def common(row):
        require(isinstance(row["id"], str) and ID_PATTERN.fullmatch(row["id"]))
        require(row["workspace_id"] in by_owner)
        require(type(row["version"]) is int and 1 <= row["version"] <= MAX_VERSION)
        require(type(row["updated_at"]) is int and row["updated_at"] >= by_owner[row["workspace_id"]]["created_at"])
        datetime.fromtimestamp(row["updated_at"], timezone.utc)

    def property_row(row, state):
        validate_property(state, legacy=version == 1)
        key = row["workspace_id"], state["home"]["property_id"]
        require(key not in seen_homes)
        seen_homes.add(key)
        for item in state["events"]:
            require(item["id"] not in seen_events)
            seen_events.add(item["id"])
            require(by_owner[row["workspace_id"]]["created_at"]
                    <= utc_timestamp(item["created_at"]) <= row["updated_at"])

    for row in parents:
        common(row)
        state = load_state(row["state_json"])
        if version == 1:
            property_row(row, state)
        else:
            validate_settings(state)
    if version == 2:
        children = conn.execute(select(properties)).mappings().all()
        by_customer = defaultdict(list)
        for row in children:
            common(row)
            require(row["customer_id"] in by_parent)
            parent = by_parent[row["customer_id"]]
            require(row["workspace_id"] == parent["workspace_id"] and row["updated_at"] <= parent["updated_at"])
            state = load_state(row["state_json"])
            require(row["home_id"] == state["home"]["property_id"])
            property_row(row, state)
            by_customer[row["customer_id"]].append((row, state))
        for parent in parents:
            owned = by_customer[parent["id"]]
            require(1 <= len(owned) <= MAX_PROPERTIES)
            require(sorted(row["slot"] for row, _ in owned) == list(range(1, len(owned) + 1)))
            check_allocation(load_state(parent["state_json"]), [state for _, state in owned])
    return counter, parents


def backup_before_upgrade(path):
    """Snapshot committed WAL data through a second reader while writer-locked.

    The caller has made no writes yet. Do not use backup() on the write
    connection itself, which would wait for its own transaction.
    """
    fd, name = tempfile.mkstemp(prefix=path.name + ".schema1-", suffix=".sqlite3", dir=path.parent)
    os.close(fd)  # mkstemp uses O_EXCL and 0600.
    destination = Path(name)
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as source:
            with sqlite3.connect(destination, timeout=5) as copy:
                source.backup(copy)
                require(copy.execute("PRAGMA integrity_check").fetchone() == ("ok",))
        with destination.open("rb") as stream:
            os.fsync(stream.fileno())
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def initialize(conn, sqlite_path=None):
    names = set(inspect(conn).get_table_names())
    owned = {name for name in names if name == "workspaces" or name.startswith("workspace_")}
    if not owned:
        metadata.create_all(conn)
        conn.execute(insert(control).values(id=1, schema_version=2, creation_day="1970-01-01", creations=0))
        validate_schema(conn, 2)
        validate_rows(conn, 2)
        return None
    require("workspace_control" in owned)
    counters = conn.execute(select(control)).mappings().all()
    require(len(counters) == 1)
    version = counters[0]["schema_version"]
    require(version in (1, 2))
    validate_schema(conn, version)
    counter, parents = validate_rows(conn, version)
    if version == 2:
        return None
    backup = backup_before_upgrade(sqlite_path) if sqlite_path else None
    customer_owner_index.create(conn)
    properties.create(conn)
    for parent in parents:
        state = load_state(parent["state_json"])
        pid = hashlib.sha256(("greenhome:property:v2:" + parent["id"]).encode("ascii")).hexdigest()[:32]
        conn.execute(insert(properties).values(
            id=pid, customer_id=parent["id"], workspace_id=parent["workspace_id"],
            slot=1, home_id=state["home"]["property_id"], version=parent["version"],
            state_json=parent["state_json"], updated_at=parent["updated_at"],
        ))
        conn.execute(update(customers).where(customers.c.id == parent["id"]).values(
            state_json=_state_json(neutral_settings(state)),
        ))
    # No table references this singleton. Replacing its v1 CHECK constraint is
    # transactional on both supported dialects; no writable_schema workaround.
    control.drop(conn)
    control.create(conn)
    conn.execute(insert(control).values(**{**dict(counter), "schema_version": 2}))
    validate_schema(conn, 2)
    validate_rows(conn, 2)
    return backup
