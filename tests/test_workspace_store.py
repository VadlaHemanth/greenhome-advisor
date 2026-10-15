"""Real local SQLite persistence and cross-process concurrency, not PostgreSQL proof."""
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import sqlite3
import threading
import time

import pytest
from sqlalchemy import event, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from greenhome.workspace_store import (
    MAX_STATE_BYTES, TTL_SECONDS, WorkspaceError, WorkspaceStore, customers,
    metadata, new_token, token_hash,
)

NOW = 1_791_590_400


def seeds():
    return [{
        "home": {"property_id": f"DEMO-0{i}", "data_kind": "synthetic_demo"},
        "preferences": {"budget_gbp": None, "deferred_retrofits": [], "priority": "energy", "disruption": "flexible"},
        "selected_retrofits": [], "review_status": "new", "baseline_status": "current", "events": [],
    } for i in range(1, 5)]


def _worker_update(url, token, customer_id, start, output):
    store = WorkspaceStore(url, clock=lambda: NOW)
    start.wait(20)
    try:
        def change(current):
            current["review_status"] = "ready"
            return current
        result = store.mutate(token, customer_id, 1, change)
        output.put(("ok", result["customers"][0]["version"]))
    except WorkspaceError as exc:
        output.put(("error", exc.status))
    finally:
        store.close()


def _worker_create(url, start, output):
    store = WorkspaceStore(url, max_workspaces=1, clock=lambda: NOW)
    start.wait(20)
    try:
        store.create(new_token(), seeds())
        output.put(200)
    except WorkspaceError as exc:
        output.put(exc.status)
    finally:
        store.close()


def _worker_restore(url, token, output):
    store = WorkspaceStore(url, clock=lambda: NOW)
    try:
        output.put(store.get(token))
    finally:
        store.close()


def full_seeds():
    from greenhome.engine import demo_homes
    customers_ = seeds()
    for customer, home in zip(customers_, demo_homes()):
        customer["home"] = home
        customer["preferences"]["budget_gbp"] = home["budget_gbp"]
    return customers_


def _burst(stores, count):
    barrier = threading.Barrier(count)
    seed_data = full_seeds()

    def create_and_read(i):
        token = new_token()
        store = stores[i % len(stores)]
        barrier.wait(timeout=30)
        workspace = store.create(token, seed_data)
        for _ in range(3):
            assert store.get(token) == workspace
        return workspace["id"]

    with ThreadPoolExecutor(count) as pool:
        return list(pool.map(create_and_read, range(count)))


def _worker_burst(url, start, output):
    store = WorkspaceStore(url, clock=lambda: NOW)
    try:
        store._ensure_engine()
        start.wait(30)
        output.put(_burst([store], 50))
    finally:
        store.close()


def run_processes(target, args, count=2):
    ctx = multiprocessing.get_context("spawn")
    start, output = ctx.Event(), ctx.Queue()
    workers = [ctx.Process(target=target, args=(*args, start, output)) for _ in range(count)]
    try:
        for worker in workers:
            worker.start()
        start.set()
        results = [output.get(timeout=30) for _ in workers]
        for worker in workers:
            worker.join(30)
            assert worker.exitcode == 0
        return results
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join()
        output.close()


def test_separate_processes_compare_and_swap_one_winner(tmp_path):
    url = f"sqlite:///{tmp_path}/memory.sqlite3"
    store = WorkspaceStore(url, clock=lambda: NOW)
    token = new_token()
    workspace = store.create(token, seeds())
    store.close()
    results = run_processes(_worker_update, (url, token, workspace["customers"][0]["id"]))
    assert sorted(results) == [("error", 409), ("ok", 2)]
    restored = WorkspaceStore(url, clock=lambda: NOW)
    assert restored.get(token)["customers"][0]["version"] == 2
    restored.close()


def test_concurrent_cold_start_global_quota_across_processes(tmp_path):
    url = f"sqlite:///{tmp_path}/memory.sqlite3"
    assert sorted(run_processes(_worker_create, (url,))) == [200, 429]
    with sqlite3.connect(tmp_path / "memory.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM workspace_customers").fetchone()[0] == 4
        assert db.execute("SELECT creations FROM workspace_control").fetchone()[0] == 1


