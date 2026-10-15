"""Optional PostgreSQL-backed provider budget shared by every service replica.

Provision the schema explicitly before enabling the URL. Runtime fails closed.
The existing private SQLite budget remains the default for a single-host demo.
"""
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import Column, Date, Integer, MetaData, Table, CheckConstraint, create_engine, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import make_url

from greenhome.provider_budget import BudgetExceeded, BudgetUnavailable

metadata = MetaData()
attempts = Table(
    "greenhome_provider_daily_budget", metadata,
    Column("utc_day", Date, primary_key=True),
    Column("used", Integer, nullable=False),
    CheckConstraint("used >= 0 AND used <= 10000"),
)


@lru_cache(maxsize=1)
def database(url):
    """Bounded pool; credentials/SQL parameters must never be logged."""
    try:
        parsed = make_url(url)
        if parsed.drivername != "postgresql+psycopg":
            raise ValueError()
        return create_engine(
            parsed, echo=False, hide_parameters=True, pool_pre_ping=True,
            pool_size=2, max_overflow=2, pool_timeout=2,
            connect_args={"connect_timeout": 3, "options": "-c statement_timeout=2000 -c timezone=UTC"},
        )
    except Exception:
        raise BudgetUnavailable("Shared provider budget is unavailable.") from None


def reserve(connection, day, limit):
    """Caller owns the transaction. Conditional UPDATE is the atomic admission."""
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise BudgetUnavailable("Shared provider budget is unavailable.")
    insert = pg_insert if connection.dialect.name == "postgresql" else sqlite_insert
    connection.execute(insert(attempts).values(utc_day=day, used=0).on_conflict_do_nothing(
        index_elements=["utc_day"],
    ))
    value = connection.execute(update(attempts).where(
        attempts.c.utc_day == day, attempts.c.used < limit,
    ).values(used=attempts.c.used + 1).returning(attempts.c.used)).scalar_one_or_none()
    if value is None:
        raise BudgetExceeded("Daily provider attempt limit reached.")


def consume(url, limit):
    try:
        with database(url).begin() as connection:
            # The shared database's UTC date avoids replica clock disagreement.
            day = connection.execute(text("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date")).scalar_one()
            reserve(connection, day, limit)
    except (BudgetExceeded, BudgetUnavailable):
        raise
    except Exception:
        raise BudgetUnavailable("Shared provider budget is unavailable.") from None
