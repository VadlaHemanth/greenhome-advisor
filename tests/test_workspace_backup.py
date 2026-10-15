from pathlib import Path
import sqlite3
import stat

import pytest
from scripts.migrate_workspaces import backup_sqlite


def test_snapshot_contains_committed_wal_records_and_is_private(tmp_path):
    source=tmp_path/"original.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE records (value TEXT)")
        connection.execute("INSERT INTO records VALUES ('fictional')")
        connection.commit()
        target=tmp_path/"private"/"snapshot.sqlite3"
        result=backup_sqlite(source,target)
        with sqlite3.connect(target) as copied:
            assert copied.execute("SELECT value FROM records").fetchall()==[("fictional",)]
        assert result["status"]=="verified"
        assert stat.S_IMODE(target.stat().st_mode)==0o600
        assert stat.S_IMODE(target.parent.stat().st_mode)==0o700
        connection.execute("INSERT INTO records VALUES ('later')")
        connection.commit()
        with sqlite3.connect(target) as copied:
            assert copied.execute("SELECT count(*) FROM records").fetchone()==(1,)


def test_backup_cannot_overwrite_an_existing_file(tmp_path):
    source=tmp_path/"source.sqlite3"
    with sqlite3.connect(source) as c:
        c.execute("CREATE TABLE example (id INTEGER)")
    target=tmp_path/"backup.sqlite3";target.write_text("preserve me")
    with pytest.raises(FileExistsError):
        backup_sqlite(source,target)
    assert target.read_text()=="preserve me"


def test_invalid_source_does_not_reset_or_leave_false_backup(tmp_path):
    source=tmp_path/"corrupt.sqlite3";source.write_bytes(b"not a SQLite database")
    target=tmp_path/"new"/"backup.sqlite3"
    with pytest.raises(sqlite3.DatabaseError):
        backup_sqlite(source,target)
    assert source.read_bytes()==b"not a SQLite database"
    assert not target.exists()


def test_symlink_source_is_rejected(tmp_path):
    original=tmp_path/"original";original.write_text("data")
    source=tmp_path/"symlink";source.symlink_to(original)
    with pytest.raises(ValueError):
        backup_sqlite(source,tmp_path/"new"/"backup")
