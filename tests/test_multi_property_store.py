"""Storage-only invariants and process races; PostgreSQL compilation, not runtime."""
from copy import deepcopy
import json
import multiprocessing
import sqlite3

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from greenhome import workspace_migration
from greenhome.workspace_store import (
    MAX_VERSION, WorkspaceError, WorkspaceStore, customer_owner_index, customers,
    metadata, new_token, properties, token_hash, workspaces,
)
from test_workspace_store import NOW, full_seeds


def _sibling_worker(url, token, cid, pid, customer_version, property_version, start, output):
    store = WorkspaceStore(url, clock=lambda: NOW)
    try:
        store.warm()
        start.wait(20)

        def allocate(state, settings):
            state["selected_retrofits"] = ["loft_insulation"]
            return state

        result = store.mutate_property(token, cid, pid, customer_version, property_version, allocate)
        output.put(("ok", result["customers"][0]["budget_summary"]["total_reserved_gbp"]))
    except WorkspaceError as exc:
        output.put(("error", exc.status, exc.code))
    finally:
        store.close()


def test_separate_process_sibling_allocation_has_one_winner_and_no_rebase(tmp_path):
    url = f"sqlite:///{tmp_path}/siblings.sqlite3"
    token = new_token()
    store = WorkspaceStore(url, clock=lambda: NOW)
    workspace = store.create(token, full_seeds())
    customer = workspace["customers"][0]
    customer = store.add_property(token, customer["id"], customer["version"], full_seeds()[0])["customers"][0]
    customer = store.settings(token, customer["id"], customer["version"],
                              lambda state: {**state, "portfolio_budget_gbp": 1600})["customers"][0]
    ctx = multiprocessing.get_context("spawn")
    start, output = ctx.Event(), ctx.Queue()
    workers = [ctx.Process(target=_sibling_worker, args=(
        url, token, customer["id"], prop["id"], customer["version"], prop["version"], start, output,
    )) for prop in customer["properties"]]
    try:
        for worker in workers:
            worker.start()
        start.set()
        results = [output.get(timeout=30) for _ in workers]
        for worker in workers:
            worker.join(30)
            assert worker.exitcode == 0
        assert sorted(results) == [("error", 409, "stale_version"), ("ok", 1600)]
        result = store.get(token)["customers"][0]
        assert result["version"] == customer["version"] + 1
        assert result["budget_summary"]["remaining_gbp"] == 0
        assert sorted(prop["version"] - old["version"] for prop, old in
                      zip(result["properties"], customer["properties"])) == [0, 1]
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join()
        output.close()
        store.close()


def test_composite_fk_prevents_cross_workspace_owner_and_home_ids_are_workspace_unique(tmp_path):
    path = tmp_path / "fk.sqlite3"
    store = WorkspaceStore(f"sqlite:///{path}", clock=lambda: NOW)
    first_token = new_token()
    first = store.create(first_token, full_seeds())
    second = store.create(new_token(), full_seeds())
    parent = first["customers"][0]
    first = store.add_property(first_token, parent["id"], parent["version"], full_seeds()[0])
    props = first["customers"][0]["properties"]
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE workspace_properties SET workspace_id=? WHERE id=?", (second["id"], props[0]["id"]))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE workspace_properties SET customer_id=? WHERE id=?",
                       (second["customers"][0]["id"], props[0]["id"]))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE workspace_properties SET home_id=? WHERE id=?",
                       (props[0]["home"]["property_id"], props[1]["id"]))
    assert store.get(first_token) == first
    store.close()


@pytest.mark.parametrize("scope", ["customer", "property"])
def test_version_limit_rolls_back_without_incrementing_sibling_or_owner(tmp_path, scope):
    store = WorkspaceStore(f"sqlite:///{tmp_path}/versions.sqlite3", clock=lambda: NOW)
    token = new_token()
    customer = store.create(token, full_seeds())["customers"][0]
    customer = store.add_property(token, customer["id"], customer["version"], full_seeds()[0])["customers"][0]
    prop = customer["properties"][0]
    with store._transaction() as conn:
        table, identity = (customers, customer["id"]) if scope == "customer" else (properties, prop["id"])
        conn.execute(update(table).where(table.c.id == identity).values(version=MAX_VERSION))
    before = store.get(token)
    customer, prop = before["customers"][0], before["customers"][0]["properties"][0]
    with pytest.raises(WorkspaceError) as error:
        store.mutate_property(token, customer["id"], prop["id"], customer["version"], prop["version"],
                              lambda state, prefs: {**state, "review_status": "ready"})
    assert error.value.code == "version_limit"
    assert store.get(token) == before
    store.close()


