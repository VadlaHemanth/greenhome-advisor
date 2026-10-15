"""No real environment, API key, provider call or network dependency."""
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
import multiprocessing
import os
from pathlib import Path
import sqlite3
import stat

import pytest

from greenhome import provider_budget as module
from greenhome.provider_budget import BudgetExceeded, BudgetUnavailable, ProviderBudget


STAMP = datetime(2026, 10, 10, 12, tzinfo=timezone.utc).timestamp()


def _attempt(arguments):
    path, limit = arguments
    try:
        ProviderBudget(Path(path), limit, clock=lambda: STAMP).consume()
        return "consumed"
    except BudgetExceeded:
        return "exceeded"
    except BudgetUnavailable:
        return "unavailable"


def _rows(path):
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT utc_day, attempts FROM provider_attempts ORDER BY utc_day").fetchall()


@pytest.fixture
def path(tmp_path):
    return tmp_path / "state" / "provider-budget.sqlite3"


@pytest.mark.parametrize("limit", [0, -1, 10001, True, False, 1.0, "100", None])
def test_invalid_limit_cannot_disable_accounting(path, limit):
    with pytest.raises(ValueError):
        ProviderBudget(path, limit)
    assert not path.exists()


def test_reservations_survive_new_instances_and_exhaustion(path):
    assert ProviderBudget(path, 2, lambda: STAMP).consume() is None
    ProviderBudget(path, 2, lambda: STAMP).consume()
    for _ in range(3):
        with pytest.raises(BudgetExceeded):
            ProviderBudget(path, 2, lambda: STAMP).consume()
    assert _rows(path) == [("2026-10-10", 2)]


def test_provider_failure_does_not_refund(path):
    budget = ProviderBudget(path, 1, lambda: STAMP)
    budget.consume()
    # Simulate failure AFTER reservation; caller must not decrement the count.
    with pytest.raises(RuntimeError):
        raise RuntimeError("Synthetic provider failure")
    with pytest.raises(BudgetExceeded):
        budget.consume()
    assert _rows(path)[0][1] == 1


def test_utc_midnight_rollover_and_backward_clock_do_not_erase_prior_day(path):
    before = datetime(2026, 10, 10, 23, 59, 59, tzinfo=timezone.utc).timestamp()
    clock = [before]
    budget = ProviderBudget(path, 1, lambda: clock[0])
    budget.consume()
    with pytest.raises(BudgetExceeded):
        budget.consume()
    clock[0] += 1
    budget.consume()
    clock[0] = before
    with pytest.raises(BudgetExceeded):
        budget.consume()
    assert _rows(path) == [("2026-10-10", 1), ("2026-10-11", 1)]


def test_concurrent_threads_do_not_overrun_shared_budget(path):
    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(_attempt, [(str(path), 11)] * 60))
    assert outcomes.count("consumed") == 11
    assert outcomes.count("exceeded") == 49
    assert _rows(path) == [("2026-10-10", 11)]


def test_concurrent_spawned_processes_persist_one_shared_count(path):
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        outcomes = list(pool.map(_attempt, [(str(path), 9)] * 30))
    assert outcomes.count("consumed") == 9
    assert outcomes.count("exceeded") == 21
    assert _rows(path) == [("2026-10-10", 9)]
    assert _attempt((str(path), 9)) == "exceeded"


def test_private_modes_and_database_contains_only_date_and_attempt_count(path):
    path.parent.mkdir(mode=0o755)
    path.touch(mode=0o644)
    ProviderBudget(path, 100, lambda: STAMP).consume()
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with sqlite3.connect(path) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert tables == [("provider_attempts",)]
        columns = connection.execute("PRAGMA table_info(provider_attempts)").fetchall()
        assert [column[1] for column in columns] == ["utc_day", "attempts"]
    assert _rows(path) == [("2026-10-10", 1)]


def test_corrupt_database_fails_closed_without_replacing_it(path):
    path.parent.mkdir()
    corrupt = b"not a database: SYNTHETIC_SECRET"
    path.write_bytes(corrupt)
    with pytest.raises(BudgetUnavailable) as caught:
        ProviderBudget(path, 100).consume()
    assert str(caught.value) == "Provider attempt budget is unavailable."
    assert path.read_bytes() == corrupt


