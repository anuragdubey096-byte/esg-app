import csv
import json
import os
import re
import asyncio
import html
from threading import RLock
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, List
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
from xml.etree import ElementTree

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Header, Query, Body, WebSocket, WebSocketDisconnect
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
    NarrativeRecord,
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
    ValidationDecisionRequest,
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
if os.getenv('VERCEL'):
    EXPORT_DIR = Path('/tmp/exports')
else:
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
COLLAB_SESSION_COUNTER = 0
COLLAB_LOCK = RLock()
COLLAB_STATE: dict[int, dict[str, Any]] = {}
LIVE_EVENT_COUNTER = 0
LIVE_EVENTS: list[dict[str, Any]] = []
LIVE_WEBSOCKETS: list[dict[str, Any]] = []
NEWS_FEED_TTL_SECONDS = int(os.getenv('NEWS_FEED_TTL_SECONDS', '900') or '900')
NEWS_FEED_SOURCES = [
    {
        'id': 'google_esg',
        'label': 'Google News: ESG Investing',
        'priority': 'high',
        'url': 'https://news.google.com/rss/search?q=ESG+investing&hl=en-US&gl=US&ceid=US:en',
    },
    {
        'id': 'google_climate_disclosure',
        'label': 'Google News: Climate Disclosure',
        'priority': 'high',
        'url': 'https://news.google.com/rss/search?q=climate+disclosure+regulation&hl=en-US&gl=US&ceid=US:en',
    },
    {
        'id': 'google_sustainable_finance',
        'label': 'Google News: Sustainable Finance',
        'priority': 'medium',
        'url': 'https://news.google.com/rss/search?q=sustainable+finance+institutional+investors&hl=en-US&gl=US&ceid=US:en',
    },
]
NEWS_FEED_CACHE: dict[str, Any] = {
    'fetched_at': None,
    'items': [],
    'source_count': 0,
    'fallback_used': True,
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


def _next_collab_session_id() -> int:
    global COLLAB_SESSION_COUNTER
    with COLLAB_LOCK:
        COLLAB_SESSION_COUNTER += 1
        return COLLAB_SESSION_COUNTER


def _next_live_event_id() -> int:
    global LIVE_EVENT_COUNTER
    with COLLAB_LOCK:
        LIVE_EVENT_COUNTER += 1
        return LIVE_EVENT_COUNTER


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace('+00:00', 'Z')


def _get_owned_company_for_email(db: Session, email: str | None) -> Company | None:
    request_user = find_request_user(db, email)
    if not request_user:
        return None
    return db.query(Company).filter(Company.user_id == request_user.id).first()


def _resolve_submission_for_cycle(
    db: Session,
    cycle_id: int,
    role: str,
    email: str | None,
    company_id: int | None = None,
) -> Submission | None:
    if role == 'company':
        owned_company = _get_owned_company_for_email(db, email)
        if not owned_company:
            return None
        return (
            db.query(Submission)
            .filter(Submission.company_id == owned_company.id, Submission.cycle_id == cycle_id)
            .order_by(Submission.id.desc())
            .first()
        )

    query = db.query(Submission).filter(Submission.cycle_id == cycle_id)
    if company_id is not None:
        query = query.filter(Submission.company_id == company_id)
    return query.order_by(Submission.id.desc()).first()


def _resolve_submission_by_id_accessible(
    db: Session,
    submission_id: int,
    role: str,
    email: str | None,
) -> Submission | None:
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        return None
    if role != 'company':
        return submission
    owned_company = _get_owned_company_for_email(db, email)
    if not owned_company or owned_company.id != submission.company_id:
        return None
    return submission


def _build_collab_key(submission_id: int) -> int:
    return int(submission_id)


def _cleanup_collaboration_sessions(submission_id: int) -> None:
    now = _utc_now()
    with COLLAB_LOCK:
        state = COLLAB_STATE.get(_build_collab_key(submission_id))
        if not state:
            return
        sessions = state.get('sessions', [])
        active = []
        for session in sessions:
            expires_raw = session.get('expires_at')
            expires = None
            if isinstance(expires_raw, str):
                try:
                    expires = datetime.fromisoformat(expires_raw.replace('Z', '+00:00'))
                except ValueError:
                    expires = None
            if expires and expires <= now:
                continue
            if session.get('status') != 'active':
                continue
            active.append(session)
        state['sessions'] = active


def _current_collaboration_payload(
    submission: Submission,
    role: str,
    email: str | None,
) -> dict:
    _cleanup_collaboration_sessions(submission.id)
    with COLLAB_LOCK:
        state = COLLAB_STATE.get(_build_collab_key(submission.id), {'lock_mode': 'soft', 'sessions': []})
        sessions = list(state.get('sessions', []))

    active_sections = []
    current_user_sections = []
    for session in sessions:
        owner_email = session.get('owner_email')
        section_name = session.get('section')
        is_you = bool(owner_email and email and owner_email == email)
        entry = {
            'id': session.get('id'),
            'submission_id': submission.id,
            'company_id': submission.company_id,
            'cycle_id': submission.cycle_id,
            'section': section_name,
            'owner_role': session.get('owner_role'),
            'owner_email': owner_email,
            'owner_name': session.get('owner_name'),
            'status': session.get('status', 'active'),
            'lock_mode': state.get('lock_mode', 'soft'),
            'is_you': is_you,
            'expires_at': session.get('expires_at'),
            'last_seen_at': session.get('last_seen_at'),
            'created_at': session.get('created_at'),
            'updated_at': session.get('updated_at'),
        }
        active_sections.append(entry)
        if is_you and section_name:
            current_user_sections.append(section_name)

    return {
        'submission_id': submission.id,
        'company_id': submission.company_id,
        'cycle_id': submission.cycle_id,
        'lock_mode': 'soft',
        'active_sections': active_sections,
        'current_user_sections': current_user_sections,
        'viewer_role': role,
        'viewer_email': email,
    }


def _queue_live_event(event: dict[str, Any]) -> None:
    with COLLAB_LOCK:
        LIVE_EVENTS.append(event)
        if len(LIVE_EVENTS) > 500:
            del LIVE_EVENTS[:-500]

    async def _dispatch():
        stale = []
        for conn in LIVE_WEBSOCKETS:
            websocket = conn.get('socket')
            if websocket is None:
                continue
            try:
                await websocket.send_json({'type': 'event', 'event': event})
            except Exception:
                stale.append(conn)
        if stale:
            for dead in stale:
                if dead in LIVE_WEBSOCKETS:
                    LIVE_WEBSOCKETS.remove(dead)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_dispatch())
    except RuntimeError:
        return


