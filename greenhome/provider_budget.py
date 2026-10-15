"""Single-host persistent provider-attempt budget; no credentials or payloads."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sqlite3
import stat
import time
from typing import Callable

LOCK_TIMEOUT_SECONDS = 1.0


class BudgetExceeded(RuntimeError):
    """The UTC day's provider-attempt allowance has been exhausted."""


class BudgetUnavailable(RuntimeError):
    """Persistent accounting could not safely reserve an attempt."""


class ProviderBudget:
    """Commit one reservation before each real transport attempt.

    Instances share only the SQLite file: no live connection or in-memory quota
    is retained. All cooperating processes must use the same path and limit.
    """

    def __init__(self, path: Path, limit: int, clock: Callable[[], float] = time.time):
        if type(limit) is not int or not 1 <= limit <= 10_000:
            raise ValueError("Provider attempt limit must be an integer between 1 and 10000.")
        if not callable(clock):
            raise ValueError("Provider budget clock must be callable.")
        self.path = Path(path).absolute()
        self.limit = limit
        self.clock = clock

    def _prepare_storage(self) -> None:
        """Use a dedicated service-owned directory and a private regular file."""
        parent = self.path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise OSError("Unsafe budget directory.")
        os.chmod(parent, 0o700, follow_symlinks=False)
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
        descriptor = os.open(self.path, flags, 0o600)
        try:
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid()):
                raise OSError("Unsafe budget file.")
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)

    def _utc_day(self) -> str:
        stamp = self.clock()
        if type(stamp) not in (int, float) or not math.isfinite(stamp):
            raise ValueError("Invalid clock.")
        return datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()

    def consume(self) -> None:
        connection = None
        try:
            self._prepare_storage()
            connection = sqlite3.connect(
                str(self.path), timeout=LOCK_TIMEOUT_SECONDS, isolation_level=None
            )
            connection.execute("PRAGMA synchronous = FULL")
            # Reserving the write lock BEFORE reading the count serialises all
            # processes, including concurrent first-time database initialisation.
            connection.execute("BEGIN IMMEDIATE")
            day = self._utc_day()  # UTC boundary after any lock wait.
            connection.execute(
                "CREATE TABLE IF NOT EXISTS provider_attempts ("
                "utc_day TEXT PRIMARY KEY NOT NULL, "
                "attempts INTEGER NOT NULL CHECK("
                "typeof(attempts) = 'integer' AND attempts BETWEEN 0 AND 10000))"
            )
            columns = connection.execute("PRAGMA table_info(provider_attempts)").fetchall()
            if [(row[1], row[2]) for row in columns] != [
                ("utc_day", "TEXT"), ("attempts", "INTEGER")
            ]:
                raise sqlite3.DatabaseError("Unexpected budget schema.")
            rows = connection.execute(
                "SELECT attempts FROM provider_attempts WHERE utc_day = ?", (day,)
            ).fetchall()
            if len(rows) > 1:
                raise sqlite3.DatabaseError("Ambiguous budget count.")
            count = rows[0][0] if rows else 0
            if type(count) is not int or not 0 <= count <= 10_000:
                raise sqlite3.DatabaseError("Invalid budget count.")
            if count >= self.limit:
                raise BudgetExceeded("Daily provider attempt limit reached.")
            if rows:
                connection.execute(
                    "UPDATE provider_attempts SET attempts = attempts + 1 WHERE utc_day = ?", (day,)
                )
            else:
                connection.execute(
                    "INSERT INTO provider_attempts(utc_day, attempts) VALUES (?, 1)", (day,)
                )
            connection.execute("COMMIT")
            # There is deliberately no refund API: failed/abandoned provider
            # calls remain counted after this reservation commits.
        except BudgetExceeded:
            raise
        except Exception:
            # Never expose filesystem paths, SQL errors, injected clock text,
            # or exception details to a provider caller.
            raise BudgetUnavailable("Provider attempt budget is unavailable.") from None
        finally:
            if connection is not None:
                try:
                    try:
                        if connection.in_transaction:
                            connection.rollback()
                    finally:
                        connection.close()
                except Exception:
                    raise BudgetUnavailable("Provider attempt budget is unavailable.") from None
