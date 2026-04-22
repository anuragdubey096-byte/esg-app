from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from models import User, UserRole

DEFAULT_LOGIN_USERS_CSV = Path(__file__).resolve().parent / 'fixtures' / 'users.csv'
EXPECTED_LOGIN_USER_COLUMNS = {'name', 'email', 'password', 'role'}
DEFAULT_FALLBACK_USERS: list[tuple[str, str, str, UserRole]] = [
    ('Portfolio Contact', 'company@example.com', 'password123', UserRole.COMPANY),
    ('Manager Alice', 'manager@example.com', 'password123', UserRole.MANAGER),
    ('Admin Alias', 'admin@example.com', 'password123', UserRole.MANAGER),
    ('Investor Bob', 'investor@example.com', 'password123', UserRole.INVESTOR),
    ('Healthy Foods Contact', 'healthyfoods@example.com', 'password123', UserRole.COMPANY),
    ('Acme Target Contact', 'target@example.com', 'password123', UserRole.COMPANY),
]


def load_login_user_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        missing_columns = sorted(EXPECTED_LOGIN_USER_COLUMNS - set(reader.fieldnames or []))
        if missing_columns:
            raise ValueError(
                f'Login user fixture {csv_path} is missing required columns: {", ".join(missing_columns)}'
            )
        return [row for row in reader if any((value or '').strip() for value in row.values())]


def seed_login_users_from_csv(
    db,
    csv_path: Path = DEFAULT_LOGIN_USERS_CSV,
    *,
    fallback_users: Iterable[tuple[str, str, str, UserRole]] = DEFAULT_FALLBACK_USERS,
) -> None:
    rows = load_login_user_rows(csv_path)

    if rows:
        for row in rows:
            email = (row.get('email') or '').strip().lower()
            name = (row.get('name') or '').strip()
            password = (row.get('password') or 'password123').strip() or 'password123'
            role_value = (row.get('role') or '').strip().lower()
            if not email or not name or not role_value:
                continue

            try:
                role = UserRole(role_value)
            except ValueError:
                continue

            user = db.query(User).filter(User.email == email).first()
            if user:
                user.name = name
                user.password = password
                user.role = role
            else:
                db.add(User(name=name, email=email, password=password, role=role))
        db.commit()
        return

    for name, email, password, role in fallback_users:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            db.add(User(name=name, email=email, password=password, role=role))
    db.commit()