def test_restart_in_new_python_process_returns_exact_workspace(tmp_path):
    url = f"sqlite:///{tmp_path}/memory.sqlite3"
    store = WorkspaceStore(url, clock=lambda: NOW)
    token = new_token()
    original = store.create(token, seeds())
    store.close()
    ctx = multiprocessing.get_context("spawn")
    output = ctx.Queue()
    worker = ctx.Process(target=_worker_restore, args=(url, token, output))
    worker.start()
    try:
        assert output.get(timeout=30) == original
        worker.join(30)
        assert worker.exitcode == 0
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join()
        output.close()


@pytest.mark.parametrize("instances", [1, 2])
def test_100_thread_creation_and_300_reads_are_isolated(tmp_path, instances):
    url = f"sqlite:///{tmp_path}/burst.sqlite3"
    stores = [WorkspaceStore(url, clock=lambda: NOW) for _ in range(instances)]
    try:
        for store in stores:
            store._ensure_engine()
        identities = _burst(stores, 100)
        assert len(set(identities)) == 100
        with sqlite3.connect(tmp_path / "burst.sqlite3") as db:
            assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 100
            assert db.execute("SELECT count(*) FROM workspace_customers").fetchone()[0] == 400
    finally:
        for store in stores:
            store.close()


def test_two_processes_with_50_threads_each_creation_read_burst(tmp_path):
    groups = run_processes(_worker_burst, (f"sqlite:///{tmp_path}/burst.sqlite3",))
    ids = [identity for group in groups for identity in group]
    assert len(ids) == len(set(ids)) == 100


def test_get_is_one_snapshot_select_and_never_prunes_or_locks_owner(tmp_path, monkeypatch):
    store = WorkspaceStore(f"sqlite:///{tmp_path}/memory.sqlite3", clock=lambda: NOW)
    token = new_token()
    original = store.create(token, seeds())
    statements = []

    def forbidden(*args, **kwargs):
        pytest.fail("A read must not prune or enter the write-only owner-lock path.")

    monkeypatch.setattr(store, "prune_expired", forbidden)
    monkeypatch.setattr(store, "_owner", forbidden)

    @event.listens_for(store._engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.upper())

    assert store.get(token) == original
    assert sum(statement.startswith("SELECT ") for statement in statements) == 1
    assert "BEGIN" in statements
    assert "PRAGMA QUERY_ONLY = ON" in statements
    assert not any(any(term in statement for term in (
        "BEGIN IMMEDIATE", "FOR UPDATE", "DELETE ", "UPDATE ", "INSERT ", "CREATE ",
    )) for statement in statements)
    store.close()


def test_read_progresses_during_uncommitted_write_and_sees_consistent_snapshot(tmp_path):
    url = f"sqlite:///{tmp_path}/memory.sqlite3"
    store, reader = WorkspaceStore(url, clock=lambda: NOW), WorkspaceStore(url, clock=lambda: NOW)
    token = new_token()
    original = store.create(token, seeds())
    reader._ensure_engine()
    try:
        with ThreadPoolExecutor(1) as pool:
            with store._transaction() as conn:
                conn.execute(update(customers).where(
                    customers.c.id == original["customers"][0]["id"]
                ).values(version=2))
                # Must finish BEFORE releasing the writer, not after its commit.
                future = pool.submit(reader.get, token)
                assert future.result(timeout=2) == original
            current = reader.get(token)
            assert current["customers"][0]["version"] == 2
            assert current["customers"][1:] == original["customers"][1:]
    finally:
        store.close()
        reader.close()


def test_readonly_transaction_rejects_writes(tmp_path):
    store = WorkspaceStore(f"sqlite:///{tmp_path}/memory.sqlite3", clock=lambda: NOW)
    token = new_token()
    original = store.create(token, seeds())
    with pytest.raises(WorkspaceError) as exc:
        with store._transaction(readonly=True) as conn:
            conn.execute(update(customers).values(version=2))
    assert exc.value.status == 503
    assert store.get(token) == original
    store.close()