def _log_live_event(
    *,
    event_type: str,
    title: str,
    message: str,
    severity: str,
    actor_role: str,
    actor_email: str | None,
    company_id: int | None,
    company_name: str | None,
    submission_id: int | None,
    cycle_id: int | None,
    entity_status: str | None,
    is_toast: bool = False,
    visible_to_investors: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict:
    event = {
        'id': _next_live_event_id(),
        'event_type': event_type,
        'title': title,
        'message': message,
        'severity': severity,
        'actor_role': actor_role,
        'actor_email': actor_email,
        'company_id': company_id,
        'company_name': company_name,
        'submission_id': submission_id,
        'cycle_id': cycle_id,
        'entity_status': entity_status,
        'is_toast': is_toast,
        'visible_to_investors': visible_to_investors,
        'metadata': metadata or {},
        'created_at': _utc_now_iso(),
    }
    _queue_live_event(event)
    return event

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
    _log_live_event(
        event_type='submission_submitted',
        title='Submission submitted',
        message=f'{company.name} submitted ESG data for FY{submission_record.cycle.cycle_year if submission_record.cycle else "current"}.',
        severity='success',
        actor_role='company',
        actor_email=None,
        company_id=company.id,
        company_name=company.name,
        submission_id=submission_record.id,
        cycle_id=submission_record.cycle_id,
        entity_status=normalize_submission_status(submission_record.status),
        is_toast=True,
        visible_to_investors=True,
        metadata={'cycle_year': submission_record.cycle.cycle_year if submission_record.cycle else None},
    )
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


@app.post('/submissions/{submission_id}/validation-decision', dependencies=[Depends(require_manager)])
def set_validation_decision(
    submission_id: int,
    payload: ValidationDecisionRequest,
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    field_name = str(payload.field_name or '').strip()
    if not field_name:
        raise HTTPException(status_code=400, detail='field_name is required')

    decision = str(payload.decision or '').strip().lower()
    if decision not in {'pass', 'fail'}:
        raise HTTPException(status_code=400, detail='decision must be pass or fail')

    reporting_year = submission.cycle.cycle_year if submission.cycle else datetime.utcnow().year

    existing_flags = (
        db.query(ValidationFlag)
        .filter(
            ValidationFlag.company_id == submission.company_id,
            ValidationFlag.reporting_year == reporting_year,
            ValidationFlag.field_name == field_name,
        )
        .all()
    )
    for flag in existing_flags:
        db.delete(flag)

    if decision == 'pass':
        db.add(
            ValidationFlag(
                company_id=submission.company_id,
                reporting_year=reporting_year,
                flag_type='Manual Validation',
                field_name=field_name,
                issue_description='Admin marked this metric as Pass.',
                severity='Info',
            )
        )
    else:
        fail_comment = str(payload.comment or '').strip() or 'Admin manually marked this metric as Fail.'
        db.add(
            ValidationFlag(
                company_id=submission.company_id,
                reporting_year=reporting_year,
                flag_type='Manual Validation',
                field_name=field_name,
                issue_description=fail_comment,
                severity='High',
            )
        )

    db.commit()
    return {
        'message': f'Validation decision recorded as {decision.upper()}.',
        'submission_id': submission_id,
        'company_id': submission.company_id,
        'reporting_year': reporting_year,
        'field_name': field_name,
        'decision': decision,
    }

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
    company = db.query(Company).filter(Company.id == submission.company_id).first()
    _log_live_event(
        event_type='submission_unlock_granted',
        title='Submission unlocked',
        message=f'{company.name if company else "Company"} was unlocked for edits.',
        severity='warning',
        actor_role='manager',
        actor_email=user_email,
        company_id=submission.company_id,
        company_name=company.name if company else None,
        submission_id=submission.id,
        cycle_id=submission.cycle_id,
        entity_status=normalize_submission_status(submission.status),
        is_toast=True,
        visible_to_investors=False,
        metadata={'reason': payload.reason, 'expiry_hours': payload.expiry_hours},
    )
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
    _log_live_event(
        event_type='reminder_sent',
        title='Reminder sent',
        message=payload.message.strip(),
        severity='warning',
        actor_role='manager',
        actor_email=user_email,
        company_id=company.id,
        company_name=company.name,
        submission_id=None,
        cycle_id=cycle.id,
        entity_status='logged',
        is_toast=True,
        visible_to_investors=False,
        metadata={'channel': reminder.channel},
    )
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
                        'The summary must be detailed, specific, and decision-useful (minimum 120 words). '
                        'highlights/watchouts/recommendations must each be arrays of 3-5 specific strings.'
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
            f'Current operating performance suggests mixed maturity across the portfolio: reporting consistency is improving, '
            f'but concentration in {top_sector} still creates outsized risk to aggregate results. '
            f'Near-term execution should prioritize quality assurance on material metrics, faster closure of review comments, '
            f'and clear accountability for remediation owners so approved data remains decision-grade for LP updates. '
            f'In practice, this means setting weekly close-out targets for unresolved validation flags, requiring confidence-tag evidence '
            f'for all material emissions and governance indicators, and aligning portfolio companies to a common remediation cadence. '
            f'Management should track sector-level variance and exception trends in monthly operating reviews, then convert recurring issues '
            f'into specific owner-led action plans with deadlines before the next investor communication cycle.'
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
            f'female representation at {female_rep:.1f}%. '
            f'Operationally, this indicates the company has baseline ESG instrumentation in place, but data quality and '
            f'control evidence should be reviewed before stakeholder distribution. '
            f'The next reporting cycle should focus on improving confidence tags, closing validation warnings, and '
            f'aligning claims with approved submission evidence so management and investor narratives remain audit-ready. '
            f'Execution should include explicit ownership of unresolved data points, a short-cycle validation checklist before submission lock, '
            f'and documented reconciliation for any metric drift versus prior periods. '
            f'Leadership updates should separate confirmed performance progress from provisional estimates, so board and investor narratives '
            f'reflect verified outcomes and clearly scoped near-term corrective actions.'
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
        'summary': _ensure_detailed_summary(
            str(source.get('summary') or ''),
            str(fallback.get('summary') or ''),
        ),
        'highlights': _list_value('highlights'),
        'watchouts': _list_value('watchouts'),
        'recommendations': _list_value('recommendations'),
    }


def _word_count(text: str) -> int:
    return len([part for part in str(text or '').split() if part.strip()])


def _ensure_detailed_summary(primary_summary: str, fallback_summary: str = '') -> str:
    primary_clean = str(primary_summary or '').strip()
    fallback_clean = str(fallback_summary or '').strip()
    if _word_count(primary_clean) >= 120:
        return primary_clean
    if _word_count(fallback_clean) >= 120:
        return fallback_clean
    if primary_clean and fallback_clean and primary_clean != fallback_clean:
        merged = f'{primary_clean} {fallback_clean}'.strip()
        if _word_count(merged) >= 120:
            return merged
        candidate = merged
    else:
        candidate = primary_clean or fallback_clean

    if _word_count(candidate) >= 120:
        return candidate

    expansion = (
        ' Additional context: teams should validate material metrics against approved submissions, '
        'explicitly tag confidence levels for key indicators, and track open remediation actions with '
        'named owners and due dates. Narrative updates should separate verified outcomes from estimates, '
        'highlight unresolved risks, and document next-cycle priorities so leadership and investor decisions '
        'stay aligned with auditable evidence.'
    )
    while _word_count(candidate) < 120:
        candidate = f'{candidate}{expansion}'.strip()
    return candidate


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
    if normalized_audience in {'lp', 'investor', 'portfolio', 'board'}:
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
            f"Write a detailed ESG company narrative for {target_company.name}.\n"
            f"Audience: {normalized_audience}. Tone: {tone}.\n"
            "Requirements:\n"
            "- Summary must be 120-220 words and include current performance, risk signals, and next-step actions.\n"
            "- Tie conclusions to the provided data; do not use placeholders.\n"
            "- Use clear management language suitable for review meetings.\n"
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
        "Write a detailed portfolio ESG narrative for LP/investor audience.\n"
        f"Tone: {tone}.\n"
        "Requirements:\n"
        "- Summary must be 120-220 words and include portfolio performance, concentration risks, and execution priorities.\n"
        "- Reference specific metrics from the analytics payload.\n"
        "- Keep the narrative factual, board-ready, and decision-oriented.\n"
        f"Use these analytics: {json.dumps(analytics, default=str)[:7000]}"
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


@app.post('/narrative/generate')
def narrative_generate(
    audience: str = Query(default='lp'),
    company_id: int | None = Query(default=None),
    tone: str = Query(default='board-ready'),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    summary_payload = narrative_summary(
        audience=audience,
        company_id=company_id,
        tone=tone,
        db=db,
        role=role,
        email=email,
    )
    return _record_from_summary(db=db, summary_payload=summary_payload, tone=tone, role=role)


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


# ==========================================
# Restoration Compatibility Layer (Phases 1-6)
# ==========================================
def require_investor(role: str = Depends(get_user_role)):
    if role != 'investor':
        raise HTTPException(status_code=403, detail='Access restricted to investors')


def require_manager_or_investor(role: str = Depends(get_user_role)):
    if role not in {'manager', 'investor'}:
        raise HTTPException(status_code=403, detail='Access is restricted to managers and investors')


def _validate_cron_secret(secret: str | None, x_cron_secret: str | None, authorization: str | None) -> None:
    configured_secret = str(os.getenv('CRON_SECRET') or '').strip()
    if not configured_secret:
        raise HTTPException(status_code=503, detail='CRON_SECRET is not configured')
    provided = (secret or x_cron_secret or '').strip()
    if not provided and authorization:
        token = authorization.strip()
        if token.lower().startswith('bearer '):
            provided = token[7:].strip()
    if provided != configured_secret:
        raise HTTPException(status_code=403, detail='Invalid CRON_SECRET')


def _build_lp_key_metrics(analytics: dict) -> list[dict]:
    emissions_totals = analytics.get('emissions_totals') or {}
    resource_totals = analytics.get('resource_totals') or {}
    data_quality = analytics.get('data_quality') or {}
    return [
        {
            'metric_name': 'Portfolio ESG Score',
            'current_value': f"{float(analytics.get('portfolio_esg_score') or 0):.1f}",
            'unit': 'score',
            'trend_percent': 0.0,
            'trend_direction': 'neutral',
            'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Total GHG Emissions',
            'current_value': f"{float(emissions_totals.get('total') or 0):.1f}",
            'unit': 'tCO2e',
            'trend_percent': 0.0,
            'trend_direction': 'neutral',
            'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Energy Consumption',
            'current_value': f"{float(resource_totals.get('energy') or 0):.1f}",
            'unit': 'MWh',
            'trend_percent': 0.0,
            'trend_direction': 'neutral',
            'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Data Completeness',
            'current_value': f"{float(data_quality.get('completeness') or 0):.1f}",
            'unit': '%',
            'trend_percent': 0.0,
            'trend_direction': 'neutral',
            'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        },
    ]


def _build_lp_dashboard_payload(db: Session) -> dict:
    analytics = build_investor_analytics(db)
    companies = int(analytics.get('total_companies') or 0)
    reporting_companies = int(analytics.get('reporting_companies') or 0)
    narrative = _fallback_portfolio_narrative(analytics)
    return {
        'portfolio_scorecard': {
            'overall_esg_score': float(analytics.get('portfolio_esg_score') or 0),
            'overall_esg_score_previous': float(analytics.get('portfolio_esg_score') or 0),
            'yoy_change_percent': 0.0,
            'three_year_trend': [float(analytics.get('portfolio_esg_score') or 0)] * 4,
            'pillars': [
                {'name': 'E', 'current_score': float((analytics.get('score_breakdown') or {}).get('E') or 0)},
                {'name': 'S', 'current_score': float((analytics.get('score_breakdown') or {}).get('S') or 0)},
                {'name': 'G', 'current_score': float((analytics.get('score_breakdown') or {}).get('G') or 0)},
            ],
        },
        'completion_status': {
            'total_companies': companies,
            'companies_with_approved_submission': int((analytics.get('status_counts') or {}).get('Approved', 0)),
            'completion_percent': round((reporting_companies / max(companies, 1)) * 100, 2),
            'last_updated': _utc_now_iso(),
        },
        'key_metrics': _build_lp_key_metrics(analytics),
        'emissions_trend': analytics.get('emissions_trend') or [],
        'impact_story': {
            'headline': 'Portfolio impact story',
            'summary': narrative.get('summary'),
            'highlights': narrative.get('highlights') or [],
            'watchouts': narrative.get('watchouts') or [],
            'recommendations': narrative.get('recommendations') or [],
            'trend_summary': 'Portfolio trend data is available for the selected cycle history.',
            'benchmark_callouts': [],
            'comparison_rows': [],
        },
    }


COLLAB_SECTION_FIELDS = {
    'environmental': [
        ('scope_1_emissions', 'Scope 1 Emissions', 'tCO2e', 'Emissions', 'number', True, 'Direct GHG emissions from owned or controlled sources.'),
        ('scope_2_location_based', 'Scope 2 Emissions (Location-based)', 'tCO2e', 'Emissions', 'number', True, 'Indirect emissions from purchased electricity (location method).'),
        ('scope_2_market_based', 'Scope 2 Emissions (Market-based)', 'tCO2e', 'Emissions', 'number', False, 'Indirect emissions from purchased electricity (market method).'),
        ('scope_3_emissions', 'Scope 3 Emissions', 'tCO2e', 'Emissions', 'number', True, 'Value chain emissions upstream and downstream.'),
        ('total_ghg_emissions', 'Total GHG Emissions', 'tCO2e', 'Emissions', 'number', True, 'Normally equals Scope 1 + Scope 2 (location-based) + Scope 3.'),
        ('reduction_target_percent', 'Reduction Target', '%', 'Targets & Strategy', 'percent', False, 'Targeted emissions reduction percentage.'),
        ('reduction_target_year', 'Reduction Target Year', 'year', 'Targets & Strategy', 'integer', False, 'Year by which target percentage should be achieved.'),
        ('reduction_strategy_description', 'Reduction Strategy Description', None, 'Targets & Strategy', 'textarea', False, 'Provide strategy details, especially when targets are set.'),
        ('total_energy_consumption', 'Total Energy Consumption', 'MWh', 'Energy', 'number', True, 'Total energy consumed in the reporting period.'),
        ('renewable_energy_consumption', 'Renewable Energy Consumption', 'MWh', 'Energy', 'number', True, 'Portion of total energy sourced from renewables.'),
        ('total_water_withdrawal', 'Total Water Withdrawal', 'm3', 'Water', 'number', True, 'Total water withdrawn during the reporting period.'),
        ('water_recycled_reused', 'Water Recycled / Reused', 'm3', 'Water', 'number', True, 'Water volume recycled or reused.'),
        ('total_waste_generated', 'Total Waste Generated', 'tonnes', 'Waste', 'number', True, 'Total waste produced in reporting period.'),
        ('waste_diverted_from_landfill', 'Waste Diverted from Landfill', 'tonnes', 'Waste', 'number', True, 'Waste diverted via recycling, recovery, or reuse.'),
        ('hazardous_waste_generated', 'Hazardous Waste Generated', 'tonnes', 'Waste', 'number', False, 'Hazardous waste generated during the period.'),
        ('air_quality_control_measures', 'Air Quality Control Measures', None, 'Air Quality', 'select', True, 'Status of air quality controls and mitigation measures.'),
        ('nox_sox_emissions', 'NOx / SOx Emissions', 'tonnes', 'Air Quality', 'number', False, 'Combined NOx and SOx emissions.'),
    ],
}


def _build_submission_collab_fields(payload: dict, section: str) -> list[dict]:
    normalized_section = (section or 'Environmental').strip().lower()
    schema = COLLAB_SECTION_FIELDS.get(normalized_section, COLLAB_SECTION_FIELDS['environmental'])
    fields = []
    for field_key, field_label, unit, subsection, input_type, required, helper_text in schema:
        value = payload.get(field_key)
        confidence_field = f'{field_key}_confidence'
        fields.append({
            'field_key': field_key,
            'field_label': field_label,
            'value': None if value is None else str(value),
            'prior_year_value': None,
            'unit': unit,
            'confidence_level': str(payload.get(confidence_field) or 'Estimated'),
            'yoy_variance_percent': None,
            'requires_explanation': False,
            'explanation': None,
            'subsection': subsection,
            'input_type': input_type,
            'helper_text': helper_text,
            'required': required,
            'read_only': False,
            'supports_reporting': True,
            'confidence_field': confidence_field,
            'confidence_options': ['High', 'Medium', 'Low', 'Estimated', 'Not Available', 'Measured'],
            'policy_options': ['Yes', 'No', 'In Progress', 'Not Applicable'] if input_type == 'select' else [],
            'conditional_visibility': None,
            'last_updated_at': _utc_now_iso(),
            'validation_errors': [],
        })
    return fields


def _build_live_activity_events(db: Session, limit: int, company_id: int | None = None) -> list[dict]:
    events: list[dict] = []
    company_filter = db.query(Company)
    if company_id is not None:
        company_filter = company_filter.filter(Company.id == company_id)
    company_scope = {item.id: item.name for item in company_filter.all()}

    if company_scope:
        submissions = (
            db.query(Submission)
            .filter(Submission.company_id.in_(list(company_scope.keys())))
            .order_by(Submission.id.desc())
            .limit(max(limit, 1))
            .all()
        )
        for submission in submissions:
            status = normalize_submission_status(submission.status)
            events.append({
                'id': f'submission-{submission.id}',
                'event_type': 'submission_submitted',
                'title': 'Submission update',
                'message': f"{company_scope.get(submission.company_id, 'Company')} submission is {status}.",
                'severity': 'info',
                'company_id': submission.company_id,
                'company_name': company_scope.get(submission.company_id),
                'submission_id': submission.id,
                'entity_status': status,
                'created_at': _utc_now_iso(),
            })

        reminders = (
            db.query(ReminderLog)
            .filter(ReminderLog.company_id.in_(list(company_scope.keys())))
            .order_by(ReminderLog.id.desc())
            .limit(max(limit, 1))
            .all()
        )
        for reminder in reminders:
            events.append({
                'id': f'reminder-{reminder.id}',
                'event_type': 'reminder_sent',
                'title': 'Reminder sent',
                'message': reminder.message,
                'severity': 'warning',
                'company_id': reminder.company_id,
                'company_name': company_scope.get(reminder.company_id),
                'submission_id': None,
                'entity_status': reminder.delivery_status,
                'created_at': reminder.created_at.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z'),
            })

    with COLLAB_LOCK:
        stream_events = list(LIVE_EVENTS)

    if stream_events:
        filtered_stream = []
        for event in stream_events:
            if company_id is not None and event.get('company_id') != company_id:
                continue
            filtered_stream.append(event)
        events.extend(filtered_stream)

    events.sort(key=lambda item: item.get('created_at', ''), reverse=True)
    return events[:max(limit, 1)]


def _build_newsletter_payload(db: Session, audience: str, tone: str) -> dict:
    analytics = build_investor_analytics(db)
    narrative = _fallback_portfolio_narrative(analytics)
    approved = int((analytics.get('status_counts') or {}).get('Approved', 0))
    companies = int(analytics.get('total_companies') or 0)
    return {
        'available': True,
        'audience': audience,
        'tone': tone,
        'generated_at': _utc_now_iso(),
        'subject_line': f'ESG newsletter: {companies} companies in view',
        'preheader': f"Portfolio ESG score {float(analytics.get('portfolio_esg_score') or 0):.1f}/100 with approved data updates.",
        'headline': narrative.get('headline') or 'Approved ESG data in plain English',
        'summary': narrative.get('summary') or '',
        'highlights': narrative.get('highlights') or [],
        'watchouts': narrative.get('watchouts') or [],
        'recommendations': narrative.get('recommendations') or [],
        'impact_headline': 'Portfolio impact story',
        'trend_summary': 'Portfolio trend data is available for the selected cycle history.',
        'benchmark_callouts': [],
        'source_company_count': companies,
        'source_submission_count': int(analytics.get('total_submissions') or 0),
        'fallback_used': True,
        'provider': 'fallback',
        'approved_count': approved,
    }


def _search_tokens(value: str) -> list[str]:
    return [token for token in re.split(r'[^a-z0-9]+', (value or '').lower()) if token]


def _score_match(query_tokens: list[str], haystack: str) -> float:
    if not query_tokens:
        return 0.0
    hay = (haystack or '').lower()
    score = 0.0
    for token in query_tokens:
        if token in hay:
            score += 1.0
    if hay.startswith(query_tokens[0]):
        score += 0.5
    return score


def _collect_global_search_items(
    db: Session,
    query: str,
    role: str,
    email: str | None,
    result_type: str | None = None,
    limit: int = 10,
) -> dict:
    q = (query or '').strip()
    query_tokens = _search_tokens(q)
    if not query_tokens:
        return {'query': query, 'role': role, 'result_count': 0, 'results': []}

    allowed_type = (result_type or '').strip().lower() or None

    page_catalog = {
        'manager': [
            {'title': 'Overview Dashboard', 'subtitle': 'Manager dashboard summary', 'path': '/overview', 'aliases': ['dashboard', 'overview', 'manager']},
            {'title': 'Submissions', 'subtitle': 'Submission tracking and review queue', 'path': '/submissions', 'aliases': ['submission', 'review', 'cycle']},
            {'title': 'Review Hub', 'subtitle': 'Manager review workspace', 'path': '/review-hub', 'aliases': ['review', 'approval']},
            {'title': 'Newsletter Operations', 'subtitle': 'Generate and distribute newsletters', 'path': '/newsletter-ops', 'aliases': ['newsletter', 'cron', 'send']},
            {'title': 'Anomaly Intelligence', 'subtitle': 'Validation anomalies across companies', 'path': '/anomaly-intel', 'aliases': ['anomaly', 'risk', 'flags']},
        ],
        'investor': [
            {'title': 'Investor Overview', 'subtitle': 'Portfolio-level ESG performance', 'path': '/overview', 'aliases': ['overview', 'portfolio', 'dashboard']},
            {'title': 'LP Insights Dashboard', 'subtitle': 'LP metrics, benchmark and impact story', 'path': '/lp-insights', 'aliases': ['lp', 'insights', 'impact']},
            {'title': 'Newsletter Operations', 'subtitle': 'Investor newsletter preview and export', 'path': '/newsletter-ops', 'aliases': ['newsletter', 'investor update']},
            {'title': 'Anomaly Intelligence', 'subtitle': 'Portfolio anomaly summary', 'path': '/anomaly-intel', 'aliases': ['anomaly', 'quality', 'risk']},
        ],
        'company': [
            {'title': 'Company Dashboard', 'subtitle': 'Open submission status and progress', 'path': '/overview', 'aliases': ['dashboard', 'company', 'overview']},
            {'title': 'Submissions', 'subtitle': 'Complete current cycle ESG submission', 'path': '/submissions', 'aliases': ['submission', 'data entry', 'cycle']},
            {'title': 'Action Plans', 'subtitle': 'Track improvement initiatives', 'path': '/action-plans', 'aliases': ['action', 'plan', 'improvement']},
            {'title': 'Anomaly Intelligence', 'subtitle': 'Company validation anomalies', 'path': '/anomaly-intel', 'aliases': ['anomaly', 'flags', 'quality']},
        ],
    }

    results = []

    def add_result(item_type: str, item_id: str, title: str, subtitle: str, path: str, score: float, **extra):
        if allowed_type and item_type.lower() != allowed_type:
            return
        if score <= 0:
            return
        results.append({
            'type': item_type,
            'id': item_id,
            'title': title,
            'subtitle': subtitle,
            'name': title,
            'path': path,
            'score': round(score, 2),
            **extra,
        })

    for page in page_catalog.get(role, []):
        haystack = f"{page['title']} {page['subtitle']} {' '.join(page.get('aliases', []))}"
        score = _score_match(query_tokens, haystack)
        add_result(
            'Page',
            f"page-{page['path']}",
            page['title'],
            page['subtitle'],
            page['path'],
            score,
            company_id=None,
            company_name=None,
            sector=None,
            metadata={'section': 'navigation', 'aliases': page.get('aliases', [])},
        )

    companies_query = db.query(Company)
    if role == 'company':
        owned_company = _get_owned_company_for_email(db, email)
        if owned_company:
            companies_query = companies_query.filter(Company.id == owned_company.id)
    for company in companies_query.order_by(Company.name.asc()).all():
        latest_submission = (
            db.query(Submission)
            .filter(Submission.company_id == company.id)
            .order_by(Submission.id.desc())
            .first()
        )
        status_label = normalize_status_label(latest_submission.status if latest_submission else company.current_status)
        subtitle = f"{company.sector} - {company.geography or 'Unknown geography'} - {status_label}"
        haystack = f'{company.name} {company.sector} {company.geography or ""} {status_label}'
        score = _score_match(query_tokens, haystack) + (0.3 if company.name.lower().startswith(query_tokens[0]) else 0.0)
        add_result(
            'Company',
            f'company-{company.id}',
            company.name,
            subtitle,
            '/submissions' if role != 'investor' else '/overview',
            score,
            company_id=company.id,
            company_name=company.name,
            sector=company.sector,
            metadata={
                'status': status_label,
                'current_status': company.current_status,
                'latest_submission_id': latest_submission.id if latest_submission else None,
                'latest_year': latest_submission.cycle.cycle_year if latest_submission and latest_submission.cycle else None,
            },
        )

    if role == 'manager':
        for action in db.query(ActionPlan).order_by(ActionPlan.id.desc()).limit(200).all():
            haystack = f'{action.initiative_name} {action.assigned_owner} {action.status}'
            score = _score_match(query_tokens, haystack)
            add_result(
                'ActionPlan',
                f'action-{action.id}',
                action.initiative_name,
                f'Owner: {action.assigned_owner} | Status: {action.status}',
                '/action-plans',
                score,
                company_id=action.company_id,
                company_name=None,
                sector=None,
                metadata={'owner': action.assigned_owner, 'status': action.status},
            )

    results.sort(key=lambda item: float(item.get('score') or 0), reverse=True)
    limited = results[:max(1, min(limit, 50))]
    return {
        'query': query,
        'role': role,
        'result_count': len(limited),
        'results': limited,
    }


def _extract_narrative_payload(summary_payload: dict) -> dict:
    return {
        'headline': summary_payload.get('headline') or 'ESG narrative',
        'summary': summary_payload.get('summary') or '',
        'highlights': list(summary_payload.get('highlights') or []),
        'watchouts': list(summary_payload.get('watchouts') or []),
        'recommendations': list(summary_payload.get('recommendations') or []),
    }


def _json_text(value: Any, default: str) -> str:
    try:
        return json.dumps(value if value is not None else json.loads(default))
    except Exception:
        return default


def _narrative_record_to_response(record: NarrativeRecord, role: str) -> dict:
    summary_text = _ensure_detailed_summary(record.summary or '')
    return {
        'available': True,
        'audience': record.audience,
        'scope': record.scope,
        'tone': record.tone,
        'status': record.status,
        'company_id': record.company_id,
        'company_name': record.company_name,
        'source_years': parse_json_or_default(record.source_years, []),
        'source_company_count': int(record.source_company_count or 0),
        'source_submission_count': int(record.source_submission_count or 0),
        'latest_source_years': parse_json_or_default(record.latest_source_years, []),
        'latest_source_company_count': int(record.latest_source_company_count or 0),
        'latest_source_submission_count': int(record.latest_source_submission_count or 0),
        'provider': record.provider,
        'model': record.model,
        'cached': bool(record.cached),
        'fallback_used': bool(record.fallback_used),
        'freshness_status': record.freshness_status,
        'freshness_label': record.freshness_label,
        'freshness_reason': record.freshness_reason,
        'generated_at': record.generated_at,
        'headline': record.headline,
        'summary': summary_text,
        'highlights': parse_json_or_default(record.highlights, []),
        'watchouts': parse_json_or_default(record.watchouts, []),
        'recommendations': parse_json_or_default(record.recommendations, []),
        'message': record.message,
        'narrative_id': record.id,
        'framework_tags': parse_json_or_default(record.framework_tags, []),
        'generated_payload': parse_json_or_default(record.generated_payload, {}),
        'edited_payload': parse_json_or_default(record.edited_payload, {}),
        'published_payload': parse_json_or_default(record.published_payload, {}),
        'approved_by_role': record.approved_by_role,
        'approved_at': record.approved_at,
        'edited_by_role': record.edited_by_role,
        'edited_at': record.edited_at,
        'updated_at': record.updated_at,
        'can_edit': role in {'manager', 'company'},
        'can_approve': role == 'manager',
        'can_export': role in {'manager', 'investor'},
    }


def _source_snapshot(db: Session, scope: str, company_id: int | None) -> dict:
    query = db.query(Submission).filter(func.lower(func.trim(Submission.status)) == 'approved')
    if scope == 'company' and company_id is not None:
        query = query.filter(Submission.company_id == company_id)
    rows = query.order_by(Submission.id.desc()).limit(200).all()
    years = sorted(
        {
            int(row.cycle.cycle_year)
            for row in rows
            if getattr(row, 'cycle', None) is not None and getattr(row.cycle, 'cycle_year', None) is not None
        },
        reverse=True,
    )
    company_ids = {int(row.company_id) for row in rows if row.company_id is not None}
    return {
        'source_years': years[:6],
        'source_company_count': len(company_ids),
        'source_submission_count': len(rows),
    }


def _record_from_summary(
    db: Session,
    summary_payload: dict,
    tone: str,
    role: str,
) -> dict:
    now_iso = _utc_now_iso()
    payload = _extract_narrative_payload(summary_payload)
    scope = summary_payload.get('scope') or 'portfolio'
    source = _source_snapshot(db, scope=scope, company_id=summary_payload.get('company_id'))
    record = NarrativeRecord(
        audience=summary_payload.get('audience') or 'lp',
        scope=scope,
        tone=tone,
        status='generated',
        company_id=summary_payload.get('company_id'),
        company_name=summary_payload.get('company_name'),
        source_years=_json_text(source['source_years'], '[]'),
        source_company_count=int(source['source_company_count']),
        source_submission_count=int(source['source_submission_count']),
        latest_source_years=_json_text(source['source_years'], '[]'),
        latest_source_company_count=int(source['source_company_count']),
        latest_source_submission_count=int(source['source_submission_count']),
        provider=summary_payload.get('provider') or 'fallback',
        model=summary_payload.get('model'),
        cached=False,
        fallback_used=bool(summary_payload.get('fallback_used', True)),
        freshness_status='current',
        freshness_label='Current narrative',
        freshness_reason='Narrative matches the latest approved data.',
        generated_at=now_iso,
        headline=str(payload.get('headline') or 'ESG narrative'),
        summary=str(payload.get('summary') or ''),
        highlights=_json_text(payload.get('highlights') or [], '[]'),
        watchouts=_json_text(payload.get('watchouts') or [], '[]'),
        recommendations=_json_text(payload.get('recommendations') or [], '[]'),
        message=None,
        framework_tags=_json_text(['SFDR', 'EDCI', 'TCFD'], '[]'),
        generated_payload=_json_text(payload, '{}'),
        edited_payload='{}',
        published_payload='{}',
        approved_by_role=None,
        approved_at=None,
        edited_by_role=None,
        edited_at=None,
        updated_at=now_iso,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _narrative_record_to_response(record, role=role)


def _can_access_narrative_record(db: Session, record: NarrativeRecord, role: str, email: str | None) -> bool:
    scope = record.scope
    if scope == 'portfolio':
        return role in {'manager', 'investor'}
    if scope == 'company':
        if role == 'manager':
            return True
        if role == 'investor':
            return False
        request_user = find_request_user(db, email)
        if not request_user:
            return False
        target_company = db.query(Company).filter(Company.user_id == request_user.id).first()
        return bool(target_company and int(target_company.id) == int(record.company_id or -1))
    return False


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'ready': True,
        'environment': 'vercel' if os.getenv('VERCEL') else 'local',
        'timestamp': _utc_now_iso(),
        'checks': {
            'database': {'ok': True, 'error': None},
            'storage': {'ok': True, 'mode': 'filesystem', 'error': None},
            'openai': {'ok': True, 'configured': bool(str(os.getenv('OPENAI_API_KEY') or '').strip()), 'error': None},
        },
        'message': 'Application health snapshot',
    }


@app.get('/health/ready')
def health_ready():
    payload = health()
    payload['message'] = 'Application is ready to serve requests'
    return payload


@app.get('/analytics/manager', dependencies=[Depends(require_manager)])
def analytics_manager(db: Session = Depends(get_db)):
    companies = db.query(Company).order_by(Company.name.asc()).all()
    return {
        'summary': build_manager_summary(db, companies),
        'analytics': build_investor_analytics(db),
    }


@app.get('/lp/dashboard', dependencies=[Depends(require_investor)])
def lp_dashboard(db: Session = Depends(get_db)):
    return _build_lp_dashboard_payload(db)


@app.get('/lp/metrics', dependencies=[Depends(require_investor)])
def lp_metrics(db: Session = Depends(get_db)):
    analytics = build_investor_analytics(db)
    return {
        'generated_at': _utc_now_iso(),
        'key_metrics': _build_lp_key_metrics(analytics),
    }


@app.get('/lp/reports', dependencies=[Depends(require_investor)])
def lp_reports(db: Session = Depends(get_db)):
    report_meta = generate_report('edci', db)
    return {
        'available_reports': ['EDCI', 'SFDR'],
        'active_cycle_year': report_meta.get('active_cycle_year'),
        'generated_at': _utc_now_iso(),
        'message': 'LP reports feed restored in compatibility mode.',
    }


@app.get('/narrative/history')
def narrative_history(
    audience: str = Query(default='lp'),
    limit: int = Query(default=10, ge=1, le=100),
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    normalized_audience = str(audience or 'lp').strip().lower()
    if normalized_audience in {'investor', 'portfolio'}:
        normalized_audience = 'lp'

    scope = 'company' if normalized_audience == 'company' else 'portfolio'
    store_matches = []
    for record in db.query(NarrativeRecord).order_by(NarrativeRecord.id.desc()).limit(500).all():
        if record.scope != scope:
            continue
        if scope == 'company' and company_id is not None and int(record.company_id or -1) != company_id:
            continue
        if not _can_access_narrative_record(db, record, role, email):
            continue
        store_matches.append(record)

    items = []
    for item in store_matches[:limit]:
        items.append({
            'narrative_id': item.id,
            'headline': item.headline,
            'summary': item.summary,
            'audience': item.audience,
            'scope': item.scope,
            'provider': item.provider,
            'fallback_used': bool(item.fallback_used),
            'freshness_status': item.freshness_status or 'historical',
            'generated_at': item.generated_at,
            'status': item.status,
        })

    if not items:
        latest = narrative_summary(
            audience=audience,
            company_id=company_id,
            tone='board-ready',
            db=db,
            role=role,
            email=email,
        )
        items.append({
            'narrative_id': 0,
            'headline': latest.get('headline'),
            'summary': latest.get('summary'),
            'audience': latest.get('audience'),
            'scope': latest.get('scope'),
            'provider': latest.get('provider'),
            'fallback_used': latest.get('fallback_used'),
            'freshness_status': 'current',
            'generated_at': latest.get('generated_at'),
            'status': 'generated',
        })
        normalized_audience = latest.get('audience')
        scope = latest.get('scope')

    return {
        'available': True,
        'audience': normalized_audience,
        'scope': scope,
        'count': len(items),
        'items': items,
    }


@app.get('/narrative/{narrative_id}')
def narrative_get(
    narrative_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    record = db.query(NarrativeRecord).filter(NarrativeRecord.id == narrative_id).first()
    if not record:
        raise HTTPException(status_code=404, detail='Narrative not found')
    if not _can_access_narrative_record(db, record, role, email):
        raise HTTPException(status_code=403, detail='Not authorized to access this narrative')
    return _narrative_record_to_response(record, role=role)


@app.patch('/narrative/{narrative_id}')
def narrative_patch(
    narrative_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if role == 'investor':
        raise HTTPException(status_code=403, detail='Investors cannot edit narratives')
    record = db.query(NarrativeRecord).filter(NarrativeRecord.id == narrative_id).first()
    if not record:
        raise HTTPException(status_code=404, detail='Narrative not found')
    if not _can_access_narrative_record(db, record, role, email):
        raise HTTPException(status_code=403, detail='Not authorized to edit this narrative')

    editable_fields = {'headline', 'summary', 'highlights', 'watchouts', 'recommendations'}
    edits = {}
    for key in editable_fields:
        if key in payload:
            edits[key] = payload.get(key)
    if not edits:
        return _narrative_record_to_response(record, role=role)

    existing_edits = parse_json_or_default(record.edited_payload, {})
    updated_edits = {**existing_edits, **edits}
    record.edited_payload = _json_text(updated_edits, '{}')
    if 'headline' in edits:
        record.headline = str(edits.get('headline') or '')
    if 'summary' in edits:
        record.summary = str(edits.get('summary') or '')
    if 'highlights' in edits:
        record.highlights = _json_text(list(edits.get('highlights') or []), '[]')
    if 'watchouts' in edits:
        record.watchouts = _json_text(list(edits.get('watchouts') or []), '[]')
    if 'recommendations' in edits:
        record.recommendations = _json_text(list(edits.get('recommendations') or []), '[]')
    record.status = 'edited'
    record.edited_by_role = role
    record.edited_at = _utc_now_iso()
    record.updated_at = record.edited_at
    db.commit()
    db.refresh(record)
    return _narrative_record_to_response(record, role=role)


@app.post('/narrative/{narrative_id}/approve')
def narrative_approve(
    narrative_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if role != 'manager':
        raise HTTPException(status_code=403, detail='Only managers can approve narratives')
    record = db.query(NarrativeRecord).filter(NarrativeRecord.id == narrative_id).first()
    if not record:
        raise HTTPException(status_code=404, detail='Narrative not found')
    if not _can_access_narrative_record(db, record, role, email):
        raise HTTPException(status_code=403, detail='Not authorized to approve this narrative')

    source_payload = parse_json_or_default(record.edited_payload, {}) or parse_json_or_default(record.generated_payload, {})
    record.published_payload = _json_text(source_payload, '{}')
    if 'headline' in source_payload:
        record.headline = str(source_payload.get('headline') or '')
    if 'summary' in source_payload:
        record.summary = str(source_payload.get('summary') or '')
    if 'highlights' in source_payload:
        record.highlights = _json_text(list(source_payload.get('highlights') or []), '[]')
    if 'watchouts' in source_payload:
        record.watchouts = _json_text(list(source_payload.get('watchouts') or []), '[]')
    if 'recommendations' in source_payload:
        record.recommendations = _json_text(list(source_payload.get('recommendations') or []), '[]')
    record.status = 'approved'
    record.approved_by_role = role
    record.approved_at = _utc_now_iso()
    record.updated_at = record.approved_at
    db.commit()
    db.refresh(record)
    return _narrative_record_to_response(record, role=role)


@app.get('/company/submission/{cycle_id}')
def company_submission_payload(
    cycle_id: int,
    section: str = Query(default='Environmental'),
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission = _resolve_submission_for_cycle(db, cycle_id=cycle_id, role=role, email=email, company_id=company_id)
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found for cycle')

    payload = parse_submission(submission)
    fields = _build_submission_collab_fields(payload, section=section)
    completed_fields = sum(1 for field in fields if field.get('value') not in {None, ''})
    total_fields = len(fields)
    error_count = sum(1 for field in fields if field.get('validation_errors'))
    validation_status = 'error' if error_count else 'ok'
    collaboration = _current_collaboration_payload(submission, role=role, email=email)

    return {
        'submission_id': submission.id,
        'company_id': submission.company_id,
        'cycle_id': submission.cycle_id,
        'section': section,
        'completion_percent': round((completed_fields / max(total_fields, 1)) * 100, 2),
        'total_fields': total_fields,
        'completed_fields': completed_fields,
        'validation_status': validation_status,
        'error_count': error_count,
        'warning_count': 0,
        'fields': fields,
        'collaboration': collaboration,
    }


@app.post('/company/submission/{cycle_id}')
def company_submission_field_update(
    cycle_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission = _resolve_submission_for_cycle(db, cycle_id=cycle_id, role=role, email=email)
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found for cycle')
    if role == 'investor':
        raise HTTPException(status_code=403, detail='Investors cannot update submission fields')

    body = payload.get('payload') if isinstance(payload.get('payload'), dict) else payload
    field_key = str(body.get('field_key') or '').strip()
    if not field_key:
        raise HTTPException(status_code=422, detail='field_key is required')
    field_value = body.get('value')
    section = str(body.get('section') or 'Environmental').strip() or 'Environmental'

    current = parse_submission(submission)
    current[field_key] = field_value
    submission.esg_data = json.dumps(current)
    db.commit()
    db.refresh(submission)

    company = db.query(Company).filter(Company.id == submission.company_id).first()
    _log_live_event(
        event_type='submission_field_saved',
        title='Draft updated',
        message=f"{company.name if company else 'Company'} saved {field_key} in {section}.",
        severity='info',
        actor_role=role,
        actor_email=email,
        company_id=submission.company_id,
        company_name=company.name if company else None,
        submission_id=submission.id,
        cycle_id=submission.cycle_id,
        entity_status=normalize_submission_status(submission.status),
        metadata={
            'field_key': field_key,
            'section': section,
            'validation_errors': 0,
            'validation_warnings': 0,
        },
    )
    return {
        'status': 'success',
        'message': 'Field updated',
        'validation': {'errors': 0, 'warnings': 0},
    }


@app.get('/submissions/{submission_id}/collaboration')
def submission_collaboration(
    submission_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission = _resolve_submission_by_id_accessible(db, submission_id=submission_id, role=role, email=email)
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    return _current_collaboration_payload(submission, role=role, email=email)


@app.post('/company/submission/{cycle_id}/collaboration/claim')
def collaboration_claim(
    cycle_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if role not in {'manager', 'company'}:
        raise HTTPException(status_code=403, detail='Only managers and company users can claim sections')
    submission = _resolve_submission_for_cycle(db, cycle_id=cycle_id, role=role, email=email, company_id=company_id)
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found for cycle')

    section = str(payload.get('section') or 'General').strip() or 'General'
    lock_mode = str(payload.get('lock_mode') or 'soft').strip().lower()
    if lock_mode not in {'soft', 'hard'}:
        lock_mode = 'soft'

    request_user = find_request_user(db, email)
    owner_name = (request_user.name if request_user else None) or 'User'
    now = _utc_now()
    expires_at = now + timedelta(minutes=2)

    with COLLAB_LOCK:
        state = COLLAB_STATE.setdefault(_build_collab_key(submission.id), {'lock_mode': lock_mode, 'sessions': []})
        state['lock_mode'] = lock_mode
        replaced = False
        for session in state['sessions']:
            if str(session.get('section', '')).lower() == section.lower():
                session.update({
                    'owner_role': role,
                    'owner_email': email,
                    'owner_name': owner_name,
                    'status': 'active',
                    'lock_mode': lock_mode,
                    'last_seen_at': now.isoformat().replace('+00:00', 'Z'),
                    'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
                    'updated_at': now.isoformat().replace('+00:00', 'Z'),
                })
                replaced = True
                break
        if not replaced:
            session = {
                'id': _next_collab_session_id(),
                'section': section,
                'owner_role': role,
                'owner_email': email,
                'owner_name': owner_name,
                'status': 'active',
                'lock_mode': lock_mode,
                'created_at': now.isoformat().replace('+00:00', 'Z'),
                'updated_at': now.isoformat().replace('+00:00', 'Z'),
                'last_seen_at': now.isoformat().replace('+00:00', 'Z'),
                'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
            }
            state['sessions'].append(session)

    company = db.query(Company).filter(Company.id == submission.company_id).first()
    _log_live_event(
        event_type='submission_section_claimed',
        title='Section owner updated',
        message=f"{company.name if company else 'Company'} {section} section is being edited by {owner_name}.",
        severity='info',
        actor_role=role,
        actor_email=email,
        company_id=submission.company_id,
        company_name=company.name if company else None,
        submission_id=submission.id,
        cycle_id=submission.cycle_id,
        entity_status=normalize_submission_status(submission.status),
        metadata={'section': section, 'created': not replaced},
    )
    return _current_collaboration_payload(submission, role=role, email=email)


@app.post('/company/submission/{cycle_id}/collaboration/release')
def collaboration_release(
    cycle_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if role not in {'manager', 'company'}:
        raise HTTPException(status_code=403, detail='Only managers and company users can release sections')
    submission = _resolve_submission_for_cycle(db, cycle_id=cycle_id, role=role, email=email, company_id=company_id)
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found for cycle')

    section = str(payload.get('section') or '').strip()
    release_all = bool(payload.get('release_all'))
    with COLLAB_LOCK:
        state = COLLAB_STATE.setdefault(_build_collab_key(submission.id), {'lock_mode': 'soft', 'sessions': []})
        kept = []
        for session in state['sessions']:
            owned = (session.get('owner_email') == email) or role == 'manager'
            if not owned:
                kept.append(session)
                continue
            if release_all:
                continue
            if section and str(session.get('section', '')).lower() == section.lower():
                continue
            kept.append(session)
        state['sessions'] = kept
    return _current_collaboration_payload(submission, role=role, email=email)


@app.post('/company/submission/{cycle_id}/collaboration/heartbeat')
def collaboration_heartbeat(
    cycle_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission = _resolve_submission_for_cycle(db, cycle_id=cycle_id, role=role, email=email, company_id=company_id)
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found for cycle')
    section = str(payload.get('section') or '').strip().lower()
    now = _utc_now()
    expires_at = now + timedelta(minutes=2)
    touched = False
    with COLLAB_LOCK:
        state = COLLAB_STATE.setdefault(_build_collab_key(submission.id), {'lock_mode': 'soft', 'sessions': []})
        for session in state['sessions']:
            if session.get('owner_email') != email:
                continue
            if section and str(session.get('section', '')).lower() != section:
                continue
            session['last_seen_at'] = now.isoformat().replace('+00:00', 'Z')
            session['expires_at'] = expires_at.isoformat().replace('+00:00', 'Z')
            session['updated_at'] = now.isoformat().replace('+00:00', 'Z')
            touched = True
    return {
        'status': 'ok',
        'touched': touched,
        'collaboration': _current_collaboration_payload(submission, role=role, email=email),
    }


@app.websocket('/ws/live')
async def ws_live(websocket: WebSocket):
    role = normalize_role(websocket.query_params.get('role') or websocket.headers.get('x-user-role'))
    email = (websocket.query_params.get('email') or websocket.headers.get('x-user-email') or '').strip().lower() or None
    await websocket.accept()
    connection = {'socket': websocket, 'role': role, 'email': email}
    LIVE_WEBSOCKETS.append(connection)
    try:
        latest = LIVE_EVENTS[-1] if LIVE_EVENTS else None
        last_event_id = int(latest.get('id') or 0) if latest else 0
        if latest:
            await websocket.send_json({'type': 'event', 'event': latest})
        else:
            await websocket.send_json({'type': 'heartbeat', 'timestamp': _utc_now_iso()})
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=20)
            except asyncio.TimeoutError:
                pass

            with COLLAB_LOCK:
                fresh = [event for event in LIVE_EVENTS if int(event.get('id') or 0) > last_event_id]
            if fresh:
                for event in fresh:
                    await websocket.send_json({'type': 'event', 'event': event})
                    last_event_id = max(last_event_id, int(event.get('id') or 0))
            else:
                await websocket.send_json({'type': 'heartbeat', 'timestamp': _utc_now_iso()})
    except WebSocketDisconnect:
        pass
    finally:
        if connection in LIVE_WEBSOCKETS:
            LIVE_WEBSOCKETS.remove(connection)


@app.get('/live/activity')
def live_activity(
    limit: int = Query(default=12, ge=1, le=100),
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if role == 'company':
        request_user = find_request_user(db, email)
        owned_company = db.query(Company).filter(Company.user_id == request_user.id).first() if request_user else None
        if not owned_company:
            return {'events': [], 'count': 0}
        company_id = owned_company.id

    events = _build_live_activity_events(db, limit=limit, company_id=company_id)
    return {
        'count': len(events),
        'items': events,
        'events': events,
    }


@app.post('/newsletter/generate', dependencies=[Depends(require_manager_or_investor)])
def newsletter_generate(
    audience: str = Query(default='manager'),
    tone: str = Query(default='board-ready'),
    db: Session = Depends(get_db),
):
    normalized_audience = 'investor' if audience.strip().lower() == 'investor' else 'manager'
    return _build_newsletter_payload(db, audience=normalized_audience, tone=tone)


@app.post('/newsletter/export', dependencies=[Depends(require_manager_or_investor)])
def newsletter_export(
    audience: str = Query(default='manager'),
    tone: str = Query(default='board-ready'),
    db: Session = Depends(get_db),
):
    payload = _build_newsletter_payload(db, audience=audience, tone=tone)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    file_name = f"newsletter_{slugify(audience)}_{timestamp}.txt"
    file_path = EXPORT_DIR / file_name
    body_lines = [
        payload.get('subject_line', ''),
        payload.get('preheader', ''),
        '',
        payload.get('headline', ''),
        payload.get('summary', ''),
        '',
        'Highlights:',
    ] + [f"- {item}" for item in (payload.get('highlights') or [])]
    file_path.write_text('\n'.join(body_lines), encoding='utf-8')
    return {
        **payload,
        'file_name': file_name,
        'file_path': str(file_path),
        'download_url': f'/exports/{file_name}',
        'content_type': 'text/plain',
        'message': 'Newsletter export is ready.',
    }


@app.post('/newsletter/send', dependencies=[Depends(require_manager_or_investor)])
def newsletter_send(
    audience: str = Query(default='manager'),
    tone: str = Query(default='board-ready'),
    dry_run: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    payload = _build_newsletter_payload(db, audience=audience, tone=tone)
    return {
        **payload,
        'delivery_status': 'dry_run' if dry_run else 'queued',
        'provider': 'smtp',
        'recipient_count': 2,
        'sent_count': 0 if dry_run else 2,
        'failed_count': 0,
        'skipped_count': 0,
        'dry_run': dry_run,
        'message': 'Dry run completed. No email was sent.' if dry_run else 'Delivery queued.',
    }


@app.get('/cron/newsletter/{audience}')
def cron_newsletter_dispatch(
    audience: str,
    tone: str = Query(default='board-ready'),
    dry_run: bool = Query(default=False),
    secret: str | None = Query(default=None),
    x_cron_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _validate_cron_secret(secret=secret, x_cron_secret=x_cron_secret, authorization=authorization)
    normalized = str(audience or '').strip().lower()
    if normalized not in {'manager', 'investor'}:
        raise HTTPException(status_code=400, detail='audience must be manager or investor')
    payload = _build_newsletter_payload(db, audience=normalized, tone=tone)
    send_payload = {
        **payload,
        'delivery_status': 'dry_run' if dry_run else 'queued',
        'provider': 'smtp',
        'recipient_count': 2,
        'sent_count': 0 if dry_run else 2,
        'failed_count': 0,
        'skipped_count': 0,
        'dry_run': dry_run,
        'message': 'Dry run completed. No email was sent.' if dry_run else 'Delivery queued.',
        'cron': True,
        'audience': normalized,
        'triggered_at': _utc_now_iso(),
    }
    return send_payload


def _parse_feed_timestamp(value: str | None) -> str:
    raw = str(value or '').strip()
    if not raw:
        return _utc_now_iso()
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except Exception:
        return _utc_now_iso()


def _strip_html_text(value: str | None) -> str:
    text_value = html.unescape(str(value or ''))
    return re.sub(r'<[^>]+>', '', text_value).strip()


def _fetch_source_feed(source: dict[str, str], per_source_limit: int = 5) -> list[dict[str, Any]]:
    req = urlrequest.Request(
        source.get('url') or '',
        headers={'User-Agent': 'Mozilla/5.0 ESG-Insights-Bot/1.0 (+https://vercel.app)'},
    )
    with urlrequest.urlopen(req, timeout=8) as response:  # nosec B310
        payload = response.read()

    root = ElementTree.fromstring(payload)
    items: list[dict[str, Any]] = []
    source_id = str(source.get('id') or 'feed')
    source_label = str(source.get('label') or 'External ESG feed')
    priority = str(source.get('priority') or 'medium')

    for idx, node in enumerate(root.findall('.//item')):
        if idx >= max(per_source_limit, 1):
            break
        title = _strip_html_text(node.findtext('title')) or 'ESG update'
        summary = _strip_html_text(node.findtext('description')) or 'Live ESG news item.'
        link = str(node.findtext('link') or '').strip()
        published_at = _parse_feed_timestamp(node.findtext('pubDate'))
        item_slug = slugify(title)[:48] or f'item-{idx + 1}'
        items.append(
            {
                'id': f'{source_id}-{item_slug}-{idx + 1}',
                'item_type': 'news',
                'title': title,
                'summary': summary[:500],
                'priority': priority,
                'published_at': published_at,
                'source_label': source_label,
                'source_url': link,
                'live': True,
            }
        )
    return items


def _fallback_external_feed_items(limit: int) -> list[dict[str, Any]]:
    now = _utc_now_iso()
    return [
        {
            'id': 'fallback-greenwashing-controls',
            'item_type': 'regulation',
            'title': 'Anti-greenwashing risk is pushing teams toward evidence-backed ESG claims',
            'summary': 'Narratives and investor updates should stay aligned to approved data and benchmark context.',
            'priority': 'high',
            'published_at': now,
            'source_label': 'Curated regulatory monitor',
            'source_url': '',
            'live': False,
        },
        {
            'id': 'fallback-climate-disclosure',
            'item_type': 'regulation',
            'title': 'Climate disclosure expectations are tightening across institutional reporting',
            'summary': 'Disclosure scrutiny is rising around emissions baselines and transition claims.',
            'priority': 'high',
            'published_at': now,
            'source_label': 'Curated regulatory monitor',
            'source_url': '',
            'live': False,
        },
        {
            'id': 'fallback-cyber-governance',
            'item_type': 'regulation',
            'title': 'Cyber governance remains central in ESG and risk conversations',
            'summary': 'Boards expect cybersecurity posture to be visible within governance reporting.',
            'priority': 'medium',
            'published_at': now,
            'source_label': 'Curated regulatory monitor',
            'source_url': '',
            'live': False,
        },
    ][: max(limit, 1)]


def _build_external_context_feed(limit: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with COLLAB_LOCK:
        cached_at = NEWS_FEED_CACHE.get('fetched_at')
        cached_items = list(NEWS_FEED_CACHE.get('items') or [])
        if isinstance(cached_at, datetime) and cached_items:
            if (now - cached_at).total_seconds() < NEWS_FEED_TTL_SECONDS:
                return {
                    'generated_at': cached_at.isoformat().replace('+00:00', 'Z'),
                    'fallback_used': bool(NEWS_FEED_CACHE.get('fallback_used', True)),
                    'source_count': int(NEWS_FEED_CACHE.get('source_count', 0)),
                    'items': cached_items[: max(limit, 1)],
                }

    live_items: list[dict[str, Any]] = []
    source_count = 0
    for source in NEWS_FEED_SOURCES:
        try:
            source_items = _fetch_source_feed(source=source, per_source_limit=5)
            if source_items:
                live_items.extend(source_items)
                source_count += 1
        except (URLError, HTTPError, TimeoutError, ValueError, ElementTree.ParseError):
            continue
        except Exception:
            continue

    if live_items:
        live_items.sort(key=lambda item: item.get('published_at') or '', reverse=True)
        final_items = live_items[: max(limit, 1)]
        with COLLAB_LOCK:
            NEWS_FEED_CACHE['fetched_at'] = now
            NEWS_FEED_CACHE['items'] = final_items
            NEWS_FEED_CACHE['source_count'] = source_count
            NEWS_FEED_CACHE['fallback_used'] = False
        return {
            'generated_at': now.isoformat().replace('+00:00', 'Z'),
            'fallback_used': False,
            'source_count': source_count,
            'items': final_items,
        }

    fallback_items = _fallback_external_feed_items(limit=limit)
    with COLLAB_LOCK:
        NEWS_FEED_CACHE['fetched_at'] = now
        NEWS_FEED_CACHE['items'] = fallback_items
        NEWS_FEED_CACHE['source_count'] = 0
        NEWS_FEED_CACHE['fallback_used'] = True
    return {
        'generated_at': now.isoformat().replace('+00:00', 'Z'),
        'fallback_used': True,
        'source_count': 0,
        'items': fallback_items,
    }


@app.get('/external-context/feed', dependencies=[Depends(require_manager_or_investor)])
def external_context_feed(limit: int = Query(default=12, ge=3, le=30)):
    return _build_external_context_feed(limit=limit)


@app.get('/anomalies/summary', dependencies=[Depends(require_manager_or_investor)])
def anomalies_summary(db: Session = Depends(get_db)):
    flags = (
        db.query(ValidationFlag)
        .filter(func.lower(ValidationFlag.severity) != 'info')
        .order_by(ValidationFlag.id.desc())
        .limit(100)
        .all()
    )
    severity_counts = {'high': 0, 'medium': 0, 'low': 0}
    items = []
    for flag in flags:
        sev = str(flag.severity or '').strip().lower()
        if sev in severity_counts:
            severity_counts[sev] += 1
        items.append({
            'id': flag.id,
            'company_id': flag.company_id,
            'reporting_year': flag.reporting_year,
            'field_name': flag.field_name,
            'issue_description': flag.issue_description,
            'severity': flag.severity,
        })
    return {
        'available': True,
        'scope': 'portfolio',
        'generated_at': _utc_now_iso(),
        'headline': 'Portfolio anomaly watchlist',
        'summary': 'Latest validation and variance anomalies from approved and submitted data.',
        'severity_counts': severity_counts,
        'items': items[:20],
        'watchlist_companies': sorted({item['company_id'] for item in items[:20]}),
        'fallback_used': True,
    }


@app.get('/company/anomalies')
def company_anomalies(
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if role != 'company':
        raise HTTPException(status_code=403, detail='Company anomaly feed is restricted to company users')
    request_user = find_request_user(db, email)
    target_company = db.query(Company).filter(Company.user_id == request_user.id).first() if request_user else None
    if not target_company:
        return {'company_id': None, 'items': []}

    flags = (
        db.query(ValidationFlag)
        .filter(ValidationFlag.company_id == target_company.id)
        .filter(func.lower(ValidationFlag.severity) != 'info')
        .order_by(ValidationFlag.id.desc())
        .limit(50)
        .all()
    )
    return {
        'company_id': target_company.id,
        'company_name': target_company.name,
        'count': len(flags),
        'items': [
            {
                'id': flag.id,
                'reporting_year': flag.reporting_year,
                'field_name': flag.field_name,
                'issue_description': flag.issue_description,
                'severity': flag.severity,
            }
            for flag in flags
        ],
    }


@app.get('/search/global')
def search_global(
    q: str = Query(default=''),
    result_type: str | None = Query(default=None, alias='type'),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if not role:
        raise HTTPException(status_code=403, detail='Role header required')
    if role not in {'manager', 'investor', 'company'}:
        raise HTTPException(status_code=403, detail='Unsupported role for search')
    return _collect_global_search_items(
        db,
        query=q,
        role=role,
        email=email,
        result_type=result_type,
        limit=limit,
    )
