from datetime import date
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select

from greenhome.shared_budget import attempts, metadata, reserve, database
from greenhome.provider_budget import BudgetExceeded, BudgetUnavailable


def test_shared_reservation_concurrency_persistence(tmp_path):
    url = f"sqlite:///{tmp_path}/counter.sqlite3"
    engine = create_engine(url, connect_args={"timeout":5})
    metadata.create_all(engine)
    day = date(2026,10,10)
    def attempt(_):
        try:
            with engine.begin() as conn:
                reserve(conn, day, 10)
            return True
        except BudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(40))) == 10
    engine.dispose()
    second = create_engine(url)
    with second.begin() as conn:
        assert conn.execute(select(attempts.c.used)).scalar_one() == 10
        with pytest.raises(BudgetExceeded):
            reserve(conn, day, 10)
        reserve(conn, date(2026,10,11), 10)
    second.dispose()


def test_invalid_url_does_not_expose_configuration():
    with pytest.raises(BudgetUnavailable) as err:
        database("bad://secret-value")
    assert "secret-value" not in str(err.value)


def test_invalid_limit_fails_closed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/counter.sqlite3")
    metadata.create_all(engine)
    with engine.begin() as conn:
        with pytest.raises(BudgetUnavailable):
            reserve(conn, date(2026,10,10), 0)
    engine.dispose()