def test_write_admission_timeout_never_mutates_or_blocks_reads(tmp_path, monkeypatch):
    from greenhome import workspace_store
    store = WorkspaceStore(f"sqlite:///{tmp_path}/memory.sqlite3", clock=lambda: NOW)
    token = new_token()
    original = store.create(token, seeds())
    monkeypatch.setattr(workspace_store, "WRITE_QUEUE_WAIT_SECONDS", 0.01)
    store._write_gate.acquire()
    try:
        assert store.get(token) == original
        with pytest.raises(WorkspaceError) as exc:
            store.mutate(token, original["customers"][0]["id"], 1, lambda state: state)
        assert exc.value.code == "workspace_busy"
    finally:
        store._write_gate.release()
    assert store.get(token) == original
    store.close()


def test_cleanup_is_throttled_on_creation_but_capacity_always_forces_it(tmp_path):
    store = WorkspaceStore(f"sqlite:///{tmp_path}/memory.sqlite3", max_workspaces=2, clock=lambda: NOW)
    store._ensure_engine()
    statements = []

    @event.listens_for(store._engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.upper())

    store.create(new_token(), seeds())
    store.create(new_token(), seeds())
    assert sum(statement.startswith("DELETE FROM WORKSPACES") for statement in statements) == 1
    # Even a very distant efficiency hint cannot bypass row bounds or hold capacity.
    store._next_prune_at = time.monotonic() + 100_000
    store.clock = lambda: NOW + TTL_SECONDS
    store.create(new_token(), seeds())
    assert sum(statement.startswith("DELETE FROM WORKSPACES") for statement in statements) == 2
    with sqlite3.connect(tmp_path / "memory.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 1
    store.close()

def test_state_byte_limit_and_callback_failures_rollback(tmp_path):
    store = WorkspaceStore(f"sqlite:///{tmp_path}/memory.sqlite3", clock=lambda: NOW)
    token = new_token()
    original = store.create(token, seeds())
    cid = original["customers"][0]["id"]

    def oversized(state):
        state["home"]["unexpected"] = "x" * MAX_STATE_BYTES
        return state

    with pytest.raises(WorkspaceError) as exc:
        store.mutate(token, cid, 1, oversized)
    assert exc.value.status == 413
    assert store.get(token) == original

    def failed(state):
        state["review_status"] = "ready"
        raise ValueError("Failed validation.")

    with pytest.raises(ValueError):
        store.mutate(token, cid, 1, failed)
    assert store.get(token) == original
    store.close()


def test_history_limit_cannot_be_bypassed_at_storage_boundary(tmp_path):
    store = WorkspaceStore(f"sqlite:///{tmp_path}/memory.sqlite3", clock=lambda: NOW)
    token = new_token()
    original = store.create(token, seeds())

    def huge_history(state):
        state["events"] = [{}] * 21
        return state

    with pytest.raises(WorkspaceError) as exc:
        store.mutate(token, original["customers"][0]["id"], 1, huge_history)
    assert exc.value.code == "history_limit"
    assert store.get(token) == original
    store.close()


def test_expiry_cascades_and_frees_active_capacity(tmp_path):
    store = WorkspaceStore(f"sqlite:///{tmp_path}/memory.sqlite3", max_workspaces=1, clock=lambda: NOW)
    old = new_token()
    store.create(old, seeds())
    store.clock = lambda: NOW + TTL_SECONDS
    with pytest.raises(WorkspaceError) as exc:
        store.get(old)
    assert exc.value.status == 401
    current = store.create(new_token(), seeds())
    assert len(current["customers"]) == 4
    with sqlite3.connect(tmp_path / "memory.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM workspace_customers").fetchone()[0] == 4
    store.close()


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:", "mysql://localhost/db",
                                "sqlite:///file.db?uri=true", "not a database url"])
def test_storage_rejects_unsupported_or_ephemeral_configuration(url):
    with pytest.raises(ValueError):
        WorkspaceStore(url)


