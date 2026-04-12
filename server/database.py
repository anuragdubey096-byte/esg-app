from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# SQLite stores data in a file named db.sqlite in the server folder.
BASE_DIR = Path(__file__).resolve().parent
SQLITE_DB_PATH = BASE_DIR / 'db.sqlite'
SQLALCHEMY_DATABASE_URL = f'sqlite:///{SQLITE_DB_PATH.as_posix()}'

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={'check_same_thread': False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
