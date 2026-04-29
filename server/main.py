import csv
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from bootstrap import seed_sample_data
from database import SessionLocal, engine
from models import (
    Base,
    User,
    UserRole,
    Company,
    Submission,
    CollectionCycle,
    ActionPlan,
    ReviewAction,
    ValidationFlag,
    SubmissionUnlock,
    ReminderLog,
)
from schemas import (
    ActionPlanCreateRequest,
    ActionPlanInfo,
    CompanyCreateRequest,
    CompanyCreateResponse,
    CompanyDetail,
    CycleCreateRequest,
    CycleInfo,
    CycleStatusUpdateRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GHGCalculatorRequest,
    GHGCalculatorResponse,
    ReviewSubmissionRequest,
    InvestorSummary,
    InvestorDashboardResponse,
    LoginRequest,
    SSOLoginRequest,
    SubmissionCreateRequest,
    SubmissionInfo,
    SubmissionStatusUpdateRequest,
    SubmissionUnlockRequest,
    SubmissionUnlockInfo,
    ReminderRequest,
    ReminderInfo,
    ReportExportResponse,
    ManagerDashboardResponse,
    UserResponse,
)
from new_esg_module import router as new_esg_router
try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency at runtime
    OpenAI = None

BASE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = BASE_DIR / 'exports'
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_REPORT_TYPES = {'edci', 'sfdr'}
ALLOWED_CYCLE_STATUSES = {'draft', 'active', 'closed'}
ALLOWED_REVIEW_STATUSES = {'submitted', 'under review', 'approved', 'rejected', 'resubmission requested'}
OPENAI_DEFAULT_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
ALLOWED_REVIEW_TRANSITIONS = {
    'submitted': {'under review'},
    'under review': {'approved', 'rejected', 'resubmission requested'},
    'resubmission requested': {'submitted'},
}

app = FastAPI(title='ESG Data App')
app.include_router(new_esg_router, prefix="/api/v2")
app.mount('/exports', StaticFiles(directory=EXPORT_DIR), name='exports')


def normalize_role(role: Any) -> str:
    if role is None:
        return ''
    value = role.value if hasattr(role, 'value') else str(role)
    normalized = value.strip().lower()
    if normalized in {'admin', 'manager'}:
        return 'manager'
    if normalized in {'company', 'investor'}:
        return normalized
    if normalized == 'managerrole':
        return 'manager'
    if normalized == 'companyrole':
        return 'company'
    return normalized


def to_user_role_enum(role: str) -> UserRole:
    normalized = normalize_role(role)
    if normalized == 'company':
        return UserRole.COMPANY
    if normalized == 'investor':
        return UserRole.INVESTOR
    return UserRole.MANAGER


def serialize_user(user: User):
    return {
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'role': normalize_role(user.role),
    }


