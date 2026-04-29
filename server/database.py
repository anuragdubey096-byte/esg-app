import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parent

def _load_env_local() -> None:
    """Load simple KEY=VALUE pairs from server/.env.local if present."""
    env_file = BASE_DIR / '.env.local'
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _database_url() -> str:
    _load_env_local()
    configured = os.getenv('DATABASE_URL', '').strip().strip('"').strip("'")
    if configured:
        # SQLAlchemy works best with explicit drivers.
        if configured.startswith('postgresql://'):
            configured = configured.replace('postgresql://', 'postgresql+psycopg2://', 1)
        elif configured.startswith('postgres://'):
            configured = configured.replace('postgres://', 'postgresql+psycopg2://', 1)

        try:
            make_url(configured)
            return configured
        except Exception:
            # Fall through to SQLite fallback when DATABASE_URL is malformed.
            pass

    # Fallback for local development. Vercel's source filesystem is read-only,
    # so use /tmp for ephemeral SQLite in serverless runtime.
    if os.getenv('VERCEL'):
        sqlite_db_path = Path('/tmp/db.sqlite')
    else:
        sqlite_db_path = BASE_DIR / 'db.sqlite'
    return f'sqlite:///{sqlite_db_path.as_posix()}'


SQLALCHEMY_DATABASE_URL = _database_url()
engine_kwargs = {}
if SQLALCHEMY_DATABASE_URL.startswith('sqlite:///'):
    engine_kwargs['connect_args'] = {'check_same_thread': False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
