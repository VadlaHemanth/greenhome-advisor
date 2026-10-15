"""Offline SQLite backup + schema upgrade; never resets an invalid database."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def backup_sqlite(source: Path, destination: Path) -> dict:
    """Use SQLite's snapshot API, including WAL content; don't copy an open file."""
    source, destination = Path(source).absolute(), Path(destination).absolute()
    info = source.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid()):
        raise ValueError("Source must be a service-owned regular SQLite file.")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = destination.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.geteuid():
        raise ValueError("Backup directory is not service-owned.")
    os.chmod(destination.parent, 0o700)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(source.as_uri()+"?mode=ro", uri=True, timeout=5) as original:
            if original.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Source SQLite integrity check failed.")
            with sqlite3.connect(destination, timeout=5) as copied:
                original.backup(copied)
                if copied.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("Backup SQLite integrity check failed.")
        os.chmod(destination, 0o600)
        return {
            "status": "verified",
            "bytes": destination.stat().st_size,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "contains_private_workspace_data": True,
            "restore_requires_stopped_workers": True,
        }
    except Exception:
        # This file was created exclusively by this invocation, never user data.
        destination.unlink(missing_ok=True)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", type=Path, default=ROOT/"state/workspaces.sqlite3")
    p.add_argument("--backup-dir", type=Path, default=ROOT/"state/backups")
    p.add_argument("--confirm-workers-stopped", action="store_true")
    args = p.parse_args()
    if not args.confirm_workers_stopped:
        raise SystemExit("Stop every app worker using this database, then pass --confirm-workers-stopped.")
    source = args.database.absolute()
    backup = args.backup_dir.absolute()/(
        "workspace-v1-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+".sqlite3"
    )
    try:
        record = backup_sqlite(source, backup)
    except Exception:
        raise SystemExit("Backup failed. No migration was attempted; private error details were not printed.") from None
    manifest = backup.with_suffix(".json")
    fd = os.open(manifest, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd,"w") as stream:
        json.dump(record,stream,indent=2)
    try:
        from greenhome.workspace_store import WorkspaceStore
        store = WorkspaceStore(f"sqlite:///{source}")
        try:
            store.warm()
        finally:
            store.close()
    except Exception:
        print("Verified backup saved:",backup)
        raise SystemExit("Schema upgrade failed. Keep workers stopped and inspect the retained backup; no reset was performed.") from None
    print("Schema verified/upgraded. Verified private backup:",backup)
    print("Do not commit, upload or include this backup in submission archives.")


if __name__=="__main__":
    main()