def parse_json_or_default(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        parsed = json.loads(value)
        return parsed if parsed is not None else default
    except (TypeError, ValueError):
        return default


def normalize_cycle_status(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in ALLOWED_CYCLE_STATUSES:
        return normalized
    return 'draft'


def serialize_cycle(cycle: CollectionCycle):
    template_config = parse_json_or_default(cycle.template_config, {})
    prefill_summary = parse_json_or_default(cycle.prefill_summary, {})
    reminder_schedule = parse_json_or_default(cycle.reminder_schedule, [])
    return CycleInfo(
        id=cycle.id,
        cycle_year=cycle.cycle_year,
        submission_open_date=cycle.submission_open_date,
        submission_deadline=cycle.submission_deadline,
        extension_date=cycle.extension_date,
        reminder_days_before_deadline=reminder_schedule if isinstance(reminder_schedule, list) else [],
        private_equity_template=template_config.get('private_equity', ''),
        real_estate_template=template_config.get('real_estate', ''),
        debt_template=template_config.get('debt', ''),
        status=normalize_cycle_status(cycle.status),
        carry_forward_prefill=bool(prefill_summary.get('carry_forward_prefill', True)),
        prefill_company_count=int(prefill_summary.get('prefill_company_count', 0)),
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# Create database tables automatically when the app starts.
Base.metadata.create_all(bind=engine)

# A helper to get a database session inside path operations.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# RBAC Dependencies
# ==========================================
def get_user_role(x_user_role: str = Header(None)):
    return normalize_role(x_user_role)


def get_user_email(x_user_email: str | None = Header(default=None)) -> str | None:
    return x_user_email.strip().lower() if x_user_email else None

def require_manager(role: str = Depends(get_user_role)):
    if role != 'manager':
        raise HTTPException(status_code=403, detail='Access restricted to ESG Managers')

def block_investors(role: str = Depends(get_user_role)):
    if role == 'investor':
        raise HTTPException(status_code=403, detail='Investors are blocked from individual company-level data')


def find_request_user(db: Session, email: str | None) -> User | None:
    if email:
        return db.query(User).filter(User.email == email).first()
    return None


def _provision_company_for_user(db: Session, user: User) -> Company:
    existing_company = db.query(Company).filter(Company.user_id == user.id).first()
    if existing_company:
        return existing_company

    base_name = (user.name or '').strip() or (user.email.split('@')[0] if user.email else f'company-{user.id}')
    company_name = f'{base_name} Company'
    generated_code = f'AUTO-{user.id}'

    company = Company(
        code=generated_code,
        name=company_name,
        sector='Unassigned',
        user_id=user.id,
        asset_class='Unassigned',
        geography='Unassigned',
        client_visible='TRUE',
        current_status='not started',
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def table_has_column(db: Session, table_name: str, column_name: str) -> bool:
    pragma_rows = db.execute(text(f'PRAGMA table_info({table_name})')).mappings().all()
    return any(row.get('name') == column_name for row in pragma_rows)


def ensure_submission_cycle_column(db: Session):
    if table_has_column(db, 'submissions', 'cycle_id'):
        return
    db.execute(text('ALTER TABLE submissions ADD COLUMN cycle_id INTEGER'))
    db.commit()


def get_active_cycle(db: Session) -> CollectionCycle | None:
    return (
        db.query(CollectionCycle)
        .filter(CollectionCycle.status == 'active')
        .order_by(CollectionCycle.cycle_year.desc())
        .first()
    )


def get_latest_cycle(db: Session) -> CollectionCycle | None:
    return db.query(CollectionCycle).order_by(CollectionCycle.id.desc()).first()


def get_or_create_reserved_cycle(db: Session) -> CollectionCycle:
    reserved = db.query(CollectionCycle).filter(CollectionCycle.cycle_year == 0).first()
    if reserved:
        if normalize_cycle_status(reserved.status) != 'closed':
            reserved.status = 'closed'
            db.commit()
            db.refresh(reserved)
        return reserved

    reserved = CollectionCycle(
        cycle_year=0,
        submission_open_date='1970-01-01',
        submission_deadline='1970-01-01',
        extension_date=None,
        reminder_schedule=json.dumps([]),
        template_config=json.dumps({'private_equity': '', 'real_estate': '', 'debt': ''}),
        prefill_summary=json.dumps({'carry_forward_prefill': False, 'prefill_company_count': 0}),
        status='closed',
        created_by_user_id=None,
    )
    db.add(reserved)
    db.commit()
    db.refresh(reserved)
    return reserved


def migrate_legacy_user_roles(db: Session):
    rows = db.execute(text('SELECT id, role FROM users')).mappings().all()
    for row in rows:
        normalized = normalize_role(row.get('role'))
        enum_name = to_user_role_enum(normalized).name
        if str(row.get('role')) != enum_name:
            db.execute(
                text('UPDATE users SET role = :role WHERE id = :user_id'),
                {'role': enum_name, 'user_id': row['id']},
            )
    db.commit()


def fix_cycle_statuses_and_active_conflicts(db: Session):
    cycles = db.query(CollectionCycle).order_by(CollectionCycle.cycle_year.desc()).all()
    active_cycles: list[CollectionCycle] = []
    changed = False

    for cycle in cycles:
        normalized = normalize_cycle_status(cycle.status)
        if cycle.status != normalized:
            cycle.status = normalized
            changed = True
        if normalized == 'active':
            active_cycles.append(cycle)

    if len(active_cycles) > 1:
        keeper = active_cycles[0]
        for cycle in active_cycles[1:]:
            if cycle.id != keeper.id:
                cycle.status = 'draft'
                changed = True

    if changed:
        db.commit()


def ensure_submission_cycle_backfill(db: Session):
    fallback_cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)
    orphan_submissions = db.query(Submission).filter(Submission.cycle_id.is_(None)).all()
    if orphan_submissions:
        for submission in orphan_submissions:
            submission.cycle_id = fallback_cycle.id
        db.commit()

    valid_cycle_ids = {cycle.id for cycle in db.query(CollectionCycle).all()}
    changed = False
    for submission in db.query(Submission).filter(Submission.cycle_id.is_not(None)).all():
        if submission.cycle_id not in valid_cycle_ids:
            submission.cycle_id = fallback_cycle.id
            changed = True
    if changed:
        db.commit()


def deactivate_expired_unlocks(db: Session):
    now = datetime.utcnow()
    unlocks = (
        db.query(SubmissionUnlock)
        .filter(SubmissionUnlock.active.is_(True), SubmissionUnlock.expires_at <= now)
        .all()
    )
    if not unlocks:
        return
    for unlock in unlocks:
        unlock.active = False
    db.commit()


def resolve_submission_cycle(db: Session) -> CollectionCycle:
    return get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)


def has_active_unlock(db: Session, submission_id: int, company_id: int, cycle_id: int) -> bool:
    deactivate_expired_unlocks(db)
    now = datetime.utcnow()
    unlock = (
        db.query(SubmissionUnlock)
        .filter(
            SubmissionUnlock.submission_id == submission_id,
            SubmissionUnlock.company_id == company_id,
            SubmissionUnlock.cycle_id == cycle_id,
            SubmissionUnlock.active.is_(True),
            SubmissionUnlock.expires_at > now,
        )
        .order_by(SubmissionUnlock.id.desc())
        .first()
    )
    return unlock is not None


def normalize_submission_status(value: Any) -> str:
    normalized = str(value or '').strip().lower()
    if not normalized:
        return 'not started'
    return normalized


def enforce_transition(current_status: str, next_status: str):
    current = normalize_submission_status(current_status)
    target = normalize_submission_status(next_status)
    if current == target:
        return
    allowed_next = ALLOWED_REVIEW_TRANSITIONS.get(current, set())
    if target not in allowed_next:
        raise HTTPException(status_code=422, detail=f'Invalid status transition: {current} -> {target}')

@app.on_event('startup')
def startup_event():
    db = SessionLocal()
    try:
        ensure_submission_cycle_column(db)
        Base.metadata.create_all(bind=engine)
        seed_sample_data(db)
        migrate_legacy_user_roles(db)
        fix_cycle_statuses_and_active_conflicts(db)
        ensure_submission_cycle_backfill(db)
        deactivate_expired_unlocks(db)
    finally:
        db.close()

@app.post('/login', response_model=UserResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    normalized_email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if not user or user.password != request.password:
        raise HTTPException(status_code=401, detail='Invalid email or password')
    return serialize_user(user)


@app.post('/auth/forgot-password', response_model=ForgotPasswordResponse)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Deliberately return a generic message to avoid revealing account existence.
    _ = db.query(User).filter(User.email == request.email).first()
    return ForgotPasswordResponse(
        message='If an account with that email exists, password reset instructions have been sent.'
    )


@app.post('/auth/sso/{provider}', response_model=UserResponse)
def sso_login(provider: str, payload: SSOLoginRequest | None = None, db: Session = Depends(get_db)):
    normalized_provider = provider.strip().lower()
    allowed_providers = {'google', 'microsoft'}
    if normalized_provider not in allowed_providers:
        raise HTTPException(status_code=400, detail='Unsupported SSO provider')

    email_hint = (payload.email_hint if payload else None) or ''
    provider_default_email = 'manager@example.com' if normalized_provider == 'google' else 'investor@example.com'
    target_email = email_hint.strip().lower() or provider_default_email

    user = db.query(User).filter(User.email == target_email).first()
    if not user:
        # Fallback to the provider default user if hint email does not exist.
        user = db.query(User).filter(User.email == provider_default_email).first()

    if not user:
        # Create a bootstrap user if seed data is unavailable.
        user = User(
            name='SSO User',
            email=provider_default_email,
            password='password123',
            role=UserRole.MANAGER if normalized_provider == 'google' else UserRole.INVESTOR,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return serialize_user(user)


@app.get('/users', response_model=List[UserResponse], dependencies=[Depends(require_manager)])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [serialize_user(user) for user in users]


@app.post('/companies', response_model=CompanyCreateResponse, dependencies=[Depends(require_manager)])
def create_company(payload: CompanyCreateRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.contact_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail='A user with this contact email already exists')

    portfolio_user = User(
        name=payload.contact_name,
        email=payload.contact_email,
        password=payload.temporary_password,
        role=UserRole.COMPANY,
    )
    db.add(portfolio_user)
    db.commit()
    db.refresh(portfolio_user)

    company = Company(
        name=payload.name,
        sector=payload.sector,
        user_id=portfolio_user.id,
        current_status=payload.current_status,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    return CompanyCreateResponse(
        id=company.id,
        name=company.name,
        sector=company.sector,
        portfolio_user_email=portfolio_user.email,
        portfolio_user_password=payload.temporary_password,
    )


@app.post('/cycles', response_model=CycleInfo, dependencies=[Depends(require_manager)])
def create_cycle(payload: CycleCreateRequest, db: Session = Depends(get_db)):
    existing_cycle = db.query(CollectionCycle).filter(CollectionCycle.cycle_year == payload.cycle_year).first()
    if existing_cycle:
        raise HTTPException(status_code=400, detail='A cycle for this year already exists')

    latest_submissions = 0
    if payload.carry_forward_prefill:
        for company in db.query(Company).all():
            if company.submissions:
                latest_submissions += 1

    if payload.activate_on_create:
        active_cycles = db.query(CollectionCycle).filter(CollectionCycle.status == 'active').all()
        for active_cycle in active_cycles:
            active_cycle.status = 'draft'

    cycle = CollectionCycle(
        cycle_year=payload.cycle_year,
        submission_open_date=payload.submission_open_date,
        submission_deadline=payload.submission_deadline,
        extension_date=payload.extension_date,
        reminder_schedule=json.dumps(payload.reminder_days_before_deadline),
        template_config=json.dumps({
            'private_equity': payload.private_equity_template,
            'real_estate': payload.real_estate_template,
            'debt': payload.debt_template,
        }),
        prefill_summary=json.dumps({
            'carry_forward_prefill': payload.carry_forward_prefill,
            'prefill_company_count': latest_submissions,
        }),
        status='active' if payload.activate_on_create else 'draft',
    )
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    return serialize_cycle(cycle)


@app.get('/cycles', response_model=List[CycleInfo], dependencies=[Depends(require_manager)])
def list_cycles(db: Session = Depends(get_db)):
    cycles = db.query(CollectionCycle).order_by(CollectionCycle.cycle_year.desc()).all()
    return [serialize_cycle(cycle) for cycle in cycles]

@app.patch('/cycles/{cycle_id}/status', response_model=CycleInfo, dependencies=[Depends(require_manager)])
def update_cycle_status(cycle_id: int, payload: CycleStatusUpdateRequest, db: Session = Depends(get_db)):
    cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail='Cycle not found')

    next_status = normalize_cycle_status(payload.status)
    if next_status == 'active':
        active_cycles = db.query(CollectionCycle).filter(CollectionCycle.status == 'active').all()
        for active_cycle in active_cycles:
            if active_cycle.id != cycle.id:
                active_cycle.status = 'draft'

    cycle.status = next_status
    db.commit()
    db.refresh(cycle)
    return serialize_cycle(cycle)


@app.post('/company/{company_id}/onboarding/complete', dependencies=[Depends(require_manager)])
def complete_onboarding(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    company.current_status = 'active'
    db.commit()
    return {"message": "Onboarding complete. Company is now active in the portfolio."}

@app.post('/company/{company_id}/submissions', response_model=SubmissionInfo)
def add_submission(company_id: int, submission: SubmissionCreateRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    target_cycle = resolve_submission_cycle(db)
    if not target_cycle:
        raise HTTPException(status_code=400, detail='No collection cycle is configured')

    latest_for_cycle = (
        db.query(Submission)
        .filter(Submission.company_id == company_id, Submission.cycle_id == target_cycle.id)
        .order_by(Submission.id.desc())
        .first()
    )

    if normalize_cycle_status(target_cycle.status) == 'closed':
        if not latest_for_cycle:
            raise HTTPException(status_code=423, detail='This cycle is closed and no unlock is available')
        if not has_active_unlock(db, latest_for_cycle.id, company_id, target_cycle.id):
            raise HTTPException(status_code=423, detail='This cycle is closed. Request a manager unlock.')

    if latest_for_cycle and normalize_submission_status(latest_for_cycle.status) == 'resubmission requested':
        enforce_transition(latest_for_cycle.status, 'submitted')
        latest_for_cycle.esg_data = json.dumps(submission.model_dump())
        latest_for_cycle.status = 'submitted'
        db.commit()
        db.refresh(latest_for_cycle)
        return latest_for_cycle

    submission_record = Submission(
        company_id=company_id,
        cycle_id=target_cycle.id,
        esg_data=json.dumps(submission.model_dump()),
        status='submitted',
    )
    db.add(submission_record)
    db.commit()
    db.refresh(submission_record)
    return submission_record

@app.get('/dashboard/company/{user_id}', response_model=List[CompanyDetail], dependencies=[Depends(block_investors)])
def company_dashboard(
    user_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    companies = db.query(Company).filter(Company.user_id == user_id).all()
    if companies or role != 'company':
        return companies

    request_user = find_request_user(db, email)
    if request_user and normalize_role(request_user.role) == 'company':
        companies = db.query(Company).filter(Company.user_id == request_user.id).all()
        if companies:
            return companies
        provisioned_company = _provision_company_for_user(db, request_user)
        return [provisioned_company]

    return companies

@app.patch('/submissions/{submission_id}/status', response_model=SubmissionInfo, dependencies=[Depends(require_manager)])
def update_submission_status(
    submission_id: int,
    payload: SubmissionStatusUpdateRequest,
    db: Session = Depends(get_db)
):
    next_status = normalize_submission_status(payload.status)
    if next_status not in ALLOWED_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail='Invalid submission status')

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    enforce_transition(submission.status, next_status)
    submission.status = next_status
    db.commit()
    db.refresh(submission)
    return submission

@app.post('/company/{company_id}/action-plans', response_model=ActionPlanInfo)
def create_action_plan(company_id: int, payload: ActionPlanCreateRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    plan = ActionPlan(
        company_id=company.id,
        initiative_name=payload.initiative_name,
        target_completion_date=payload.target_completion_date,
        assigned_owner=payload.assigned_owner,
        status='planned'
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

@app.post('/calculator/ghg', response_model=GHGCalculatorResponse)
def calculate_ghg(payload: GHGCalculatorRequest):
    scope_1 = payload.fuel_liters * 0.00268
    scope_2 = payload.electricity_kwh * 0.0005
    return GHGCalculatorResponse(
        scope_1_tco2e=round(scope_1, 4),
        scope_2_tco2e=round(scope_2, 4),
        total_tco2e=round(scope_1 + scope_2, 4)
    )

@app.post('/company/{company_id}/upload-evidence')
def upload_evidence(company_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    return {"filename": file.filename, "message": "Evidence uploaded successfully"}

@app.post('/submissions/{submission_id}/review', dependencies=[Depends(require_manager)])
def review_submission(submission_id: int, payload: ReviewSubmissionRequest, db: Session = Depends(get_db)):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    next_status = normalize_submission_status(payload.review_status)
    if next_status not in ALLOWED_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail='Invalid review status')

    enforce_transition(submission.status, next_status)
    submission.status = next_status
    reporting_year = submission.cycle.cycle_year if submission.cycle else datetime.utcnow().year
    review_action = ReviewAction(
        company_id=submission.company_id,
        reporting_year=reporting_year,
        review_status=next_status,
        reviewer_role=payload.reviewer_role or 'manager',
        review_comment=payload.review_comment,
    )
    db.add(review_action)
    db.commit()
    db.refresh(submission)
    return {"message": "Review logged successfully", "status": submission.status}

@app.post('/submissions/{submission_id}/validate', dependencies=[Depends(require_manager)])
def validate_submission(submission_id: int, db: Session = Depends(get_db)):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    
    data = json.loads(submission.esg_data)
    flags_created = 0
    reporting_year = submission.cycle.cycle_year if submission.cycle else datetime.utcnow().year
    
    # Define required fields for validation
    required_fields = [
        'scope_1_emissions', 'scope_2_location_based', 'scope_3_emissions',
        'total_ghg_emissions', 'total_energy_consumption', 'renewable_energy_consumption',
        'total_water_withdrawal', 'total_waste_generated', 'total_employees_fte',
        'employee_turnover_rate', 'female_representation_percent'
    ]
    
    # Check for missing required fields
    for field in required_fields:
        if field not in data or data[field] is None:
            db.add(ValidationFlag(
                company_id=submission.company_id, reporting_year=reporting_year,
                flag_type='Missing Data', field_name=field,
                issue_description=f'Required field "{field}" is missing or null.',
                severity='High'
            ))
            flags_created += 1
    
    # Data quality checks - only if fields exist
    if all(field in data and data[field] is not None for field in ['scope_1_emissions', 'scope_2_location_based', 'scope_2_market_based', 'scope_3_emissions', 'total_ghg_emissions']):
        scope_1 = float(data['scope_1_emissions'])
        scope_2_loc = float(data['scope_2_location_based'])
        scope_2_mkt = float(data['scope_2_market_based'])
        scope_3 = float(data['scope_3_emissions'])
        total_ghg = float(data['total_ghg_emissions'])
        
        # Check for negative emissions
        if scope_1 < 0 or scope_2_loc < 0 or scope_3 < 0:
            db.add(ValidationFlag(
                company_id=submission.company_id, reporting_year=reporting_year,
                flag_type='Data Quality', field_name='emissions',
                issue_description='Negative emissions detected. Scopes 1, 2, and 3 should be non-negative.',
                severity='High'
            ))
            flags_created += 1
        
        # Check GHG total consistency (allow 5% tolerance for rounding)
        calculated_total = scope_1 + scope_2_loc + scope_3
        if calculated_total > 0 and abs(total_ghg - calculated_total) / calculated_total > 0.05:
            db.add(ValidationFlag(
                company_id=submission.company_id, reporting_year=reporting_year,
                flag_type='Data Quality', field_name='total_ghg_emissions',
                issue_description=f'Total GHG emissions ({total_ghg}) does not match sum of scopes ({calculated_total:.1f}). Variance: {abs(total_ghg - calculated_total) / calculated_total:.1%}',
                severity='Medium'
            ))
            flags_created += 1
    
    # Check energy consumption consistency
    if 'total_energy_consumption' in data and 'renewable_energy_consumption' in data:
        total_energy = data['total_energy_consumption']
        renewable_energy = data['renewable_energy_consumption']
        if total_energy is not None and renewable_energy is not None:
            if renewable_energy > total_energy:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name='renewable_energy_consumption',
                    issue_description='Renewable energy consumption exceeds total energy consumption.',
                    severity='High'
                ))
                flags_created += 1
    
    # Check water recycling consistency
    if 'total_water_withdrawal' in data and 'water_recycled_reused' in data:
        total_water = data['total_water_withdrawal']
        recycled_water = data['water_recycled_reused']
        if total_water is not None and recycled_water is not None:
            if recycled_water > total_water:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name='water_recycled_reused',
                    issue_description='Water recycled/reused exceeds total water withdrawal.',
                    severity='High'
                ))
                flags_created += 1
    
    # Check waste diversion consistency
    if 'total_waste_generated' in data and 'waste_diverted_from_landfill' in data:
        total_waste = data['total_waste_generated']
        diverted_waste = data['waste_diverted_from_landfill']
        if total_waste is not None and diverted_waste is not None:
            if diverted_waste > total_waste:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name='waste_diverted_from_landfill',
                    issue_description='Waste diverted from landfill exceeds total waste generated.',
                    severity='High'
                ))
                flags_created += 1
    
    # Check percentage fields are in valid range (0-100)
    percentage_fields = [
        'employee_turnover_rate', 'female_representation_percent',
        'female_leadership_representation_percent', 'independent_board_members_percent',
        'female_board_members_percent'
    ]
    for field in percentage_fields:
        if field in data and data[field] is not None:
            value = float(data[field])
            if value < 0 or value > 100:
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name=field,
                    issue_description=f'Percentage field "{field}" must be between 0-100. Current value: {value}',
                    severity='High'
                ))
                flags_created += 1
    
    # Check female leadership vs overall female representation (proportionality)
    if 'female_representation_percent' in data and 'female_leadership_representation_percent' in data:
        female_overall = data['female_representation_percent']
        female_leadership = data['female_leadership_representation_percent']
        if female_overall is not None and female_leadership is not None:
            if female_leadership > female_overall + 5:  # Allow 5% tolerance
                db.add(ValidationFlag(
                    company_id=submission.company_id, reporting_year=reporting_year,
                    flag_type='Data Quality', field_name='female_leadership_representation_percent',
                    issue_description=f'Female leadership representation ({female_leadership}%) exceeds overall female representation ({female_overall}%) by more than 5%.',
                    severity='Medium'
                ))
                flags_created += 1
    
    # Year-over-year variance check
    prev_submission = db.query(Submission).filter(
        Submission.company_id == submission.company_id,
        Submission.id != submission.id
    ).order_by(Submission.id.desc()).first()
    
    if prev_submission:
        prev_data = json.loads(prev_submission.esg_data)
        for field in ['total_ghg_emissions', 'total_energy_consumption', 'total_water_withdrawal']:
            curr_val, prev_val = data.get(field), prev_data.get(field)
            if curr_val is not None and prev_val is not None and prev_val > 0:
                variance = (curr_val - prev_val) / prev_val
                if abs(variance) > 0.30:
                    db.add(ValidationFlag(
                        company_id=submission.company_id, reporting_year=reporting_year,
                        flag_type='Variance Alert', field_name=field,
                        issue_description=f'YoY variance for {field} is {variance:.1%}, exceeding +/-30% threshold.',
                        severity='High'
                    ))
                    flags_created += 1

    db.commit()
    return {"message": f"Validation complete. {flags_created} anomalies flagged.", "flagged": flags_created > 0}

