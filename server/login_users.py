from __future__ import annotations

import csv
from pathlib import Path

from models import User, UserRole

DEFAULT_LOGIN_USERS_CSV = Path(__file__).resolve().parent / 'fixtures' / 'users.csv'
EXPECTED_LOGIN_USER_COLUMNS = {'name', 'email', 'password', 'role'}


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
) -> None:
    rows = load_login_user_rows(csv_path)

    if rows:
        normalized_rows: list[tuple[str, str, str, UserRole]] = []
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
            normalized_rows.append((name, email, password, role))

        if not normalized_rows:
            return

        emails = {email for _, email, _, _ in normalized_rows}
        existing_users = db.query(User).filter(User.email.in_(emails)).all()
        existing_by_email = {user.email: user for user in existing_users}

        changed = False
        for name, email, password, role in normalized_rows:
            user = existing_by_email.get(email)
            if user:
                if user.name != name:
                    user.name = name
                    changed = True
                if user.password != password:
                    user.password = password
                    changed = True
                if user.role != role:
                    user.role = role
                    changed = True
            else:
                db.add(User(name=name, email=email, password=password, role=role))
                changed = True
        if changed:
            db.commit()
        return
