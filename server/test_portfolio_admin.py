import csv
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app, get_authenticated_user, get_db
from models import Base, Company, Holding, Portfolio, Submission, User, UserRole


ROOT = Path(__file__).resolve().parents[1]
DEMO_CSV = ROOT / 'client' / 'public' / 'demo-portfolio.csv'
COMPANIES_CSV = ROOT / 'server' / 'fixtures' / 'companies.csv'


def build_test_context():
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()
    db.execute(text(
        'CREATE TABLE onboarding_states ('
        'id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, '
        'FOREIGN KEY(company_id) REFERENCES companies(id))'
    ))
    manager = User(name='Test Manager', email='manager-test@example.com', password='test', role=UserRole.MANAGER)
    owner = User(name='Portfolio Owner', email='owner-test@example.com', password='test', role=UserRole.COMPANY)
    db.add_all([manager, owner])
    db.flush()
    with COMPANIES_CSV.open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            db.add(Company(
                code=row['company_id'],
                name=row['company_name'],
                sector=row['sector'],
                geography=row['geography'],
                asset_class=row['asset_class'],
                current_status=row['current_status'],
                user_id=owner.id,
            ))
    db.commit()

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_authenticated_user] = lambda: manager
    return db, TestClient(app)


def close_test_context(db, client):
    client.close()
    app.dependency_overrides.clear()
    db.close()


def test_portfolio_csv_preview_commit_and_update():
    db, client = build_test_context()
    try:
        csv_bytes = DEMO_CSV.read_bytes()
        preview = client.post(
            '/admin/import/portfolio-csv',
            data={'mode': 'preview'},
            files={'file': ('demo-portfolio.csv', csv_bytes, 'text/csv')},
        )
        assert preview.status_code == 200
        assert preview.json()['summary']['ready_rows'] == 20
        assert preview.json()['summary']['blocked_rows'] == 0

        first_commit = client.post(
            '/admin/import/portfolio-csv',
            data={'mode': 'commit'},
            files={'file': ('demo-portfolio.csv', csv_bytes, 'text/csv')},
        )
        assert first_commit.status_code == 200
        assert first_commit.json()['summary']['portfolios_created'] == 1
        assert first_commit.json()['summary']['funds_created'] == 2
        assert first_commit.json()['summary']['holdings_created'] == 20
        assert db.query(Portfolio).count() == 1
        assert db.query(Holding).count() == 20

        second_commit = client.post(
            '/admin/import/portfolio-csv',
            data={'mode': 'commit'},
            files={'file': ('demo-portfolio.csv', csv_bytes, 'text/csv')},
        )
        assert second_commit.status_code == 200
        assert second_commit.json()['summary']['holdings_created'] == 0
        assert second_commit.json()['summary']['holdings_updated'] == 20
        assert db.query(Holding).count() == 20
    finally:
        close_test_context(db, client)


def test_empty_company_deletion_refuses_company_with_esg_data():
    db, client = build_test_context()
    try:
        owner = db.query(User).filter(User.email == 'owner-test@example.com').one()
        empty_company = Company(name='Empty QA Company', sector='Unassigned', user_id=owner.id)
        protected_company = Company(name='Protected Company', sector='Energy', user_id=owner.id)
        db.add_all([empty_company, protected_company])
        db.flush()
        db.execute(
            text('INSERT INTO onboarding_states (company_id) VALUES (:company_id)'),
            {'company_id': empty_company.id},
        )
        db.add(Submission(company_id=protected_company.id, esg_data='{}', status='submitted'))
        db.commit()

        check = client.get(f'/admin/companies/{empty_company.id}/deletion-check')
        assert check.status_code == 200
        assert check.json()['safe_to_delete'] is True
        assert check.json()['cleanup_dependencies']['onboarding_states'] == 1
        deleted = client.delete(
            f'/admin/companies/{empty_company.id}',
            params={'confirm_name': empty_company.name},
        )
        assert deleted.status_code == 200
        assert deleted.json()['cleanup_dependencies']['onboarding_states'] == 1
        assert db.query(Company).filter(Company.id == empty_company.id).first() is None

        refused = client.delete(
            f'/admin/companies/{protected_company.id}',
            params={'confirm_name': protected_company.name},
        )
        assert refused.status_code == 409
        assert refused.json()['detail']['dependencies']['submissions'] == 1
        assert db.query(Company).filter(Company.id == protected_company.id).first() is not None
    finally:
        close_test_context(db, client)