def test_database_lock_fails_closed_then_releases_cleanly(path, monkeypatch):
    budget = ProviderBudget(path, 100, lambda: STAMP)
    budget.consume()
    monkeypatch.setattr(module, "LOCK_TIMEOUT_SECONDS", 0.02)
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(BudgetUnavailable):
            budget.consume()
    finally:
        connection.rollback()
        connection.close()
    assert _rows(path) == [("2026-10-10", 1)]
    budget.consume()
    assert _rows(path) == [("2026-10-10", 2)]


def test_permission_error_fails_closed_without_logging(path, monkeypatch, capsys, caplog):
    def denied(*args, **kwargs):
        raise PermissionError("SYNTHETIC_PRIVATE_PATH")
    monkeypatch.setattr(module.os, "open", denied)
    with pytest.raises(BudgetUnavailable) as caught:
        ProviderBudget(path, 100).consume()
    captured = capsys.readouterr()
    assert "SYNTHETIC_PRIVATE" not in str(caught.value) + captured.out + captured.err + caplog.text


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_symlink_storage_is_rejected(path, tmp_path, kind):
    target = tmp_path / "target"
    if kind == "directory":
        target.mkdir()
        path.parent.symlink_to(target, target_is_directory=True)
    else:
        path.parent.mkdir()
        target.touch()
        path.symlink_to(target)
    with pytest.raises(BudgetUnavailable):
        ProviderBudget(path, 100).consume()


@pytest.mark.parametrize("stamp", [None, True, float("nan"), float("inf"), 10**400])
def test_invalid_clock_fails_closed(path, stamp):
    with pytest.raises(BudgetUnavailable):
        ProviderBudget(path, 100, lambda: stamp).consume()


def test_wrong_schema_fails_closed(path):
    path.parent.mkdir()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE provider_attempts(utc_day TEXT, attempts INTEGER, secret TEXT)"
        )
    with pytest.raises(BudgetUnavailable):
        ProviderBudget(path, 100).consume()


def test_invalid_existing_count_is_not_reset(path):
    path.parent.mkdir()
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE provider_attempts(utc_day TEXT, attempts INTEGER)")
        connection.execute("INSERT INTO provider_attempts VALUES('2026-10-10', -1)")
    with pytest.raises(BudgetUnavailable):
        ProviderBudget(path, 100, lambda: STAMP).consume()
    assert _rows(path) == [("2026-10-10", -1)]


def test_commit_failure_does_not_authorise_or_persist_an_attempt(path, monkeypatch):
    budget = ProviderBudget(path, 5, lambda: STAMP)
    budget.consume()
    real_connect = sqlite3.connect

    class CommitFailure(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql == "COMMIT":
                raise sqlite3.OperationalError("SYNTHETIC_PRIVATE_STORAGE_ERROR")
            return super().execute(sql, parameters)

    monkeypatch.setattr(module.sqlite3, "connect", lambda *args, **kwargs: real_connect(
        *args, **kwargs, factory=CommitFailure
    ))
    with pytest.raises(BudgetUnavailable) as caught:
        budget.consume()
    assert "SYNTHETIC_PRIVATE" not in str(caught.value)
    assert _rows(path) == [("2026-10-10", 1)]


def test_cleanup_failure_also_has_generic_fail_closed_exception(path, monkeypatch):
    budget = ProviderBudget(path, 1, lambda: STAMP)
    budget.consume()
    real_connect = sqlite3.connect

    class RollbackFailure(sqlite3.Connection):
        def rollback(self):
            raise sqlite3.OperationalError("SYNTHETIC_PRIVATE_CLEANUP_ERROR")

    monkeypatch.setattr(module.sqlite3, "connect", lambda *args, **kwargs: real_connect(
        *args, **kwargs, factory=RollbackFailure
    ))
    with pytest.raises(BudgetUnavailable) as caught:
        budget.consume()
    assert "SYNTHETIC_PRIVATE" not in str(caught.value)
