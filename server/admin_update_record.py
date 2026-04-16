from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import inspect, text

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from env import load_local_env
from database import engine

load_local_env()


def _parse_value(raw: str):
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return raw

    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed)
    return parsed


def _quote(name: str) -> str:
    return f'"{name}"'


def list_tables() -> list[str]:
    inspector = inspect(engine)
    return sorted(inspector.get_table_names())


def list_columns(table_name: str) -> list[str]:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        raise ValueError(f'Unknown table: {table_name}')
    return [column['name'] for column in inspector.get_columns(table_name)]


def update_record(table_name: str, record_id: str, column_name: str, value: str, id_column: str = 'id') -> dict:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if table_name not in tables:
        raise ValueError(f'Unknown table: {table_name}')

    columns = {column['name'] for column in inspector.get_columns(table_name)}
    if id_column not in columns:
        raise ValueError(f'Unknown id column {id_column!r} on table {table_name!r}')
    if column_name not in columns:
        raise ValueError(f'Unknown column {column_name!r} on table {table_name!r}')

    typed_value = _parse_value(value)
    typed_id = _parse_value(record_id)

    update_sql = text(
        f'UPDATE {_quote(table_name)} '
        f'SET {_quote(column_name)} = :value '
        f'WHERE {_quote(id_column)} = :record_id'
    )
    select_sql = text(
        f'SELECT * FROM {_quote(table_name)} '
        f'WHERE {_quote(id_column)} = :record_id'
    )

    with engine.begin() as connection:
        result = connection.execute(update_sql, {'value': typed_value, 'record_id': typed_id})
        row = connection.execute(select_sql, {'record_id': typed_id}).mappings().first()

    return {
        'table': table_name,
        'record_id': record_id,
        'column': column_name,
        'rows_updated': result.rowcount or 0,
        'row': dict(row) if row else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Update one field in a Vercel production database row.')
    parser.add_argument('--table', help='Table name to update.')
    parser.add_argument('--id', dest='record_id', help='Primary key value of the row to update.')
    parser.add_argument('--column', help='Column to update.')
    parser.add_argument('--value', help='New value. JSON is accepted for arrays/objects.')
    parser.add_argument('--id-column', default='id', help='Primary key column name. Defaults to id.')
    parser.add_argument('--list-tables', action='store_true', help='Print the available table names.')
    parser.add_argument('--list-columns', help='Print columns for the given table.')
    args = parser.parse_args()

    if args.list_tables:
        for table_name in list_tables():
            print(table_name)
        return 0

    if args.list_columns:
        for column_name in list_columns(args.list_columns):
            print(column_name)
        return 0

    missing = [name for name in ('table', 'record_id', 'column', 'value') if getattr(args, name) is None]
    if missing:
        parser.error(f"Missing required arguments: {', '.join(missing)}")

    result = update_record(args.table, args.record_id, args.column, args.value, args.id_column)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