def parse_date_string(date_string: str | None):
    if not date_string:
        return None
    try:
        return datetime.strptime(date_string, '%Y-%m-%d').date()
    except ValueError:
        return None


def get_days_to_deadline(deadline: str | None):
    parsed = parse_date_string(deadline)
    if not parsed:
        return None
    return (parsed - datetime.now().date()).days


def normalize_manager_bucket(status: str | None) -> str:
    normalized = normalize_submission_status(status)
    mapping = {
        'not started': 'Not Started',
        'in progress': 'In Progress',
        'submitted': 'Submitted',
        'under review': 'Under Review',
        'approved': 'Approved',
        'rejected': 'Resubmission Requested',
        'resubmission requested': 'Resubmission Requested',
        'pre-acquisition': 'Not Started',
        'active': 'In Progress',
    }
    return mapping.get(normalized, 'Not Started')


def get_progress_from_bucket(bucket: str) -> int:
    return {
        'Not Started': 8,
        'In Progress': 45,
        'Submitted': 72,
        'Under Review': 84,
        'Approved': 100,
        'Resubmission Requested': 58,
    }.get(bucket, 8)


def build_manager_summary(db: Session, companies: List[Company]) -> dict:
    cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)
    cycle_deadline = cycle.submission_deadline if cycle else None
    cycle_days_remaining = get_days_to_deadline(cycle_deadline)
    status_breakdown = {
        'Not Started': 0,
        'In Progress': 0,
        'Submitted': 0,
        'Under Review': 0,
        'Approved': 0,
        'Resubmission Requested': 0,
    }
    upcoming_deadlines = []
    progress_rows = []

    for company in companies:
        submissions = company.submissions or []
        cycle_submissions = [item for item in submissions if cycle and item.cycle_id == cycle.id]
        latest_submission = (cycle_submissions or submissions)[-1] if (cycle_submissions or submissions) else None
        status_source = latest_submission.status if latest_submission else company.current_status
        bucket = normalize_manager_bucket(status_source)
        status_breakdown[bucket] += 1
        completion = get_progress_from_bucket(bucket)
        days_remaining = cycle_days_remaining

        progress_rows.append({
            'company_id': company.id,
            'company_name': company.name,
            'asset_class': company.asset_class,
            'sector': company.sector,
            'status': bucket,
            'completion_percent': completion,
            'last_activity': f'Submission #{latest_submission.id}' if latest_submission else 'No submission yet',
            'deadline': cycle_deadline,
            'actions': ['Validate', 'Approve', 'Request Resubmission', 'Reject', 'Unlock', 'Send Reminder'],
        })

        if days_remaining is not None and 0 <= days_remaining <= 7 and bucket not in {'Submitted', 'Under Review', 'Approved'}:
            upcoming_deadlines.append({
                'company_id': company.id,
                'company_name': company.name,
                'asset_class': company.asset_class,
                'sector': company.sector,
                'status': bucket,
                'completion_percent': completion,
                'deadline': cycle_deadline,
                'days_remaining': days_remaining,
            })

    upcoming_deadlines.sort(key=lambda row: row['days_remaining'] if row['days_remaining'] is not None else 99999)
    return {
        'status_breakdown': status_breakdown,
        'cycle_banner': {
            'active_cycle_year': cycle.cycle_year if cycle else None,
            'submission_open_date': cycle.submission_open_date if cycle else None,
            'submission_deadline': cycle_deadline,
            'days_remaining': cycle_days_remaining,
            'cycle_status': normalize_cycle_status(cycle.status) if cycle else 'closed',
        },
        'upcoming_deadlines': upcoming_deadlines,
        'progress_rows': progress_rows,
    }