@pytest.mark.parametrize("quota", [0, -1, 1001, True, 1.5])
def test_quotas_have_hard_upper_bounds(tmp_path, quota):
    with pytest.raises(ValueError):
        WorkspaceStore(f"sqlite:///{tmp_path}/memory.sqlite3", max_workspaces=quota)
    with pytest.raises(ValueError):
        WorkspaceStore(f"sqlite:///{tmp_path}/memory.sqlite3", max_creations_per_day=quota)


def test_symlink_database_rejected_without_modifying_target(tmp_path):
    target = tmp_path / "do-not-touch"
    target.write_text("preserved")
    path = tmp_path / "memory.sqlite3"
    path.symlink_to(target)
    store = WorkspaceStore(f"sqlite:///{path}")
    with pytest.raises(WorkspaceError) as exc:
        store.create(new_token(), seeds())
    assert exc.value.status == 503
    assert target.read_text() == "preserved"


def test_postgresql_schema_compiles_only_not_runtime_proof():
    dialect = postgresql.dialect()
    rendered = "\n".join(str(CreateTable(table).compile(dialect=dialect)) for table in metadata.sorted_tables)
    assert "ON DELETE CASCADE" in rendered
    assert "BIGINT" in rendered
    assert "length(state_json) <= 16384" in rendered
    statement = customers.update().where(
        (customers.c.id == "a" * 32) & (customers.c.workspace_id == "b" * 32) & (customers.c.version == 1)
    ).values(version=customers.c.version + 1)
    compiled = str(statement.compile(dialect=dialect))
    assert "workspace_customers.version =" in compiled
    # Parsing/building configuration opens no PostgreSQL connection.
    store = WorkspaceStore("postgresql+psycopg://localhost/greenhome")
    assert not store.sqlite and store._engine is None


def test_only_digest_is_stored_and_export_excludes_internal_schema(tmp_path):
    store = WorkspaceStore(f"sqlite:///{tmp_path}/memory.sqlite3", clock=lambda: NOW)
    token = new_token()
    exported = store.create(token, seeds())
    with sqlite3.connect(tmp_path / "memory.sqlite3") as db:
        assert db.execute("SELECT token_hash FROM workspaces").fetchone()[0] == token_hash(token)
        dumped = "\n".join(db.iterdump())
    assert token not in dumped
    assert "token_hash" not in repr(exported)
    assert "creation_day" not in repr(exported)
    store.close()


def test_warm_initializes_schema_without_opt_in_or_customer_records(tmp_path):
    path = tmp_path / "warm.sqlite3"
    store = WorkspaceStore(f"sqlite:///{path}")
    assert store.warm() is None
    assert store.warm() is None  # Idempotent in the same worker.
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT schema_version, creations FROM workspace_control").fetchone() == (2, 0)
        assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM workspace_customers").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM workspace_properties").fetchone()[0] == 0
    store.close()


def test_warm_hides_initialization_failure_details(tmp_path, monkeypatch):
    store = WorkspaceStore(f"sqlite:///{tmp_path}/warm.sqlite3")

    def fail():
        raise ValueError("PRIVATE_DRIVER_CONFIGURATION")

    monkeypatch.setattr(store, "_ensure_engine", fail)
    with pytest.raises(WorkspaceError) as exc:
        store.warm()
    assert exc.value.status == 503
    assert "PRIVATE_DRIVER_CONFIGURATION" not in str(exc.value)


def test_warm_rejects_unexpected_existing_schema_without_migrating(tmp_path):
    path = tmp_path / "warm.sqlite3"
    store = WorkspaceStore(f"sqlite:///{path}")
    store.warm()
    store.close()
    with sqlite3.connect(path) as db:
        db.execute("ALTER TABLE workspace_customers ADD COLUMN unexpected TEXT")
    new_worker = WorkspaceStore(f"sqlite:///{path}")
    with pytest.raises(WorkspaceError) as exc:
        new_worker.warm()
    assert exc.value.status == 503
    assert new_worker._engine is None
