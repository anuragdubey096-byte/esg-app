from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from sqlalchemy import inspect

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from env import load_local_env
from database import SessionLocal, engine
from models import User

load_local_env()

DEFAULT_USERS_CSV = BASE_DIR / 'fixtures' / 'users.csv'


def load_users(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f'User CSV not found: {csv_path}')

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, str]] = []
        for row in reader:
            if any((value or '').strip() for value in row.values()):
                rows.append(row)
        return rows


def ensure_users_table() -> None:
    inspector = inspect(engine)
    if 'users' not in inspector.get_table_names():
        raise RuntimeError('The users table does not exist yet. Run the app migrations/reset first.')


def seed_users(csv_path: Path) -> tuple[int, int]:
    ensure_users_table()
    rows = load_users(csv_path)

    inserted = 0
    updated = 0
    db = SessionLocal()
    try:
        for row in rows:
            email = (row.get('email') or '').strip().lower()
            name = (row.get('name') or '').strip()
            password = (row.get('password') or 'password123').strip() or 'password123'
            role = (row.get('role') or '').strip().lower()
            if not email or not name or not role:
                continue

            user = db.query(User).filter(User.email == email).first()
            if user:
                user.name = name
                user.password = password
                user.role = role
                updated += 1
            else:
                db.add(User(name=name, email=email, password=password, role=role))
                inserted += 1
        db.commit()
    finally:
        db.close()

    return inserted, updated


def main() -> int:
    parser = argparse.ArgumentParser(description='Seed login users from a CSV into the configured database.')
    parser.add_argument(
        'csv_path',
        nargs='?',
        default=str(DEFAULT_USERS_CSV),
        help='Path to users.csv. Defaults to server/fixtures/users.csv.',
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_path).resolve()
    inserted, updated = seed_users(csv_path)
    print(f'Seeded login users from {csv_path}')
    print(f'Inserted: {inserted}')
    print(f'Updated: {updated}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