def slugify(value: str) -> str:
    sanitized = re.sub(r'[^a-zA-Z0-9]+', '_', str(value or '').strip()).strip('_')
    return sanitized.lower() or 'all'


def build_report_rows(db: Session, portfolio: str, period: str):
    active_cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)
    companies_query = db.query(Company)
    normalized_portfolio = (portfolio or 'all').strip()
    if normalized_portfolio and normalized_portfolio.lower() not in {'all', 'all portfolio companies'}:
        companies_query = companies_query.filter(Company.name == normalized_portfolio)
    companies = companies_query.order_by(Company.name.asc()).all()

    rows = []
    for company in companies:
        cycle_submissions = [item for item in company.submissions if item.cycle_id == active_cycle.id]
        latest_submission = (cycle_submissions or company.submissions)[-1] if (cycle_submissions or company.submissions) else None
        bucket = normalize_manager_bucket(latest_submission.status if latest_submission else company.current_status)
        payload = parse_submission(latest_submission)
        rows.append({
            'company_name': company.name,
            'asset_class': company.asset_class or '',
            'sector': company.sector,
            'status': bucket,
            'completion_percent': get_progress_from_bucket(bucket),
            'total_ghg_emissions': round(safe_number(payload.get('total_ghg_emissions')), 2),
            'female_representation_percent': round(safe_number(payload.get('female_representation_percent')), 2),
            'esg_score': round(clamp(50 + safe_number(payload.get('reduction_target_percent')) * 0.25), 2),
            'period': period,
            'cycle_year': active_cycle.cycle_year,
        })
    return rows, active_cycle


