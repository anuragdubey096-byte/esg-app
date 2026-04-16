import argparse
import csv
import json
import re
from pathlib import Path

from sqlalchemy import inspect
from database import SessionLocal, engine
from models import (
    Base,
    CollectionCycle,
    Company,
    Submission,
    User,
    ReviewAction,
    ValidationFlag,
)

EXPECTED_FILES = {
    'companies': 'companies.csv',
    'cycles': 'cycles.csv',
    'review_actions': 'review_actions.csv',
    'validation_flags': 'validation_flags.csv',
    'submissions_previous': 'esg_submissions_previous_year.csv',
    'submissions_current': 'esg_submissions_current_year.csv',
}


def get_default_data_dir() -> Path:
    fixtures_dir = Path(__file__).resolve().parent / 'fixtures'
    if fixtures_dir.exists():
        return fixtures_dir
    return Path.cwd()


def load_csv_rows(csv_path: Path):
    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if any((value or '').strip() for value in row.values())]


def to_int(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def to_bool(value):
    return str(value).strip().lower() in {'true', '1', 'yes', 'y'}


def parse_list(value):
    if not value:
        return []
    return [item.strip() for item in re.split(r'[;,]', value) if item.strip()]


def ensure_required_files(data_dir: Path):
    missing = [filename for filename in EXPECTED_FILES.values() if not (data_dir / filename).exists()]
    if missing:
        raise FileNotFoundError(f"Missing CSV files in {data_dir}: {', '.join(missing)}")


def clear_database(db):
    db.query(ReviewAction).delete()
    db.query(ValidationFlag).delete()
    db.query(Submission).delete()
    db.query(CollectionCycle).delete()
    db.query(Company).delete()
    db.query(User).delete()
    db.commit()


def import_default_personas(db):
    personas = [
        {'name': 'System Manager', 'email': 'manager@example.com', 'role': 'manager'},
        {'name': 'Global Investor', 'email': 'investor@example.com', 'role': 'investor'}
    ]
    for p in personas:
        user = db.query(User).filter(User.email == p['email']).first()
        if not user:
            db.add(User(
                name=p['name'],
                email=p['email'],
                password='password123',
                role=p['role']
            ))
    db.commit()


def import_companies(db, data_dir: Path):
    rows = load_csv_rows(data_dir / EXPECTED_FILES['companies'])
    for row in rows:
        company_code = row['company_id'].strip()
        contact_email = row['portfolio_contact_email'].strip()
        contact_name = row['portfolio_contact_name'].strip() or row['company_name'].strip()

        company_user = db.query(User).filter(User.email == contact_email).first()
        if not company_user:
            company_user = User(
                name=contact_name,
                email=contact_email,
                password='password123',
                role='company',
            )
            db.add(company_user)
            db.commit()
            db.refresh(company_user)

        existing_company = db.query(Company).filter(Company.code == company_code).first()
        if existing_company:
            existing_company.name = row['company_name'].strip()
            existing_company.sector = row['sector'].strip()
            existing_company.user_id = company_user.id
            existing_company.asset_class = row['asset_class'].strip()
            existing_company.geography = row['geography'].strip()
            existing_company.client_visible = str(to_bool(row['client_visible']))
            existing_company.current_status = row['current_status'].strip()
        else:
            db.add(
                Company(
                    code=company_code,
                    name=row['company_name'].strip(),
                    sector=row['sector'].strip(),
                    user_id=company_user.id,
                    asset_class=row['asset_class'].strip(),
                    geography=row['geography'].strip(),
                    client_visible=str(to_bool(row['client_visible'])),
                    current_status=row['current_status'].strip(),
                )
            )
    db.commit()


def import_cycles(db, data_dir: Path):
    rows = load_csv_rows(data_dir / EXPECTED_FILES['cycles'])
    for row in rows:
        reminder_schedule = json.dumps([int(value) for value in parse_list(row['reminder_days_before_deadline']) if value.isdigit()])
        template_config = json.dumps(
            {
                'private_equity': row['private_equity_template'].strip(),
                'real_estate': row['real_estate_template'].strip(),
                'debt': row['debt_template'].strip(),
            }
        )
        prefill_summary = json.dumps(
            {
                'carry_forward_prefill': to_bool(row['carry_forward_prefill']),
                'prefill_company_count': 0,
            }
        )
        db.add(
            CollectionCycle(
                cycle_year=to_int(row['cycle_year']),
                submission_open_date=row['submission_open_date'].strip(),
                submission_deadline=row['submission_deadline'].strip(),
                extension_date=row['extension_date'].strip() or None,
                reminder_schedule=reminder_schedule,
                template_config=template_config,
                prefill_summary=prefill_summary,
                status=row['status'].strip(),
                created_by_user_id=None,
            )
        )
    db.commit()


def import_review_actions(db, data_dir: Path):
    rows = load_csv_rows(data_dir / EXPECTED_FILES['review_actions'])
    for row in rows:
        company = db.query(Company).filter(Company.code == row['company_id'].strip()).first()
        if not company:
            continue
        db.add(
            ReviewAction(
                company_id=company.id,
                reporting_year=to_int(row['reporting_year']),
                review_status=row['review_status'].strip(),
                reviewer_role=row['reviewer_role'].strip(),
                review_comment=row['review_comment'].strip(),
            )
        )
    db.commit()


def import_validation_flags(db, data_dir: Path):
    rows = load_csv_rows(data_dir / EXPECTED_FILES['validation_flags'])
    for row in rows:
        company = db.query(Company).filter(Company.code == row['company_id'].strip()).first()
        if not company:
            continue
        db.add(
            ValidationFlag(
                company_id=company.id,
                reporting_year=to_int(row['reporting_year']),
                flag_type=row['flag_type'].strip(),
                field_name=row['field_name'].strip(),
                issue_description=row['issue_description'].strip(),
                severity=row['severity'].strip(),
            )
        )
    db.commit()


def import_submissions(db, data_dir: Path):
    for key in ('submissions_previous', 'submissions_current'):
        rows = load_csv_rows(data_dir / EXPECTED_FILES[key])
        for row in rows:
            company = db.query(Company).filter(Company.code == row['company_id'].strip()).first()
            if not company:
                continue
            payload = {k: v for k, v in row.items() if v is not None}
            db.add(
                Submission(
                    company_id=company.id,
                    esg_data=json.dumps(payload),
                    status='submitted',
                )
            )
    db.commit()


def ensure_schema_ready():
    inspector = inspect(engine)
    columns = [column['name'] for column in inspector.get_columns('companies')]
    if 'code' not in columns:
        raise RuntimeError(
            'The existing database schema is outdated. Run python server/reset_db.py before importing the new synthetic CSV files.'
        )


def import_all(data_dir: Path):
    ensure_required_files(data_dir)
    Base.metadata.create_all(bind=engine)
    ensure_schema_ready()

    db = SessionLocal()
    try:
        clear_database(db)
        import_default_personas(db)
        import_companies(db, data_dir)
        import_cycles(db, data_dir)
        import_review_actions(db, data_dir)
        import_validation_flags(db, data_dir)
        import_submissions(db, data_dir)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description='Import ESG app CSV data into the configured database')
    parser.add_argument(
        'data_dir',
        nargs='?',
        default=str(get_default_data_dir()),
        help='Directory containing cycles.csv, review_actions.csv, validation_flags.csv, companies.csv, esg_submissions_previous_year.csv, and esg_submissions_current_year.csv. Defaults to server/fixtures when present.',
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    import_all(data_dir)
    print(f'CSV import complete from {data_dir}')


if __name__ == '__main__':
    main()
