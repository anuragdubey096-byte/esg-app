import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from env import load_local_env

load_local_env()

BASE_DIR = Path(__file__).resolve().parent
SQLITE_DB_PATH = BASE_DIR / 'db.sqlite'

SQLALCHEMY_DATABASE_URL = os.getenv('DATABASE_URL')
if not SQLALCHEMY_DATABASE_URL:
    if os.getenv('VERCEL') == '1':
        raise RuntimeError('DATABASE_URL is required when running on Vercel.')
    SQLALCHEMY_DATABASE_URL = f'sqlite:///{SQLITE_DB_PATH.as_posix()}'

IS_SQLITE = SQLALCHEMY_DATABASE_URL.startswith('sqlite:')

engine_kwargs = {'pool_pre_ping': True}
if IS_SQLITE:
    engine_kwargs['connect_args'] = {'check_same_thread': False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
