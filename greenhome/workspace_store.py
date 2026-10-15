"""Bounded fictional workspace persistence; bearer secrets never enter the database."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time
from typing import Callable

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, ForeignKey, ForeignKeyConstraint, Index,
    Integer, MetaData, String,
    Table, Text, UniqueConstraint, create_engine, delete, event, func, insert,
    select, update,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

TTL_SECONDS = 30 * 24 * 60 * 60
MAX_WORKSPACES = 1000
MAX_CREATIONS_PER_DAY = 1000
CUSTOMERS_PER_WORKSPACE = 4
MAX_PROPERTIES = 8
MAX_EVENTS = 20
MAX_STATE_BYTES = 16 * 1024
MAX_VERSION = 2_147_483_647
PRUNE_INTERVAL_SECONDS = 60
WRITE_QUEUE_WAIT_SECONDS = 5
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
NOTE = "Private fictional workspace; not a bank account or shared adviser access."

metadata = MetaData()
control = Table(
    "workspace_control", metadata,
    Column("id", Integer, primary_key=True),
    Column("schema_version", Integer, nullable=False),
    Column("creation_day", String(10), nullable=False),
    Column("creations", Integer, nullable=False),
    CheckConstraint("id = 1 AND schema_version = 2"),
    CheckConstraint(f"creations >= 0 AND creations <= {MAX_CREATIONS_PER_DAY}"),
)
workspaces = Table(
    "workspaces", metadata,
    Column("id", String(32), primary_key=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created_at", BigInteger, nullable=False),
    Column("expires_at", BigInteger, nullable=False, index=True),
    CheckConstraint(f"expires_at = created_at + {TTL_SECONDS}"),
)
customers = Table(
    "workspace_customers", metadata,
    Column("id", String(32), primary_key=True),
    Column("workspace_id", String(32), ForeignKey("workspaces.id", ondelete="CASCADE"),
           nullable=False, index=True),
    Column("slot", Integer, nullable=False),
    Column("version", Integer, nullable=False),
    Column("state_json", Text, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    UniqueConstraint("workspace_id", "slot"),
    CheckConstraint(f"slot >= 1 AND slot <= {CUSTOMERS_PER_WORKSPACE}"),
    CheckConstraint(f"version >= 1 AND version <= {MAX_VERSION}"),
    CheckConstraint(f"length(state_json) <= {MAX_STATE_BYTES}"),
)
# The composite key prevents a property from naming a customer in another
# workspace, including in direct SQL. An index is additive for the v1 migration.
customer_owner_index = Index("uq_workspace_customers_owner", customers.c.id,
                             customers.c.workspace_id, unique=True)
properties = Table(
    "workspace_properties", metadata,
    Column("id", String(32), primary_key=True),
    Column("customer_id", String(32), nullable=False, index=True),
    Column("workspace_id", String(32), nullable=False),
    Column("slot", Integer, nullable=False),
    Column("home_id", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("state_json", Text, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
    ForeignKeyConstraint(["customer_id", "workspace_id"],
                         ["workspace_customers.id", "workspace_customers.workspace_id"],
                         ondelete="CASCADE"),
    UniqueConstraint("workspace_id", "home_id"),
    UniqueConstraint("customer_id", "slot"),
    CheckConstraint(f"slot >= 1 AND slot <= {MAX_PROPERTIES}"),
    CheckConstraint(f"version >= 1 AND version <= {MAX_VERSION}"),
    CheckConstraint(f"length(state_json) <= {MAX_STATE_BYTES}"),
)


class WorkspaceError(Exception):
    """Static, non-sensitive boundary errors."""

    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def invalid(message="Invalid fictional workspace input."):
    return WorkspaceError(422, "invalid_workspace_input", message)


def unauthorized():
    return WorkspaceError(401, "workspace_required", "Save a fictional demo workspace first.")


def iso_utc(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def token_hash(token: str | None) -> str:
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        raise unauthorized()
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _state_json(state: dict) -> str:
    """Bound the whole stored state, not just individual incoming fields."""
    if len(state.get("events", [])) > MAX_EVENTS:
        raise WorkspaceError(409, "history_limit", "This customer's completion history is full.")
    encoded = json.dumps(state, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode("ascii")) > MAX_STATE_BYTES:
        raise WorkspaceError(413, "state_limit", "The fictional customer state is too large.")
    return encoded


def neutral_settings(state=None):
    return {
        "customer_preferences": {
            "deferred_retrofits": [], "priority": "energy", "disruption": "flexible",
        },
        "portfolio_budget_gbp": None,
        "legacy_completed_reserve_gbp": (
            None if state and any("planning_cost_upper_gbp" not in item
                                  for item in state["events"]) else 0
        ),
    }


def effective_home(state, settings):
    """A read/assessment projection; never overwrite a sibling's raw facts."""
    home = deepcopy(state["home"])
    universal = settings["customer_preferences"]["deferred_retrofits"]
    if universal:
        home["excluded_retrofits"] = list(dict.fromkeys(
            state["preferences"]["deferred_retrofits"] + universal
        ))
    return home