def write_csv_export(file_path: Path, rows: List[dict]):
    headers = [
        'company_name',
        'asset_class',
        'sector',
        'status',
        'completion_percent',
        'total_ghg_emissions',
        'female_representation_percent',
        'esg_score',
        'period',
        'cycle_year',
    ]
    with file_path.open('w', newline='', encoding='utf-8') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def escape_pdf_text(text_value: str) -> str:
    return str(text_value).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def build_simple_pdf(lines: List[str]) -> bytes:
    if not lines:
        lines = ['No data']
    content_lines = ['BT', '/F1 12 Tf', '50 780 Td', '16 TL']
    for index, line in enumerate(lines):
        escaped = escape_pdf_text(line)
        if index == 0:
            content_lines.append(f'({escaped}) Tj')
        else:
            content_lines.append(f'T* ({escaped}) Tj')
    content_lines.append('ET')
    stream = '\n'.join(content_lines).encode('utf-8')
    objects = [
        b'1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n',
        b'2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n',
        b'3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n',
        b'4 0 obj << /Length ' + str(len(stream)).encode('ascii') + b' >> stream\n' + stream + b'\nendstream endobj\n',
        b'5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n',
    ]
    output = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for obj in objects:
        offsets.append(len(output))
        output.extend(obj)
    xref_offset = len(output)
    output.extend(f'xref\n0 {len(objects) + 1}\n'.encode('ascii'))
    output.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        output.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    output.extend((f'trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n').encode('ascii'))
    return bytes(output)


def write_pdf_export(file_path: Path, report_type: str, period: str, cycle: CollectionCycle, rows: List[dict]):
    status_counts = {}
    for row in rows:
        status_counts[row['status']] = status_counts.get(row['status'], 0) + 1

    lines = [
        f'{report_type.upper()} Report Export',
        f'Generated At: {datetime.now(timezone.utc).isoformat()}',
        f'Period: {period}',
        f'Cycle Year: {cycle.cycle_year}',
        f'Total Rows: {len(rows)}',
        f'Status Distribution: {json.dumps(status_counts)}',
        '--- Company Snapshot ---',
    ]
    for row in rows[:25]:
        lines.append(f"{row['company_name']} | {row['sector']} | {row['status']} | ESG {row['esg_score']}")
    file_path.write_bytes(build_simple_pdf(lines))


