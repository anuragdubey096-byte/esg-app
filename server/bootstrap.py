from __future__ import annotations

from pathlib import Path

from database import IS_SQLITE, SQLITE_DB_PATH, engine
from import_csv import get_default_data_dir, import_all
from models import Base


def _resolve_fixture_dir(data_dir: Path | str | None = None) -> Path:
    if data_dir is None:
        return get_default_data_dir().resolve()
    return Path(data_dir).resolve()


def seed_sample_data(db=None, data_dir: Path | str | None = None):
    """
    Backward-compatible startup seed entrypoint.
    Uses fixture CSVs only (no hardcoded sample rows).
    """
    _ = db  # kept for compatibility with existing callsites
    import_all(_resolve_fixture_dir(data_dir))


def reset_database(data_dir: Path | str | None = None):
    engine.dispose()
    if IS_SQLITE and SQLITE_DB_PATH.exists():
        try:
            SQLITE_DB_PATH.unlink()
        except PermissionError:
            pass

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    import_all(_resolve_fixture_dir(data_dir))


def clear_runtime_data():
    """
    Legacy helper retained for compatibility.
    Clears the database by re-importing fixture data.
    """
    import_all(_resolve_fixture_dir())