def budget_summary(settings, states):
    from greenhome.engine import RETROFITS
    planned = sum(RETROFITS[rid]["cost_gbp"][1]
                  for state in states for rid in state["selected_retrofits"])
    legacy = settings["legacy_completed_reserve_gbp"]
    completed = None if legacy is None else legacy + sum(
        item.get("planning_cost_upper_gbp", 0)
        for state in states for item in state["events"]
    )
    total = None if completed is None else planned + completed
    cap = settings["portfolio_budget_gbp"]
    return {
        "planned_upper_gbp": planned, "completed_reserved_gbp": completed,
        "total_reserved_gbp": total,
        "remaining_gbp": None if cap is None or total is None else cap - total,
        "status": "needs_cost_evidence" if total is None else
                  "unlimited" if cap is None else "within_budget",
    }


def check_allocation(settings, states):
    excluded = set(settings["customer_preferences"]["deferred_retrofits"])
    if any(excluded.intersection(state["selected_retrofits"]) for state in states):
        raise WorkspaceError(409, "exclusion_conflict",
                             "A customer-wide exclusion conflicts with a saved property plan.")
    summary = budget_summary(settings, states)
    if settings["portfolio_budget_gbp"] is not None:
        if summary["total_reserved_gbp"] is None:
            raise WorkspaceError(409, "needs_cost_evidence",
                                 "Explicitly confirm the legacy planning reserve before setting a shared cap.")
        if summary["remaining_gbp"] < 0:
            raise WorkspaceError(409, "portfolio_budget_exceeded",
                                 "The shared cap cannot cover all planned and completed reservations.")
    return summary


