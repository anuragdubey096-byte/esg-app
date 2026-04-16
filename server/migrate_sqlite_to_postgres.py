from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = BASE_DIR / 'db.sqlite'

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from env import load_local_env
from models import Base

load_local_env()


def build_source_engine(sqlite_path: Path):
    if not sqlite_path.exists():
        raise FileNotFoundError(f'Source SQLite database not found: {sqlite_path}')
    return create_engine(
        f'sqlite:///{sqlite_path.as_posix()}',
        connect_args={'check_same_thread': False},
    )


def build_target_engine(database_url: str):
    if not database_url:
        raise ValueError('Target DATABASE_URL is required.')
    return create_engine(database_url, pool_pre_ping=True)


def reset_target_schema(target_engine):
    Base.metadata.drop_all(bind=target_engine)
    Base.metadata.create_all(bind=target_engine)


def reset_postgres_sequence(connection, table_name: str):
    if connection.dialect.name != 'postgresql':
        return

    pk_seq = connection.execute(
        text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
        {'table_name': table_name},
    ).scalar_one_or_none()
    if not pk_seq:
        return

    max_id = connection.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{table_name}"')).scalar_one()
    if max_id and max_id > 0:
        connection.execute(text(f"SELECT setval('{pk_seq}', :max_id, true)"), {'max_id': max_id})


def migrate(sqlite_path: Path, database_url: str):
    source_engine = build_source_engine(sqlite_path)
    target_engine = build_target_engine(database_url)

    reset_target_schema(target_engine)

    copied_tables = []
    with source_engine.connect() as source_conn, target_engine.begin() as target_conn:
        for table in Base.metadata.sorted_tables:
            rows = source_conn.execute(table.select()).mappings().all()
            if not rows:
                continue

            target_conn.execute(table.insert(), [dict(row) for row in rows])
            reset_postgres_sequence(target_conn, table.name)
            copied_tables.append((table.name, len(rows)))

    return copied_tables


def main():
    parser = argparse.ArgumentParser(description='Copy data from local SQLite into Postgres.')
    parser.add_argument(
        '--source',
        default=str(DEFAULT_SQLITE_PATH),
        help='Path to the source SQLite database file. Defaults to server/db.sqlite.',
    )
    parser.add_argument(
        '--target',
        default=os.getenv('DATABASE_URL', ''),
        help='Postgres database URL to load into. Defaults to DATABASE_URL.',
    )
    args = parser.parse_args()

    copied_tables = migrate(Path(args.source), args.target)
    total_rows = sum(count for _, count in copied_tables)

    print(f'Migrated {total_rows} rows into Postgres.')
    for table_name, count in copied_tables:
        print(f'  {table_name}: {count}')


if __name__ == '__main__':
    main()