@app.post('/submissions/{submission_id}/unlock', response_model=SubmissionUnlockInfo, dependencies=[Depends(require_manager)])
def unlock_submission(
    submission_id: int,
    payload: SubmissionUnlockRequest,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    cycle = submission.cycle or resolve_submission_cycle(db)
    if submission.cycle_id is None:
        submission.cycle_id = cycle.id
        db.commit()
        db.refresh(submission)

    db.query(SubmissionUnlock).filter(
        SubmissionUnlock.submission_id == submission.id,
        SubmissionUnlock.company_id == submission.company_id,
        SubmissionUnlock.cycle_id == cycle.id,
        SubmissionUnlock.active.is_(True),
    ).update({'active': False}, synchronize_session=False)

    manager_user = find_request_user(db, user_email)
    expires_at = datetime.utcnow() + timedelta(hours=payload.expiry_hours)
    unlock = SubmissionUnlock(
        submission_id=submission.id,
        company_id=submission.company_id,
        cycle_id=cycle.id,
        unlocked_by_user_id=manager_user.id if manager_user else None,
        reason=payload.reason,
        expires_at=expires_at,
        active=True,
    )
    db.add(unlock)
    db.commit()
    db.refresh(unlock)
    return SubmissionUnlockInfo(
        id=unlock.id,
        submission_id=unlock.submission_id,
        company_id=unlock.company_id,
        cycle_id=unlock.cycle_id,
        unlocked_by_user_id=unlock.unlocked_by_user_id,
        reason=unlock.reason,
        expires_at=unlock.expires_at.isoformat(),
        created_at=unlock.created_at.isoformat(),
        active=unlock.active,
    )


@app.post('/companies/{company_id}/reminders', response_model=ReminderInfo, dependencies=[Depends(require_manager)])
def send_reminder(
    company_id: int,
    payload: ReminderRequest,
    db: Session = Depends(get_db),
    user_email: str | None = Depends(get_user_email),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    if payload.cycle_id is not None:
        cycle = db.query(CollectionCycle).filter(CollectionCycle.id == payload.cycle_id).first()
        if not cycle:
            raise HTTPException(status_code=404, detail='Cycle not found')
    else:
        cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)

    manager_user = find_request_user(db, user_email)
    reminder = ReminderLog(
        company_id=company.id,
        cycle_id=cycle.id,
        sent_by_user_id=manager_user.id if manager_user else None,
        channel=(payload.channel or 'email').strip().lower() or 'email',
        message=payload.message.strip(),
        delivery_status='logged',
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return ReminderInfo(
        id=reminder.id,
        company_id=reminder.company_id,
        cycle_id=reminder.cycle_id,
        sent_by_user_id=reminder.sent_by_user_id,
        channel=reminder.channel,
        message=reminder.message,
        created_at=reminder.created_at.isoformat(),
        delivery_status=reminder.delivery_status,
    )


@app.get('/reports/{report_type}')
def generate_report(report_type: str, db: Session = Depends(get_db)):
    report_name = report_type.strip().lower()
    if report_name not in ALLOWED_REPORT_TYPES:
        raise HTTPException(status_code=400, detail='Invalid report type')

    active_cycle = get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)
    return {
        'report_type': report_name.upper(),
        'available_formats': ['csv', 'pdf'],
        'active_cycle_year': active_cycle.cycle_year,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }


@app.get('/reports/{report_type}/export', response_model=ReportExportResponse, dependencies=[Depends(require_manager)])
def export_report(
    report_type: str,
    format: str = Query(default='csv'),
    period: str = Query(default='Current Cycle'),
    portfolio: str = Query(default='All Portfolio Companies'),
    db: Session = Depends(get_db),
):
    report_name = report_type.strip().lower()
    if report_name not in ALLOWED_REPORT_TYPES:
        raise HTTPException(status_code=400, detail='Invalid report type')

    export_format = format.strip().lower()
    if export_format not in {'csv', 'pdf'}:
        raise HTTPException(status_code=400, detail='format must be csv or pdf')

    rows, cycle = build_report_rows(db, portfolio=portfolio, period=period)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    file_name = f'{report_name}_{slugify(period)}_{slugify(portfolio)}_{timestamp}.{export_format}'
    file_path = EXPORT_DIR / file_name

    if export_format == 'csv':
        write_csv_export(file_path, rows)
        content_type = 'text/csv'
    else:
        write_pdf_export(file_path, report_name, period, cycle, rows)
        content_type = 'application/pdf'

    return ReportExportResponse(
        report_type=report_name.upper(),
        format=export_format,
        period=period,
        portfolio=portfolio,
        generated_at=datetime.now(timezone.utc).isoformat(),
        file_name=file_name,
        file_path=str(file_path),
        download_url=f'/exports/{file_name}',
        content_type=content_type,
        rows_exported=len(rows),
    )


@app.get('/dashboard/manager', response_model=ManagerDashboardResponse, dependencies=[Depends(require_manager)])
def manager_dashboard(db: Session = Depends(get_db)):
    companies = db.query(Company).order_by(Company.name.asc()).all()
    summary = build_manager_summary(db, companies)
    return {
        'companies': companies,
        'summary': summary,
    }

def safe_number(value, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def normalize_status_label(status: str | None) -> str:
    normalized = str(status or '').strip().lower()
    mapping = {
        'not started': 'Not Started',
        'in progress': 'In Progress',
        'submitted': 'Submitted',
        'under review': 'Submitted',
        'approved': 'Approved',
        'rejected': 'Rejected',
        'resubmission requested': 'In Progress',
        'pre-acquisition': 'Not Started',
        'active': 'In Progress',
    }
    return mapping.get(normalized, 'Not Started')


def parse_submission(submission: Submission | None) -> dict:
    if not submission:
        return {}
    try:
        payload = json.loads(submission.esg_data)
        return payload if isinstance(payload, dict) else {}
    except (TypeError, ValueError):
        return {}


def build_emissions_trend(total_emissions: float) -> list[dict]:
    now = datetime.utcnow()
    periods = []
    for offset in range(5, -1, -1):
        month_value = datetime(now.year, max(1, now.month - offset), 1)
        periods.append(month_value.strftime('%b'))

    trend = []
    for index, period in enumerate(periods):
        factor = 1 + ((len(periods) - index - 1) * 0.04)
        trend.append({
            'period': period,
            'total_emissions': round(total_emissions * factor, 2),
        })
    return trend


def build_investor_analytics(db: Session) -> dict:
    companies = db.query(Company).all()

    status_counts = {
        'Not Started': 0,
        'In Progress': 0,
        'Submitted': 0,
        'Approved': 0,
        'Rejected': 0,
    }

    required_fields = [
        'scope_1_emissions',
        'scope_2_location_based',
        'scope_3_emissions',
        'total_ghg_emissions',
        'total_energy_consumption',
        'total_water_withdrawal',
        'total_waste_generated',
        'female_representation_percent',
        'trifr',
        'independent_board_members_percent',
    ]

    company_scores = []
    sector_scores = {}
    total_submissions = 0
    reporting_companies = 0
    total_scope_1 = 0.0
    total_scope_2 = 0.0
    total_scope_3 = 0.0
    total_energy = 0.0
    total_water = 0.0
    total_waste = 0.0
    total_female_rep = 0.0
    total_trifr = 0.0
    governance_yes = 0.0
    governance_checks = 0.0
    score_e_total = 0.0
    score_s_total = 0.0
    score_g_total = 0.0
    score_total = 0.0
    completeness_total = 0.0
    confidence_total = 0.0
    accuracy_total = 0.0
    high_variance_count = 0

    for company in companies:
        submissions = company.submissions or []
        total_submissions += len(submissions)
        latest = submissions[-1] if submissions else None
        previous = submissions[-2] if len(submissions) > 1 else None

        status = normalize_status_label((latest.status if latest else company.current_status))
        status_counts[status] = status_counts.get(status, 0) + 1
        payload = parse_submission(latest)
        previous_payload = parse_submission(previous)
        if not payload:
            continue

        reporting_companies += 1

        scope_1 = safe_number(payload.get('scope_1_emissions'))
        scope_2 = safe_number(payload.get('scope_2_location_based'))
        scope_3 = safe_number(payload.get('scope_3_emissions'))
        total_ghg = safe_number(payload.get('total_ghg_emissions'))
        energy = safe_number(payload.get('total_energy_consumption'))
        renewable = safe_number(payload.get('renewable_energy_consumption'))
        water = safe_number(payload.get('total_water_withdrawal'))
        waste = safe_number(payload.get('total_waste_generated'))
        female_rep = safe_number(payload.get('female_representation_percent'))
        trifr = safe_number(payload.get('trifr'))
        independent_board = safe_number(payload.get('independent_board_members_percent'))
        turnover = safe_number(payload.get('employee_turnover_rate'))
        corruption_cases = safe_number(payload.get('confirmed_cases_of_corruption'))

        total_scope_1 += scope_1
        total_scope_2 += scope_2
        total_scope_3 += scope_3
        total_energy += energy
        total_water += water
        total_waste += waste
        total_female_rep += female_rep
        total_trifr += trifr

        renewable_ratio = (renewable / energy) if energy > 0 else 0
        scope_total = scope_1 + scope_2 + scope_3

        e_score = clamp(
            30
            + max(0, 35 - (scope_total / 60))
            + min(20, safe_number(payload.get('reduction_target_percent')) * 0.25)
            + min(15, renewable_ratio * 100 * 0.2)
        )
        s_score = clamp(
            25
            + min(25, female_rep * 0.35)
            + max(0, 20 - trifr * 2.5)
            + max(0, 15 - turnover * 0.3)
            + (15 if str(payload.get('whs_policy_in_place', '')).strip().lower() == 'yes' else 0)
        )
        g_score = clamp(
            (20 if str(payload.get('esg_policy_in_place', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('board_level_esg_oversight', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes' else 0)
            + (20 if str(payload.get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes' else 0)
            + min(20, independent_board * 0.4)
            - min(10, corruption_cases * 2)
        )
        esg_score = round((0.45 * e_score) + (0.30 * s_score) + (0.25 * g_score), 2)

        score_e_total += e_score
        score_s_total += s_score
        score_g_total += g_score
        score_total += esg_score

        company_scores.append({
            'company_name': company.name,
            'sector': company.sector,
            'esg_score': esg_score,
        })
        sector_scores.setdefault(company.sector, []).append(esg_score)

        governance_checks += 4
        governance_yes += 1 if str(payload.get('esg_policy_in_place', '')).strip().lower() == 'yes' else 0
        governance_yes += 1 if str(payload.get('board_level_esg_oversight', '')).strip().lower() == 'yes' else 0
        governance_yes += 1 if str(payload.get('cybersecurity_policy_in_place', '')).strip().lower() == 'yes' else 0
        governance_yes += 1 if str(payload.get('anti_bribery_corruption_policy', '')).strip().lower() == 'yes' else 0

        filled_fields = sum(1 for field in required_fields if payload.get(field) is not None)
        completeness_total += (filled_fields / len(required_fields)) * 100

        confidence_values = [str(value).strip().lower() for key, value in payload.items() if key.endswith('_confidence')]
        if confidence_values:
            measured_count = sum(1 for value in confidence_values if value == 'measured')
            confidence_total += (measured_count / len(confidence_values)) * 100
        else:
            confidence_total += 0

        accuracy = 100.0
        if total_ghg > 0:
            delta = abs(total_ghg - scope_total) / max(total_ghg, 1)
            if delta > 0.05:
                accuracy -= min(30, delta * 100)
        if renewable > energy and energy > 0:
            accuracy -= 10
        accuracy_total += clamp(accuracy)

        prev_total_ghg = safe_number(previous_payload.get('total_ghg_emissions'))
        if prev_total_ghg > 0:
            variance = abs(total_ghg - prev_total_ghg) / prev_total_ghg
            if variance > 0.30:
                high_variance_count += 1

    reporting_count = max(reporting_companies, 1)
    portfolio_total_emissions = total_scope_1 + total_scope_2 + total_scope_3
    sector_underperforming = sorted(
        (
            (sector, sum(values) / len(values))
            for sector, values in sector_scores.items()
            if values
        ),
        key=lambda item: item[1]
    )

    top_performers = sorted(company_scores, key=lambda item: item['esg_score'], reverse=True)[:5]
    bottom_performers = sorted(company_scores, key=lambda item: item['esg_score'])[:5]

    return {
        'total_companies': len(companies),
        'reporting_companies': reporting_companies,
        'total_submissions': total_submissions,
        'status_counts': status_counts,
        'submission_funnel': status_counts,
        'portfolio_esg_score': round(score_total / reporting_count, 2),
        'score_breakdown': {
            'E': round(score_e_total / reporting_count, 2),
            'S': round(score_s_total / reporting_count, 2),
            'G': round(score_g_total / reporting_count, 2),
        },
        'average_ghg_emissions': round(portfolio_total_emissions / reporting_count, 2),
        'average_female_representation': round(total_female_rep / reporting_count, 2),
        'underperforming_sectors': [sector for sector, _ in sector_underperforming[:3]],
        'emissions_totals': {
            'scope_1': round(total_scope_1, 2),
            'scope_2': round(total_scope_2, 2),
            'scope_3': round(total_scope_3, 2),
            'total': round(portfolio_total_emissions, 2),
        },
        'emissions_trend': build_emissions_trend(portfolio_total_emissions),
        'resource_totals': {
            'energy': round(total_energy, 2),
            'water': round(total_water, 2),
            'waste': round(total_waste, 2),
        },
        'diversity_safety': {
            'female_representation_percent': round(total_female_rep / reporting_count, 2),
            'trifr': round(total_trifr / reporting_count, 2),
            'high_variance_flags': float(high_variance_count),
        },
        'governance_adoption_percent': round((governance_yes / governance_checks) * 100, 2) if governance_checks else 0.0,
        'top_performers': top_performers,
        'bottom_performers': bottom_performers,
        'data_quality': {
            'completeness': round(completeness_total / reporting_count, 2),
            'accuracy': round(accuracy_total / reporting_count, 2),
            'confidence': round(confidence_total / reporting_count, 2),
        },
    }


def _call_openai_narrative(prompt: str) -> dict | None:
    api_key = str(os.getenv('OPENAI_API_KEY') or '').strip()
    if not api_key or OpenAI is None:
        return None

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=OPENAI_DEFAULT_MODEL,
            temperature=0.2,
            response_format={'type': 'json_object'},
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'Return strict JSON with keys: headline, summary, highlights, watchouts, recommendations. '
                        'highlights/watchouts/recommendations must be arrays of short strings.'
                    ),
                },
                {'role': 'user', 'content': prompt},
            ],
        )
        content = (((response.choices or [None])[0] or {}).message or {}).content
        if not content:
            return None
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _fallback_portfolio_narrative(analytics: dict) -> dict:
    score = float(analytics.get('portfolio_esg_score') or 0)
    approved = int((analytics.get('status_counts') or {}).get('Approved', 0))
    companies = int(analytics.get('total_companies') or 0)
    top_sector = ', '.join((analytics.get('underperforming_sectors') or [])[:2]) or 'portfolio watch sectors'
    return {
        'headline': 'Investor Portfolio ESG Summary',
        'summary': (
            f'Portfolio ESG score is {score:.1f} across {companies} companies with {approved} approved submissions. '
            f'Focus remains on {top_sector} and consistency of approved data quality.'
        ),
        'highlights': [
            f"Portfolio ESG score: {score:.1f}/100",
            f"Approved submissions: {approved}",
            f"Data confidence index: {float((analytics.get('data_quality') or {}).get('confidence') or 0):.1f}%",
        ],
        'watchouts': [
            f"Average emissions: {float(analytics.get('average_ghg_emissions') or 0):.1f} tCO2e",
            f"Governance adoption: {float(analytics.get('governance_adoption_percent') or 0):.1f}%",
        ],
        'recommendations': [
            'Keep investor updates tied to approved submissions only.',
            'Prioritize remediation for sectors with recurring underperformance.',
        ],
    }


def _fallback_company_narrative(company: Company, payload: dict, status_label: str) -> dict:
    total_ghg = safe_number(payload.get('total_ghg_emissions'))
    reduction = safe_number(payload.get('reduction_target_percent'))
    female_rep = safe_number(payload.get('female_representation_percent'))
    return {
        'headline': f'{company.name} ESG Snapshot',
        'summary': (
            f'{company.name} is currently {status_label}. '
            f'Total GHG emissions are {total_ghg:.1f} tCO2e with a reduction target of {reduction:.1f}% and '
            f'female representation at {female_rep:.1f}%.'
        ),
        'highlights': [
            f"Current status: {status_label}",
            f"Total GHG emissions: {total_ghg:.1f} tCO2e",
            f"Reduction target: {reduction:.1f}%",
        ],
        'watchouts': [
            'Validate confidence tags and policy-document references before final approval.',
        ],
        'recommendations': [
            'Address outstanding validation warnings before next investor update.',
            'Keep narrative aligned with latest approved submission values.',
        ],
    }


def _normalize_narrative_payload(payload: dict | None, fallback: dict) -> dict:
    source = payload if isinstance(payload, dict) else {}

    def _list_value(key: str) -> list[str]:
        raw = source.get(key)
        if isinstance(raw, list):
            items = [str(item).strip() for item in raw if str(item).strip()]
            if items:
                return items[:5]
        return list(fallback.get(key) or [])

    return {
        'headline': str(source.get('headline') or fallback.get('headline') or '').strip(),
        'summary': str(source.get('summary') or fallback.get('summary') or '').strip(),
        'highlights': _list_value('highlights'),
        'watchouts': _list_value('watchouts'),
        'recommendations': _list_value('recommendations'),
    }


@app.get('/narrative/summary')
def narrative_summary(
    audience: str = Query(default='lp'),
    company_id: int | None = Query(default=None),
    tone: str = Query(default='board-ready'),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_audience = str(audience or 'lp').strip().lower()
    if normalized_audience in {'lp', 'investor', 'portfolio'}:
        normalized_audience = 'lp'
    elif normalized_audience == 'company':
        normalized_audience = 'company'
    else:
        raise HTTPException(status_code=400, detail='Invalid narrative audience')

    if normalized_audience == 'company':
        if role == 'investor':
            raise HTTPException(status_code=403, detail='Investors cannot access company-level narrative summaries')

        target_company = None
        if company_id is not None:
            target_company = db.query(Company).filter(Company.id == company_id).first()
        elif role == 'company':
            request_user = find_request_user(db, email)
            if request_user:
                target_company = db.query(Company).filter(Company.user_id == request_user.id).first()
        if target_company is None:
            target_company = db.query(Company).order_by(Company.id.asc()).first()
        if target_company is None:
            raise HTTPException(status_code=404, detail='No company data available for narrative summary')

        if role == 'company':
            request_user = find_request_user(db, email)
            if request_user and target_company.user_id != request_user.id:
                raise HTTPException(status_code=403, detail='Company users can only access their own narrative summary')

        latest_submission = (
            db.query(Submission)
            .filter(Submission.company_id == target_company.id)
            .order_by(Submission.id.desc())
            .first()
        )
        payload = parse_submission(latest_submission)
        status_label = normalize_status_label((latest_submission.status if latest_submission else target_company.current_status))
        fallback = _fallback_company_narrative(target_company, payload, status_label)
        prompt = (
            f"Write a concise ESG company narrative for {target_company.name}.\n"
            f"Audience: {normalized_audience}. Tone: {tone}.\n"
            f"Status: {status_label}\n"
            f"Key payload: {json.dumps(payload, default=str)[:5000]}"
        )
        ai_payload = _call_openai_narrative(prompt)
        normalized_payload = _normalize_narrative_payload(ai_payload, fallback)
        generated_at = datetime.now(timezone.utc).isoformat()
        return {
            'narrative_id': 0,
            'scope': 'company',
            'audience': normalized_audience,
            'tone': tone,
            'company_id': target_company.id,
            'company_name': target_company.name,
            'provider': 'openai' if ai_payload else 'fallback',
            'fallback_used': not bool(ai_payload),
            'generated_at': generated_at,
            **normalized_payload,
        }

    if role == 'company':
        raise HTTPException(status_code=403, detail='Company users cannot access portfolio-level narrative summaries')

    analytics = build_investor_analytics(db)
    fallback = _fallback_portfolio_narrative(analytics)
    prompt = (
        "Write a concise portfolio ESG narrative for LP/investor audience.\n"
        f"Tone: {tone}. Use these analytics: {json.dumps(analytics, default=str)[:7000]}"
    )
    ai_payload = _call_openai_narrative(prompt)
    normalized_payload = _normalize_narrative_payload(ai_payload, fallback)
    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        'narrative_id': 0,
        'scope': 'portfolio',
        'audience': 'lp',
        'tone': tone,
        'company_id': None,
        'company_name': None,
        'provider': 'openai' if ai_payload else 'fallback',
        'fallback_used': not bool(ai_payload),
        'generated_at': generated_at,
        **normalized_payload,
    }


@app.get('/analytics/portfolio', response_model=InvestorSummary)
def analytics_portfolio(db: Session = Depends(get_db)):
    analytics = build_investor_analytics(db)
    return InvestorSummary(
        total_companies=analytics['total_companies'],
        total_submissions=analytics['total_submissions'],
        status_counts=analytics['status_counts'],
        portfolio_esg_score=analytics['portfolio_esg_score'],
        average_ghg_emissions=analytics['average_ghg_emissions'],
        average_female_representation=analytics['average_female_representation'],
        underperforming_sectors=analytics['underperforming_sectors'],
    )


@app.get('/dashboard/investor', response_model=InvestorDashboardResponse)
def investor_dashboard(db: Session = Depends(get_db)):
    # Investor receives portfolio-level analytics only (no raw company submissions).
    return InvestorDashboardResponse(**build_investor_analytics(db))