def test_failed_property_callback_and_allocation_check_rollback_entire_transaction(tmp_path):
    store = WorkspaceStore(f"sqlite:///{tmp_path}/rollback.sqlite3", clock=lambda: NOW)
    token = new_token()
    customer = store.create(token, full_seeds())["customers"][0]
    customer = store.settings(token, customer["id"], customer["version"],
                              lambda state: {**state, "portfolio_budget_gbp": 0})["customers"][0]
    prop = customer["properties"][0]
    before = store.get(token)

    def fail(state, settings):
        state["review_status"] = "ready"
        raise ValueError("Injected validation failure.")

    with pytest.raises(ValueError):
        store.mutate_property(token, customer["id"], prop["id"], customer["version"], prop["version"], fail)
    assert store.get(token) == before

    def overspend(state, settings):
        state["selected_retrofits"] = ["loft_insulation"]
        return state

    with pytest.raises(WorkspaceError) as error:
        store.mutate_property(token, customer["id"], prop["id"], customer["version"], prop["version"], overspend)
    assert error.value.code == "portfolio_budget_exceeded"
    # The tentative property UPDATE precedes the allocation check, so this also
    # proves a budget failure rolls back a write already issued to the database.
    assert store.get(token) == before
    store.close()


def test_postgresql_v2_ddl_indexes_and_scoped_cas_compile_only():
    dialect = postgresql.dialect()
    ddl = "\n".join(str(CreateTable(table).compile(dialect=dialect)) for table in metadata.sorted_tables)
    assert "FOREIGN KEY(customer_id, workspace_id) REFERENCES workspace_customers (id, workspace_id) ON DELETE CASCADE" in ddl
    assert "UNIQUE (workspace_id, home_id)" in ddl and "UNIQUE (customer_id, slot)" in ddl
    assert "schema_version = 2" in ddl and "slot <= 8" in ddl
    assert "CREATE UNIQUE INDEX" in str(CreateIndex(customer_owner_index).compile(dialect=dialect))
    statement = update(properties).where(
        (properties.c.id == "a"*32) & (properties.c.customer_id == "b"*32)
        & (properties.c.workspace_id == "c"*32) & (properties.c.version == 4)
    ).values(version=properties.c.version + 1)
    sql = str(statement.compile(dialect=dialect))
    for name in ("id", "customer_id", "workspace_id", "version"):
        assert f"workspace_properties.{name} =" in sql
    snapshot = str(WorkspaceStore._snapshot().compile(dialect=dialect))
    assert "JOIN workspace_properties" in snapshot and "FOR UPDATE" not in snapshot
    locked = str(select(customers).where(customers.c.id == "a"*32).with_for_update().compile(dialect=dialect))
    assert "FOR UPDATE" in locked


def test_reflection_ignores_postgresql_duplicate_constraint_indexes_not_actual_extra_indexes(tmp_path, monkeypatch):
    """Exercise documented reflection shape without claiming a PostgreSQL run."""
    store = WorkspaceStore(f"sqlite:///{tmp_path}/reflection.sqlite3", clock=lambda: NOW)
    store.warm()
    real_inspect = workspace_migration.inspect

    class MirroredIndexes:
        def __init__(self, conn):
            self.original = real_inspect(conn)

        def __getattr__(self, name):
            return getattr(self.original, name)

        def get_indexes(self, table_name):
            indexes = self.original.get_indexes(table_name)
            for constraint in self.original.get_unique_constraints(table_name):
                indexes.append({
                    "name": "mirrored_unique", "column_names": constraint["column_names"],
                    "unique": True, "duplicates_constraint": "constraint_name",
                })
            return indexes

    monkeypatch.setattr(workspace_migration, "inspect", MirroredIndexes)
    with store._transaction() as conn:
        workspace_migration.validate_schema(conn, 2)
    store.close()
