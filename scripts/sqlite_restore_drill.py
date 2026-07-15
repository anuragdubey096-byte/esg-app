"""Run a non-production SQLite backup/restore drill and report its duration."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path


def main() -> int:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="greenledger-restore-") as directory:
        root = Path(directory)
        live = root / "live.sqlite"
        backup = root / "backup.sqlite"
        marker = "greenledger-restore-marker"

        with closing(sqlite3.connect(live)) as connection:
            connection.execute("CREATE TABLE restore_probe (id INTEGER PRIMARY KEY, marker TEXT NOT NULL)")
            connection.execute("INSERT INTO restore_probe (marker) VALUES (?)", (marker,))
            connection.commit()
            with closing(sqlite3.connect(backup)) as destination:
                connection.backup(destination)

        backup_size = backup.stat().st_size
        live.unlink()
        shutil.copy2(backup, live)

        with closing(sqlite3.connect(live)) as restored:
            integrity = restored.execute("PRAGMA integrity_check").fetchone()[0]
            restored_marker = restored.execute("SELECT marker FROM restore_probe WHERE id = 1").fetchone()[0]

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        passed = integrity == "ok" and restored_marker == marker
        print(json.dumps({
            "status": "passed" if passed else "failed",
            "database": "sqlite-test-only",
            "elapsed_ms": elapsed_ms,
            "backup_bytes": backup_size,
            "integrity": integrity,
            "marker_verified": restored_marker == marker,
        }))
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