class WorkspaceStore:
    """SQLAlchemy Core store. All mutation callbacks run inside the atomic write.

    SQLite writes use finite-wait BEGIN IMMEDIATE transactions and WAL;
    reads use a single snapshot SELECT without a write lock or opportunistic GC.
    PostgreSQL writes use row locks plus a compare-and-swap customer UPDATE.
    No Python lock/cache owns authorization, quotas, expiry, or version correctness.
    """

    def __init__(self, database_url: str, *, max_workspaces=MAX_WORKSPACES,
                 max_creations_per_day=MAX_CREATIONS_PER_DAY,
                 clock: Callable[[], float] = time.time):
        for value, maximum in ((max_workspaces, MAX_WORKSPACES),
                               (max_creations_per_day, MAX_CREATIONS_PER_DAY)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("Workspace quotas must be positive bounded integers.")
        try:
            url = make_url(database_url)
        except Exception:
            raise ValueError("Invalid workspace database configuration.") from None
        if url.drivername not in ("sqlite", "sqlite+pysqlite", "postgresql+psycopg"):
            raise ValueError("Use file SQLite or postgresql+psycopg for workspace storage.")
        self.sqlite = url.get_backend_name() == "sqlite"
        self.path = None
        if self.sqlite:
            if (not url.database or url.database == ":memory:" or url.query
                    or url.username or url.password or url.host or url.port):
                raise ValueError("Workspace SQLite storage requires a regular persistent file.")
            self.path = Path(url.database).absolute()
            url = url.set(database=str(self.path))
        self._url = url
        self.max_workspaces = max_workspaces
        self.max_creations_per_day = max_creations_per_day
        self.clock = clock
        self._engine = None
        self._init_lock = threading.Lock()
        # Admission only, not a correctness lock: the database still owns all
        # cross-process serialization. Reads never join this local write queue.
        self._write_gate = threading.Lock()
        self._next_prune_at = 0.0
        self.last_migration_backup = None

    @classmethod
    def from_environment(cls):
        default_path = Path(__file__).resolve().parents[1] / "state" / "workspaces.sqlite3"
        try:
            return cls(
                os.environ.get("GREENHOME_WORKSPACE_DATABASE_URL", f"sqlite:///{default_path}"),
                max_workspaces=int(os.environ.get("GREENHOME_WORKSPACE_MAX_WORKSPACES", "1000")),
                max_creations_per_day=int(os.environ.get("GREENHOME_WORKSPACE_MAX_CREATIONS_PER_DAY", "1000")),
            )
        except Exception:
            # Database URLs may contain credentials; never chain their parse errors.
            raise ValueError("Invalid workspace storage configuration.") from None

    def now(self) -> int:
        stamp = self.clock()
        if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0:
            raise ValueError("Invalid workspace clock.")
        return int(stamp)

    def _prepare_file(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = self.path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid():
            raise OSError("Unsafe workspace storage directory.")
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
                raise OSError("Unsafe workspace database file.")
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)

    def _ensure_engine(self):
        if self._engine is not None:
            return self._engine
        with self._init_lock:
            if self._engine is not None:
                return self._engine
            if self.sqlite:
                self._prepare_file()
            options = {"hide_parameters": True, "echo": False}
            if self.sqlite:
                options.update(poolclass=NullPool, connect_args={"timeout": 5, "check_same_thread": False})
            else:
                options.update(
                    pool_size=5, max_overflow=0, pool_timeout=5, pool_pre_ping=True,
                    connect_args={"connect_timeout": 5,
                                  "options": "-c statement_timeout=10000 -c lock_timeout=5000"},
                )
            db = create_engine(self._url, **options)
            if self.sqlite:
                @event.listens_for(db, "connect")
                def configure_connection(connection, _):
                    connection.isolation_level = None
                    cursor = connection.cursor()
                    cursor.execute("PRAGMA foreign_keys = ON")
                    cursor.execute("PRAGMA busy_timeout = 5000")
                    cursor.execute("PRAGMA synchronous = FULL")
                    cursor.execute("PRAGMA secure_delete = ON")
                    cursor.close()

                @event.listens_for(db, "begin")
                def begin_transaction(connection):
                    if connection.get_execution_options().get("workspace_readonly"):
                        connection.exec_driver_sql("PRAGMA query_only = ON")
                        connection.exec_driver_sql("BEGIN")
                    else:
                        connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                if self.sqlite:
                    # Journal mode is persistent; configure once at initialization,
                    # never on the hot connection/read path or inside a transaction.
                    raw = db.raw_connection()
                    try:
                        cursor = raw.cursor()
                        if cursor.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
                            if cursor.execute("PRAGMA journal_mode = WAL").fetchone()[0].lower() != "wal":
                                raise OSError("Workspace WAL mode is unavailable.")
                        cursor.close()
                    finally:
                        raw.close()
                with db.begin() as conn:
                    if not self.sqlite:
                        # Serialize first schema creation by independent app workers.
                        conn.exec_driver_sql("SELECT pg_advisory_xact_lock(225301001)")
                    from greenhome.workspace_migration import initialize
                    self.last_migration_backup = initialize(conn, self.path)
            except Exception:
                db.dispose()
                raise
            self._engine = db
            return db

    @contextmanager
    def _transaction(self, *, readonly=False):
        gated = self.sqlite and not readonly
        if gated and not self._write_gate.acquire(timeout=WRITE_QUEUE_WAIT_SECONDS):
            raise WorkspaceError(503, "workspace_busy", "Workspace storage is busy. Try again later.")
        try:
            with self._ensure_engine().connect() as conn:
                if readonly:
                    conn = conn.execution_options(
                        workspace_readonly=True, **({} if self.sqlite else {"postgresql_readonly": True}),
                    )
                with conn.begin():
                    yield conn
        except (SQLAlchemyError, OSError):
            raise WorkspaceError(503, "workspace_unavailable", "Workspace storage is temporarily unavailable.") from None
        finally:
            if gated:
                self._write_gate.release()

    def close(self):
        if self._engine is not None:
            self._engine.dispose()

    def warm(self) -> None:
        """Initialize/verify schema before serving requests; persist no customer data."""
        try:
            self._ensure_engine()
        except WorkspaceError:
            raise
        except Exception:
            # Startup must not reveal a credential-bearing driver URL or SQL error.
            raise WorkspaceError(
                503, "workspace_unavailable", "Workspace storage initialization failed.",
            ) from None

    def prune_expired(self) -> int:
        """Explicit maintenance; never runs on the authenticated GET path."""
        with self._transaction() as conn:
            return conn.execute(delete(workspaces).where(workspaces.c.expires_at <= self.now())).rowcount

    def _owner(self, conn, digest):
        row = conn.execute(
            select(workspaces).where(workspaces.c.token_hash == digest).with_for_update()
        ).mappings().first()
        # Check the clock after lock acquisition, not before a potentially blocking wait.
        if row is None or row["expires_at"] <= self.now():
            raise unauthorized()
        return row

    @staticmethod
    def _snapshot():
        return select(
            workspaces.c.id.label("owner_id"), workspaces.c.expires_at,
            *[column.label("c_" + column.name) for column in customers.columns],
            *[column.label("p_" + column.name) for column in properties.columns],
        ).select_from(workspaces.join(customers).join(properties, (
            (properties.c.customer_id == customers.c.id)
            & (properties.c.workspace_id == customers.c.workspace_id)
        ))).order_by(customers.c.slot, properties.c.slot)

    @staticmethod
    def _serialize(rows):
        groups = {}
        for row in rows:
            cid = row["c_id"]
            if cid not in groups:
                groups[cid] = {
                    "id": cid, "label": f"Example household {row['c_slot']}",
                    "version": row["c_version"], "updated_at": iso_utc(row["c_updated_at"]),
                    **json.loads(row["c_state_json"]), "properties": [],
                }
            customer = groups[cid]
            state = json.loads(row["p_state_json"])
            customer["properties"].append({
                "id": row["p_id"], "customer_id": cid,
                "label": f"Example property {row['p_slot']}", "version": row["p_version"],
                "updated_at": iso_utc(row["p_updated_at"]),
                **state, "home": effective_home(state, customer),
            })
        if len(groups) != CUSTOMERS_PER_WORKSPACE:
            raise WorkspaceError(503, "workspace_unavailable", "Workspace storage is temporarily unavailable.")
        for customer in groups.values():
            customer["budget_summary"] = budget_summary(customer, customer["properties"])
            if len(customer["properties"]) == 1:
                # Compatibility is deliberately absent for multi-property owners.
                prop = customer["properties"][0]
                for key in ("home", "preferences", "selected_retrofits",
                            "review_status", "baseline_status", "events"):
                    customer[key] = deepcopy(prop[key])
        return {
            "id": rows[0]["owner_id"], "schema_version": 2, "mode": "fictional_demo",
            "expires_at": iso_utc(rows[0]["expires_at"]),
            "customers": list(groups.values()), "note": NOTE,
        }

    def _view(self, conn, owner):
        return self._serialize(conn.execute(self._snapshot().where(
            workspaces.c.id == owner["id"]
        )).mappings().all())

    def get(self, token: str) -> dict:
        digest = token_hash(token)
        with self._transaction(readonly=True) as conn:
            # ONE statement prevents a PostgreSQL READ COMMITTED owner/customer
            # split snapshot during concurrent deletion. No SELECT FOR UPDATE.
            rows = conn.execute(self._snapshot().where(
                workspaces.c.token_hash == digest
            )).mappings().all()
            # Always check after fetching, including any connection/lock wait.
            if not rows or rows[0]["expires_at"] <= self.now():
                raise unauthorized()
            return self._serialize(rows)

    def create(self, token: str, seeds: list[dict]) -> dict:
        digest = token_hash(token)
        if len(seeds) != CUSTOMERS_PER_WORKSPACE:
            raise ValueError("Exactly four fictional customer seeds are required.")
        encoded = [_state_json(seed) for seed in seeds]
        from greenhome.workspace_migration import validate_property
        for seed in seeds:
            validate_property(seed)
        with self._transaction() as conn:
            # The singleton row lock serializes quota checks across processes.
            row = conn.execute(select(control).where(control.c.id == 1).with_for_update()).mappings().one()
            now = self.now()
            day = iso_utc(now)[:10]
            daily_count = row["creations"] if row["creation_day"] == day else 0
            count = conn.execute(select(func.count()).select_from(workspaces)).scalar_one()
            # GC shares an already-required creation write transaction. This
            # throttle is an efficiency hint only; capacity always forces GC,
            # so even stale process-local hints cannot bypass the row bound.
            if count >= self.max_workspaces or time.monotonic() >= self._next_prune_at:
                conn.execute(delete(workspaces).where(workspaces.c.expires_at <= now))
                count = conn.execute(select(func.count()).select_from(workspaces)).scalar_one()
                self._next_prune_at = time.monotonic() + PRUNE_INTERVAL_SECONDS
            if count >= self.max_workspaces or daily_count >= self.max_creations_per_day:
                raise WorkspaceError(429, "workspace_limit", "The fictional workspace quota is full. Try again later.")
            owner = {"id": secrets.token_hex(16), "token_hash": digest,
                     "created_at": now, "expires_at": now + TTL_SECONDS}
            conn.execute(insert(workspaces).values(**owner))
            for i, (seed, value) in enumerate(zip(seeds, encoded), 1):
                cid = secrets.token_hex(16)
                conn.execute(insert(customers).values(
                    id=cid, workspace_id=owner["id"], slot=i, version=1,
                    state_json=_state_json(neutral_settings(seed)), updated_at=now,
                ))
                conn.execute(insert(properties).values(
                    id=secrets.token_hex(16), customer_id=cid, workspace_id=owner["id"],
                    slot=1, home_id=seed["home"]["property_id"], version=1,
                    state_json=value, updated_at=now,
                ))
            conn.execute(update(control).where(control.c.id == 1).values(
                creation_day=day, creations=daily_count + 1,
            ))
            return self._view(conn, owner)

    @staticmethod
    def _version(actual, submitted):
        if type(submitted) is not int or actual != submitted:
            raise WorkspaceError(409, "stale_version", "This customer or property changed. Refresh before saving again.")
        if submitted >= MAX_VERSION:
            raise WorkspaceError(409, "version_limit", "This record's update limit is reached.")

    def mutate(self, token: str, customer_id: str, version: int, change: Callable[[dict], dict]) -> dict:
        """Deprecated one-property adapter; never pick a first sibling silently."""
        return self._mutate(token, customer_id, version,
                            change=lambda state, settings: change(state), legacy=True)

    def mutate_property(self, token, customer_id, property_id, customer_version, version, change):
        return self._mutate(token, customer_id, customer_version,
                            property_id=property_id, version=version, change=change)

    def legacy_property(self, token, customer_id, version, change):
        return self._mutate(token, customer_id, version, change=change, legacy=True)

    def add_property(self, token, customer_id, customer_version, seed):
        return self._mutate(token, customer_id, customer_version, seed=seed)

    def settings(self, token, customer_id, version, change):
        return self._mutate(token, customer_id, version, settings_change=change)

    def _mutate(self, token, customer_id, customer_version, *, property_id=None,
                version=None, change=None, legacy=False, seed=None, settings_change=None):
        from greenhome.workspace_migration import validate_property, validate_settings
        digest = token_hash(token)
        if not ID_PATTERN.fullmatch(customer_id):
            raise WorkspaceError(404, "customer_not_found", "Fictional customer not found.")
        with self._transaction() as conn:
            owner = self._owner(conn, digest)
            scope = (customers.c.id == customer_id) & (customers.c.workspace_id == owner["id"])
            row = conn.execute(select(customers).where(scope).with_for_update()).mappings().first()
            if row is None:
                raise WorkspaceError(404, "customer_not_found", "Fictional customer not found.")
            children = conn.execute(select(properties).where(
                (properties.c.customer_id == customer_id) & (properties.c.workspace_id == owner["id"])
            ).order_by(properties.c.slot)).mappings().all()
            target = None
            if legacy:
                if len(children) != 1:
                    raise WorkspaceError(409, "property_required",
                                         "Choose a property before changing a multi-property customer.")
                target = children[0]
                version = target["version"]
            elif property_id is not None:
                target = next((child for child in children if child["id"] == property_id), None)
                if target is None:
                    raise WorkspaceError(404, "property_not_found", "Fictional property not found.")
            self._version(row["version"], customer_version)
            if target is not None:
                self._version(target["version"], version)
            settings = json.loads(row["state_json"])
            states = [json.loads(child["state_json"]) for child in children]
            now = self.now()
            if settings_change is not None:
                settings = settings_change(deepcopy(settings))
                validate_settings(settings)
            elif seed is not None:
                if len(children) >= MAX_PROPERTIES:
                    raise WorkspaceError(409, "property_limit", "A fictional customer can have at most eight properties.")
                state = deepcopy(seed)
                pid = secrets.token_hex(16)
                state["home"]["property_id"] = "PROP-" + pid
                validate_property(state)
                states.append(state)
                conn.execute(insert(properties).values(
                    id=pid, customer_id=customer_id, workspace_id=owner["id"],
                    slot=len(children) + 1, home_id=state["home"]["property_id"],
                    version=1, state_json=_state_json(state), updated_at=now,
                ))
            else:
                before = json.loads(target["state_json"])
                state = change(deepcopy(before), deepcopy(settings))
                encoded = _state_json(state)
                validate_property(state)
                now = self.now()  # Event recording can cross a second boundary.
                if state["home"]["property_id"] != target["home_id"]:
                    raise invalid("The fictional property reference cannot be changed.")
                if state["events"][:len(before["events"])] != before["events"]:
                    raise invalid("Existing completion history cannot be changed.")
                states = [state if child["id"] == target["id"] else old
                          for child, old in zip(children, states)]
                result = conn.execute(update(properties).where(
                    (properties.c.id == target["id"])
                    & (properties.c.customer_id == customer_id)
                    & (properties.c.workspace_id == owner["id"])
                    & (properties.c.version == version)
                ).values(version=version + 1, state_json=encoded, updated_at=now))
                if result.rowcount != 1:
                    raise WorkspaceError(409, "stale_version", "This property changed. Refresh before saving again.")
            # ALL paths (legacy, property save/completion, add and settings) share
            # this lock and allocation check. A failure rolls back every write.
            check_allocation(settings, states)
            # Keep ownership AND version in the actual UPDATE, not only a preceding read.
            result = conn.execute(update(customers).where(scope & (customers.c.version == customer_version)).values(
                version=customers.c.version + 1, state_json=_state_json(settings), updated_at=now,
            ))
            if result.rowcount != 1:
                raise WorkspaceError(409, "stale_version", "This customer changed. Refresh before saving again.")
            return self._view(conn, owner)

    def delete(self, token: str):
        digest = token_hash(token)
        with self._transaction() as conn:
            owner = self._owner(conn, digest)
            conn.execute(delete(workspaces).where(
                (workspaces.c.id == owner["id"]) & (workspaces.c.token_hash == digest)
            ))
