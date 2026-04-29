import argparse
import csv
import json
import re
from pathlib import Path

from sqlalchemy import inspect
from database import SessionLocal, engine
from models import (
    Base,
    ActivityEvent,
    ActionPlan,
    CollectionCycle,
    Company,
    NarrativeSummary,
    NewsletterDispatchLog,
    ReminderLog,
    SubmissionCollaborationSession,
    SubmissionDataField,
    Submission,
    SubmissionUnlock,
    SupportingDocument,
    User,
    ValidationError,
    ReviewAction,
    ValidationFlag,
)
from login_users import seed_login_users_from_csv

EXPECTED_FILES = {
    'users': 'users.csv',
    'companies': 'companies.csv',
    'cycles': 'cycles.csv',
    'review_actions': 'review_actions.csv',
    'validation_flags': 'validation_flags.csv',
    'submissions_previous': 'esg_submissions_previous_year.csv',
    'submissions_current': 'esg_submissions_current_year.csv',
}

EXPECTED_COLUMNS = {
    'users': {'name', 'email', 'password', 'role'},
    'companies': {'company_id', 'company_name', 'asset_class', 'sector', 'geography', 'portfolio_contact_name', 'portfolio_contact_email', 'client_visible', 'current_status'},
    'cycles': {'cycle_year', 'submission_open_date', 'submission_deadline', 'extension_date', 'reminder_days_before_deadline', 'private_equity_template', 'real_estate_template', 'debt_template', 'activate_on_create', 'carry_forward_prefill', 'status'},
    'review_actions': {'company_id', 'reporting_year', 'review_status', 'reviewer_role', 'review_comment'},
    'validation_flags': {'company_id', 'reporting_year', 'flag_type', 'field_name', 'issue_description', 'severity'},
    'submissions_previous': {'company_id', 'reporting_year', 'scope_1_emissions', 'scope_2_location_based', 'scope_2_market_based', 'scope_3_emissions', 'total_ghg_emissions', 'reduction_target_percent', 'reduction_target_year', 'reduction_strategy_description', 'total_energy_consumption', 'renewable_energy_consumption', 'total_water_withdrawal', 'water_recycled_reused', 'total_waste_generated', 'waste_diverted_from_landfill', 'hazardous_waste_generated', 'air_quality_control_measures', 'nox_sox_emissions', 'whs_policy_in_place', 'whs_policy_document_reference', 'trifr', 'total_fatalities', 'total_lost_time_injuries', 'total_incidents_reported', 'total_employees_fte', 'employee_turnover_rate', 'female_representation_percent', 'female_leadership_representation_percent', 'community_investment_spend', 'esg_policy_in_place', 'esg_policy_document_reference', 'board_level_esg_oversight', 'esg_kpis_linked_to_remuneration', 'cybersecurity_policy_in_place', 'cybersecurity_policy_document_reference', 'cyber_incidents_in_reporting_period', 'anti_bribery_corruption_policy', 'confirmed_cases_of_corruption', 'total_board_members', 'independent_board_members_percent', 'female_board_members_percent', 'submission_notes'},
    'submissions_current': {'company_id', 'reporting_year', 'scope_1_emissions', 'scope_1_emissions_confidence', 'scope_2_location_based', 'scope_2_location_based_confidence', 'scope_2_market_based', 'scope_2_market_based_confidence', 'scope_3_emissions', 'scope_3_emissions_confidence', 'total_ghg_emissions', 'total_ghg_emissions_confidence', 'reduction_target_percent', 'reduction_target_percent_confidence', 'reduction_target_year', 'reduction_target_year_confidence', 'reduction_strategy_description', 'total_energy_consumption', 'total_energy_consumption_confidence', 'renewable_energy_consumption', 'renewable_energy_consumption_confidence', 'total_water_withdrawal', 'total_water_withdrawal_confidence', 'water_recycled_reused', 'water_recycled_reused_confidence', 'total_waste_generated', 'total_waste_generated_confidence', 'waste_diverted_from_landfill', 'waste_diverted_from_landfill_confidence', 'hazardous_waste_generated', 'hazardous_waste_generated_confidence', 'air_quality_control_measures', 'air_quality_control_measures_confidence', 'nox_sox_emissions', 'nox_sox_emissions_confidence', 'whs_policy_in_place', 'whs_policy_in_place_confidence', 'whs_policy_document_reference', 'trifr', 'trifr_confidence', 'total_fatalities', 'total_fatalities_confidence', 'total_lost_time_injuries', 'total_lost_time_injuries_confidence', 'total_incidents_reported', 'total_incidents_reported_confidence', 'total_employees_fte', 'total_employees_fte_confidence', 'employee_turnover_rate', 'employee_turnover_rate_confidence', 'female_representation_percent', 'female_representation_percent_confidence', 'female_leadership_representation_percent', 'female_leadership_representation_percent_confidence', 'community_investment_spend', 'community_investment_spend_confidence', 'esg_policy_in_place', 'esg_policy_in_place_confidence', 'esg_policy_document_reference', 'board_level_esg_oversight', 'board_level_esg_oversight_confidence', 'esg_kpis_linked_to_remuneration', 'esg_kpis_linked_to_remuneration_confidence', 'cybersecurity_policy_in_place', 'cybersecurity_policy_in_place_confidence', 'cybersecurity_policy_document_reference', 'cyber_incidents_in_reporting_period', 'cyber_incidents_in_reporting_period_confidence', 'anti_bribery_corruption_policy', 'anti_bribery_corruption_policy_confidence', 'confirmed_cases_of_corruption', 'confirmed_cases_of_corruption_confidence', 'total_board_members', 'total_board_members_confidence', 'independent_board_members_percent', 'independent_board_members_percent_confidence', 'female_board_members_percent', 'female_board_members_percent_confidence', 'submission_notes'},
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


def validate_csv_schema(csv_path: Path, required_columns: set[str]) -> None:
    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
    missing = sorted(required_columns - fieldnames)
    if missing:
        raise ValueError(f'CSV fixture {csv_path} is missing required columns: {", ".join(missing)}')


def validate_fixture_schema(data_dir: Path):
    for key, filename in EXPECTED_FILES.items():
        validate_csv_schema(data_dir / filename, EXPECTED_COLUMNS[key])


def validate_fixture_consistency(data_dir: Path):
    companies = load_csv_rows(data_dir / EXPECTED_FILES['companies'])
    company_ids = [row['company_id'].strip() for row in companies if row.get('company_id')]
    unique_company_ids = set(company_ids)
    if len(company_ids) != len(unique_company_ids):
        duplicates = sorted({company_id for company_id in company_ids if company_ids.count(company_id) > 1})
        raise ValueError(f'Duplicate company IDs found in {data_dir / EXPECTED_FILES["companies"]}: {", ".join(duplicates)}')

    referenced_files = ('review_actions', 'validation_flags', 'submissions_previous', 'submissions_current')
    for key in referenced_files:
        rows = load_csv_rows(data_dir / EXPECTED_FILES[key])
        unknown_ids = sorted(
            {
                (row.get('company_id') or '').strip()
                for row in rows
                if (row.get('company_id') or '').strip() and (row.get('company_id') or '').strip() not in unique_company_ids
            }
        )
        if unknown_ids:
            raise ValueError(
                f'CSV fixture {data_dir / EXPECTED_FILES[key]} references unknown company IDs: {", ".join(unknown_ids)}'
            )


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
    # Delete in dependency-safe order to keep fixture reload deterministic.
    db.query(SubmissionCollaborationSession).delete()
    db.query(ActivityEvent).delete()
    db.query(NewsletterDispatchLog).delete()
    db.query(SupportingDocument).delete()
    db.query(ValidationError).delete()
    db.query(SubmissionDataField).delete()
    db.query(SubmissionUnlock).delete()
    db.query(ReminderLog).delete()
    db.query(NarrativeSummary).delete()
    db.query(ReviewAction).delete()
    db.query(ValidationFlag).delete()
    db.query(ActionPlan).delete()
    db.query(Submission).delete()
    db.query(CollectionCycle).delete()
    db.query(Company).delete()
    db.query(User).delete()
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
    validate_fixture_schema(data_dir)
    validate_fixture_consistency(data_dir)
    Base.metadata.create_all(bind=engine)
    ensure_schema_ready()

    db = SessionLocal()
    try:
        clear_database(db)
        seed_login_users_from_csv(db, data_dir / EXPECTED_FILES['users'])
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
        help='Directory containing users.csv, cycles.csv, review_actions.csv, validation_flags.csv, companies.csv, esg_submissions_previous_year.csv, and esg_submissions_current_year.csv. Defaults to server/fixtures when present.',
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    import_all(data_dir)
    print(f'CSV import complete from {data_dir}')


if __name__ == '__main__':
    main()
