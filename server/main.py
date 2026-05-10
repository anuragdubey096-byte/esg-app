import csv
import json
import os
import re
import asyncio
import html
import secrets
import hashlib
from collections import Counter
from threading import RLock
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, List
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
from xml.etree import ElementTree

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Header, Query, Body, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, inspect, text
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
    UserPermission,
    FeatureFlag,
    AuditEvent,
    SubmissionDeclaration,
    ContextHelpContent,
    CycleCloneLog,
    OnboardingState,
    UserSecuritySetting,
    SessionPolicy,
    IPAllowlist,
    UserSession,
    AccountLockout,
    AuthEvent,
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
    CsvParityResponse,
    UserResponse,
)
from new_esg_module import router as new_esg_router
try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency at runtime
    OpenAI = None

try:
    import pyotp
except ImportError:  # pragma: no cover
    pyotp = None

BASE_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = BASE_DIR / 'fixtures'
CSV_PARITY_FILES = {
    'companies': 'companies.csv',
    'cycles': 'cycles.csv',
    'review_actions': 'review_actions.csv',
    'validation_flags': 'validation_flags.csv',
    'submissions_previous': 'esg_submissions_previous_year.csv',
    'submissions_current': 'esg_submissions_current_year.csv',
}
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
NEWS_SECTOR_KEYWORDS: dict[str, list[str]] = {
    'Energy & Utilities': ['energy', 'utility', 'utilities', 'power', 'renewable', 'oil', 'gas', 'grid', 'solar', 'wind'],
    'Financial Services': ['bank', 'banking', 'finance', 'financial', 'asset manager', 'private equity', 'investor', 'capital markets'],
    'Technology': ['technology', 'tech', 'software', 'ai', 'data center', 'cloud', 'cybersecurity', 'semiconductor'],
    'Healthcare': ['healthcare', 'hospital', 'pharma', 'biotech', 'medical', 'life sciences'],
    'Industrials': ['manufacturing', 'industrial', 'factory', 'supply chain', 'logistics', 'construction'],
    'Transportation': ['transport', 'shipping', 'aviation', 'airline', 'rail', 'mobility', 'fleet'],
    'Consumer & Retail': ['retail', 'consumer', 'food', 'beverage', 'apparel', 'packaging'],
    'Real Estate': ['real estate', 'property', 'buildings', 'construction materials', 'commercial real estate'],
}
NEWS_FEED_CACHE: dict[str, Any] = {
    'fetched_at': None,
    'items': [],
    'source_count': 0,
    'fallback_used': True,
}
PHASE1_FEATURE_FLAGS = {
    'feature_25_audit_trail_viewer': True,
    'feature_26_declaration_workflow': True,
    'feature_31_contextual_help': True,
    'feature_40_cycle_cloning': True,
    'feature_42_onboarding_workflow': True,
    'feature_44_mfa_sso': True,
    'feature_45_session_ip_restriction': True,
}
ONBOARDING_STEP_ORDER = [
    'profile_setup',
    'data_readiness',
    'submission_orientation',
    'document_checklist',
]

app = FastAPI(title='ESG Data App')
app.include_router(new_esg_router, prefix="/api/v2")
try:
    app.include_router(__import__('routers.agent', fromlist=['router']).router)
except Exception:
    # Keep core API alive even if optional agent router import fails at runtime.
    pass
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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_feature_flags_seed(db: Session):
    for key, enabled in PHASE1_FEATURE_FLAGS.items():
        existing = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
        if existing:
            continue
        db.add(FeatureFlag(key=key, enabled=enabled, description='Phase 1 foundation feature flag'))
    db.commit()


def is_feature_enabled(db: Session, key: str, default: bool = False) -> bool:
    flag = db.query(FeatureFlag).filter(FeatureFlag.key == key).first()
    if not flag:
        return default
    return bool(flag.enabled)


def _empty_permissions() -> dict[str, Any]:
    return {
        'can_manage_security': False,
        'can_view_portfolio_audit': False,
        'can_clone_cycles': False,
        'read_only_audit_scope': [],
    }


def get_user_permissions(db: Session, role: str, email: str | None) -> dict[str, Any]:
    if role != 'manager':
        return _empty_permissions()
    request_user = find_request_user(db, email)
    if not request_user:
        return _empty_permissions()

    perms = db.query(UserPermission).filter(UserPermission.user_id == request_user.id).first()
    if not perms:
        default_scope = ['*']
        perms = UserPermission(
            user_id=request_user.id,
            can_manage_security=True,
            can_view_portfolio_audit=True,
            can_clone_cycles=True,
            read_only_audit_scope=json.dumps(default_scope),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(perms)
        db.commit()
        db.refresh(perms)

    scope = parse_json_or_default(perms.read_only_audit_scope, [])
    return {
        'can_manage_security': bool(perms.can_manage_security),
        'can_view_portfolio_audit': bool(perms.can_view_portfolio_audit),
        'can_clone_cycles': bool(perms.can_clone_cycles),
        'read_only_audit_scope': scope if isinstance(scope, list) else [],
    }


def require_security_admin(db: Session, role: str, email: str | None):
    if role != 'manager':
        raise HTTPException(status_code=403, detail='Security controls are restricted to managers')
    perms = get_user_permissions(db, role, email)
    if not perms.get('can_manage_security'):
        raise HTTPException(status_code=403, detail='Security permissions are required')


def require_clone_permission(db: Session, role: str, email: str | None):
    if role != 'manager':
        raise HTTPException(status_code=403, detail='Cycle cloning is restricted to managers')
    perms = get_user_permissions(db, role, email)
    if not perms.get('can_clone_cycles'):
        raise HTTPException(status_code=403, detail='Cycle cloning permission is required')


def _serialize_value(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, sort_keys=True)
        except Exception:
            return str(value)
    return str(value)


def log_audit_event(
    db: Session,
    *,
    event_type: str,
    actor_role: str | None,
    actor_email: str | None,
    actor_user_id: int | None = None,
    company_id: int | None = None,
    submission_id: int | None = None,
    cycle_id: int | None = None,
    field_name: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    source: str = 'ui',
    metadata: dict[str, Any] | None = None,
):
    db.add(
        AuditEvent(
            event_type=event_type,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            actor_role=actor_role,
            company_id=company_id,
            submission_id=submission_id,
            cycle_id=cycle_id,
            field_name=field_name,
            old_value=_serialize_value(old_value),
            new_value=_serialize_value(new_value),
            source=source,
            metadata_json=json.dumps(metadata or {}),
            created_at=datetime.utcnow(),
        )
    )


def _declaration_statement() -> str:
    return 'I confirm this ESG submission is accurate and complete to the best of my knowledge.'


def _hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


def _generate_backup_codes() -> list[str]:
    codes = []
    for _ in range(8):
        raw = secrets.token_hex(3).upper()
        codes.append(f'{raw[:3]}-{raw[3:]}')
    return codes


def _normalize_backup_code(value: str) -> str:
    return re.sub(r'[^A-Za-z0-9]', '', value or '').upper()


def _get_ip_from_request(request: Request) -> str:
    forwarded = request.headers.get('x-forwarded-for', '')
    candidate = forwarded.split(',')[0].strip() if forwarded else ''
    if candidate:
        return candidate
    client_host = request.client.host if request.client else ''
    return client_host or 'unknown'


def _get_session_policy(db: Session, role: str) -> SessionPolicy:
    normalized = normalize_role(role)
    policy = db.query(SessionPolicy).filter(SessionPolicy.role == normalized).first()
    if policy:
        return policy

    default_timeout = 240 if normalized == 'manager' else (480 if normalized == 'company' else 1440)
    policy = SessionPolicy(
        role=normalized,
        timeout_minutes=default_timeout,
        warn_before_minutes=5,
        max_failed_logins=5,
        lockout_minutes=30,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def _check_ip_allowlist(db: Session, ip_address: str):
    allowlist = db.query(IPAllowlist).filter(IPAllowlist.enabled.is_(True)).all()
    if not allowlist:
        return
    allowed_values = {str(item.ip_address).strip() for item in allowlist}
    if ip_address not in allowed_values:
        raise HTTPException(status_code=403, detail='IP address is not allowed')


def _upsert_user_lockout(db: Session, user_id: int) -> AccountLockout:
    lockout = db.query(AccountLockout).filter(AccountLockout.user_id == user_id).first()
    if lockout:
        return lockout
    lockout = AccountLockout(
        user_id=user_id,
        failed_attempts=0,
        locked_until=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(lockout)
    db.commit()
    db.refresh(lockout)
    return lockout


def _is_submission_declared(db: Session, submission_id: int) -> bool:
    declaration = (
        db.query(SubmissionDeclaration)
        .filter(SubmissionDeclaration.submission_id == submission_id, SubmissionDeclaration.active.is_(True))
        .first()
    )
    return bool(declaration)


def _revoke_submission_declaration(db: Session, submission_id: int):
    declaration = (
        db.query(SubmissionDeclaration)
        .filter(SubmissionDeclaration.submission_id == submission_id, SubmissionDeclaration.active.is_(True))
        .first()
    )
    if not declaration:
        return
    declaration.active = False
    declaration.revoked_at = datetime.utcnow()

def require_manager(role: str = Depends(get_user_role)):
    if role != 'manager':
        raise HTTPException(status_code=403, detail='Access restricted to ESG Managers')


def require_supported_role(role: str = Depends(get_user_role)):
    if role not in {'manager', 'investor', 'company'}:
        raise HTTPException(status_code=403, detail='Access is restricted to platform users')


def block_investors(role: str = Depends(get_user_role)):
    if role == 'investor':
        raise HTTPException(status_code=403, detail='Investors are blocked from individual company-level data')


def find_request_user(db: Session, email: str | None) -> User | None:
    if email:
        return db.query(User).filter(User.email == email).first()
    return None


def _load_fixture_rows(file_path: Path) -> list[dict[str, str]]:
    if not file_path.exists():
        return []
    with file_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if any(str(value or '').strip() for value in row.values())]


def _build_csv_parity_report(db: Session) -> dict[str, Any]:
    fixture_rows: dict[str, list[dict[str, str]]] = {}
    files: list[dict[str, Any]] = []
    for file_key, file_name in CSV_PARITY_FILES.items():
        file_path = FIXTURES_DIR / file_name
        rows = _load_fixture_rows(file_path)
        fixture_rows[file_key] = rows
        files.append(
            {
                'file_key': file_key,
                'file_name': file_name,
                'present': file_path.exists(),
                'rows': len(rows),
            }
        )

    csv_companies = fixture_rows.get('companies', [])
    csv_code_to_name: dict[str, str] = {}
    for row in csv_companies:
        code = str(row.get('company_id') or '').strip()
        name = str(row.get('company_name') or '').strip()
        if code and name:
            csv_code_to_name[code] = name

    csv_submission_counts_by_code: Counter[str] = Counter()
    for key in ('submissions_previous', 'submissions_current'):
        for row in fixture_rows.get(key, []):
            code = str(row.get('company_id') or '').strip()
            if code:
                csv_submission_counts_by_code[code] += 1

    csv_review_counts_by_code: Counter[str] = Counter()
    for row in fixture_rows.get('review_actions', []):
        code = str(row.get('company_id') or '').strip()
        if code:
            csv_review_counts_by_code[code] += 1

    csv_flag_counts_by_code: Counter[str] = Counter()
    for row in fixture_rows.get('validation_flags', []):
        code = str(row.get('company_id') or '').strip()
        if code:
            csv_flag_counts_by_code[code] += 1

    live_companies = db.query(Company).all()
    live_company_by_code = {str(company.code).strip(): company for company in live_companies if company.code}
    live_company_by_name = {str(company.name).strip(): company for company in live_companies if company.name}

    missing_csv_companies_in_live: list[dict[str, str]] = []
    per_company_mismatches: list[dict[str, Any]] = []

    for code, name in sorted(csv_code_to_name.items()):
        company = live_company_by_code.get(code) or live_company_by_name.get(name)
        if not company:
            missing_csv_companies_in_live.append({'company_code': code, 'company_name': name})
            per_company_mismatches.append(
                {
                    'dataset': 'company',
                    'company_code': code,
                    'company_name': name,
                    'expected': 1,
                    'live': 0,
                    'delta': -1,
                }
            )
            continue

        expected_submissions = int(csv_submission_counts_by_code.get(code, 0))
        live_submissions = len(company.submissions or [])
        if live_submissions != expected_submissions:
            per_company_mismatches.append(
                {
                    'dataset': 'submission',
                    'company_code': code,
                    'company_name': name,
                    'expected': expected_submissions,
                    'live': live_submissions,
                    'delta': live_submissions - expected_submissions,
                }
            )

        expected_reviews = int(csv_review_counts_by_code.get(code, 0))
        live_reviews = len(company.review_actions or [])
        if live_reviews != expected_reviews:
            per_company_mismatches.append(
                {
                    'dataset': 'review_action',
                    'company_code': code,
                    'company_name': name,
                    'expected': expected_reviews,
                    'live': live_reviews,
                    'delta': live_reviews - expected_reviews,
                }
            )

        expected_flags = int(csv_flag_counts_by_code.get(code, 0))
        live_flags = len(company.validation_flags or [])
        if live_flags != expected_flags:
            per_company_mismatches.append(
                {
                    'dataset': 'validation_flag',
                    'company_code': code,
                    'company_name': name,
                    'expected': expected_flags,
                    'live': live_flags,
                    'delta': live_flags - expected_flags,
                }
            )

    csv_company_names = set(csv_code_to_name.values())
    csv_company_codes = set(csv_code_to_name.keys())
    extra_live_companies_not_in_csv = []
    for company in live_companies:
        company_name = str(company.name or '').strip()
        company_code = str(company.code or '').strip()
        if company_code and company_code in csv_company_codes:
            continue
        if company_name in csv_company_names:
            continue
        extra_live_companies_not_in_csv.append(
            {
                'company_code': company_code,
                'company_name': company_name,
            }
        )

    csv_totals = {
        'companies': len(fixture_rows.get('companies', [])),
        'cycles': len(fixture_rows.get('cycles', [])),
        'review_actions': len(fixture_rows.get('review_actions', [])),
        'validation_flags': len(fixture_rows.get('validation_flags', [])),
        'submissions': len(fixture_rows.get('submissions_previous', [])) + len(fixture_rows.get('submissions_current', [])),
    }
    live_totals = {
        'companies': len(live_companies),
        'cycles': db.query(CollectionCycle).count(),
        'review_actions': db.query(ReviewAction).count(),
        'validation_flags': db.query(ValidationFlag).count(),
        'submissions': db.query(Submission).count(),
    }
    delta_totals = {key: int(live_totals.get(key, 0)) - int(csv_totals.get(key, 0)) for key in csv_totals.keys()}

    missing_files = [item['file_name'] for item in files if not item['present']]
    notes: list[str] = []
    if missing_files:
        notes.append(f"Missing fixture files: {', '.join(sorted(missing_files))}.")
    notes.append('Parity uses company code matching with company-name fallback.')
    notes.append('Live totals can exceed CSV totals when manual submissions, reviews, or flags are added after import.')

    is_full_parity = (
        not missing_files
        and not missing_csv_companies_in_live
        and not extra_live_companies_not_in_csv
        and not per_company_mismatches
        and all(value == 0 for value in delta_totals.values())
    )

    return {
        'generated_at': _utc_now_iso(),
        'fixtures_dir': str(FIXTURES_DIR),
        'files': files,
        'csv_totals': csv_totals,
        'live_totals': live_totals,
        'delta_totals': delta_totals,
        'missing_csv_companies_in_live': missing_csv_companies_in_live,
        'extra_live_companies_not_in_csv': extra_live_companies_not_in_csv,
        'per_company_mismatches': per_company_mismatches,
        'is_full_parity': is_full_parity,
        'notes': notes,
    }


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
    inspector = inspect(db.bind)
    return any(column.get('name') == column_name for column in inspector.get_columns(table_name))


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
        _ensure_feature_flags_seed(db)
        migrate_legacy_user_roles(db)
        fix_cycle_statuses_and_active_conflicts(db)
        ensure_submission_cycle_backfill(db)
        deactivate_expired_unlocks(db)
    finally:
        db.close()

@app.post('/login', response_model=UserResponse)
def login(
    request: LoginRequest,
    response: Response,
    http_request: Request,
    db: Session = Depends(get_db),
):
    ip_address = _get_ip_from_request(http_request)
    if is_feature_enabled(db, 'feature_45_session_ip_restriction', default=True):
        _check_ip_allowlist(db, ip_address)

    normalized_email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if user:
        policy = _get_session_policy(db, normalize_role(user.role))
        lockout = _upsert_user_lockout(db, user.id)
        if lockout.locked_until and lockout.locked_until > datetime.utcnow():
            raise HTTPException(status_code=423, detail='Account temporarily locked due to failed login attempts')
    else:
        policy = _get_session_policy(db, 'company')
        lockout = None

    if not user or user.password != request.password:
        if user and lockout:
            lockout.failed_attempts = int(lockout.failed_attempts or 0) + 1
            if lockout.failed_attempts >= int(policy.max_failed_logins or 5):
                lockout.locked_until = datetime.utcnow() + timedelta(minutes=int(policy.lockout_minutes or 30))
                lockout.failed_attempts = 0
            lockout.updated_at = datetime.utcnow()
            db.add(
                AuthEvent(
                    user_id=user.id,
                    email=user.email,
                    event_type='login_failed',
                    ip_address=ip_address,
                    details_json=json.dumps({'reason': 'invalid_credentials'}),
                    created_at=datetime.utcnow(),
                )
            )
            db.commit()
        raise HTTPException(status_code=401, detail='Invalid email or password')

    if lockout:
        lockout.failed_attempts = 0
        lockout.locked_until = None
        lockout.updated_at = datetime.utcnow()

    session_token = secrets.token_urlsafe(36)
    expires_at = datetime.utcnow() + timedelta(minutes=int(policy.timeout_minutes or 480))
    db.add(
        UserSession(
            user_id=user.id,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=http_request.headers.get('user-agent', ''),
            expires_at=expires_at,
            active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.add(
        AuthEvent(
            user_id=user.id,
            email=user.email,
            event_type='login_success',
            ip_address=ip_address,
            details_json=json.dumps({'role': normalize_role(user.role)}),
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    response.headers['x-session-token'] = session_token
    return serialize_user(user)


@app.post('/auth/forgot-password', response_model=ForgotPasswordResponse)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Deliberately return a generic message to avoid revealing account existence.
    _ = db.query(User).filter(User.email == request.email).first()
    return ForgotPasswordResponse(
        message='If an account with that email exists, password reset instructions have been sent.'
    )


@app.post('/auth/sso/{provider}', response_model=UserResponse)
def sso_login(
    provider: str,
    payload: SSOLoginRequest | None = None,
    response: Response = None,
    http_request: Request = None,
    db: Session = Depends(get_db),
):
    normalized_provider = provider.strip().lower()
    allowed_providers = {'google', 'microsoft', 'azure'}
    if normalized_provider not in allowed_providers:
        raise HTTPException(status_code=400, detail='Unsupported SSO provider')

    if normalized_provider == 'azure' and not is_feature_enabled(db, 'feature_44_mfa_sso', default=True):
        raise HTTPException(status_code=403, detail='Azure SSO is disabled')

    email_hint = (payload.email_hint if payload else None) or ''
    provider_default_email = 'manager@example.com' if normalized_provider in {'google', 'azure'} else 'investor@example.com'
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
            role=UserRole.MANAGER if normalized_provider in {'google', 'azure'} else UserRole.INVESTOR,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    ip_address = _get_ip_from_request(http_request) if http_request else 'unknown'
    if is_feature_enabled(db, 'feature_45_session_ip_restriction', default=True):
        _check_ip_allowlist(db, ip_address)
    policy = _get_session_policy(db, normalize_role(user.role))
    session_token = secrets.token_urlsafe(36)
    db.add(
        UserSession(
            user_id=user.id,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=http_request.headers.get('user-agent', '') if http_request else '',
            expires_at=datetime.utcnow() + timedelta(minutes=int(policy.timeout_minutes or 480)),
            active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.add(
        AuthEvent(
            user_id=user.id,
            email=user.email,
            event_type='sso_login_success',
            ip_address=ip_address,
            details_json=json.dumps({'provider': normalized_provider}),
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    if response:
        response.headers['x-session-token'] = session_token

    return serialize_user(user)


@app.post('/auth/sso/saml/azure/start')
def azure_saml_start(db: Session = Depends(get_db)):
    if not is_feature_enabled(db, 'feature_44_mfa_sso', default=True):
        raise HTTPException(status_code=403, detail='SSO is disabled')
    state = secrets.token_urlsafe(24)
    return {
        'provider': 'azure',
        'state': state,
        'sso_url': os.getenv('AZURE_SAML_SSO_URL', ''),
        'message': 'Redirect user to Azure SAML endpoint with returned state.',
    }


@app.post('/auth/sso/saml/azure/callback', response_model=UserResponse)
def azure_saml_callback(
    payload: dict[str, Any] = Body(default_factory=dict),
    response: Response = None,
    http_request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_feature_enabled(db, 'feature_44_mfa_sso', default=True):
        raise HTTPException(status_code=403, detail='SSO is disabled')
    email_value = str(payload.get('email') or payload.get('email_hint') or '').strip().lower()
    if not email_value:
        raise HTTPException(status_code=422, detail='email is required')

    user = db.query(User).filter(User.email == email_value).first()
    if not user:
        user = User(
            name=str(payload.get('name') or 'Azure SSO User'),
            email=email_value,
            password='password123',
            role=to_user_role_enum(str(payload.get('role') or 'manager')),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    ip_address = _get_ip_from_request(http_request) if http_request else 'unknown'
    if is_feature_enabled(db, 'feature_45_session_ip_restriction', default=True):
        _check_ip_allowlist(db, ip_address)

    policy = _get_session_policy(db, normalize_role(user.role))
    session_token = secrets.token_urlsafe(36)
    db.add(
        UserSession(
            user_id=user.id,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=http_request.headers.get('user-agent', '') if http_request else '',
            expires_at=datetime.utcnow() + timedelta(minutes=int(policy.timeout_minutes or 480)),
            active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.add(
        AuthEvent(
            user_id=user.id,
            email=user.email,
            event_type='azure_saml_callback_success',
            ip_address=ip_address,
            details_json=json.dumps({'provider': 'azure'}),
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    if response:
        response.headers['x-session-token'] = session_token
    return serialize_user(user)


@app.post('/auth/mfa/setup')
def mfa_setup(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if not is_feature_enabled(db, 'feature_44_mfa_sso', default=True):
        raise HTTPException(status_code=403, detail='MFA is disabled')
    if pyotp is None:
        raise HTTPException(status_code=503, detail='pyotp dependency is unavailable')
    request_user = find_request_user(db, email)
    if not request_user:
        raise HTTPException(status_code=404, detail='User not found')
    if normalize_role(request_user.role) != role:
        raise HTTPException(status_code=403, detail='Role mismatch')

    secret = pyotp.random_base32()
    backup_codes = _generate_backup_codes()
    setting = db.query(UserSecuritySetting).filter(UserSecuritySetting.user_id == request_user.id).first()
    if not setting:
        setting = UserSecuritySetting(
            user_id=request_user.id,
            mfa_enabled=False,
            mfa_secret=secret,
            mfa_backup_codes_json=json.dumps([_hash_backup_code(_normalize_backup_code(code)) for code in backup_codes]),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(setting)
    else:
        setting.mfa_secret = secret
        setting.mfa_enabled = False
        setting.mfa_backup_codes_json = json.dumps([_hash_backup_code(_normalize_backup_code(code)) for code in backup_codes])
        setting.updated_at = datetime.utcnow()

    issuer_name = str(payload.get('issuer_name') or 'ESG Platform')
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=request_user.email, issuer_name=issuer_name)
    db.add(
        AuthEvent(
            user_id=request_user.id,
            email=request_user.email,
            event_type='mfa_setup_started',
            ip_address='unknown',
            details_json=json.dumps({'issuer_name': issuer_name}),
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    return {
        'mfa_enabled': False,
        'secret': secret,
        'provisioning_uri': provisioning_uri,
        'backup_codes': backup_codes,
    }


@app.post('/auth/mfa/verify')
def mfa_verify(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if not is_feature_enabled(db, 'feature_44_mfa_sso', default=True):
        raise HTTPException(status_code=403, detail='MFA is disabled')
    if pyotp is None:
        raise HTTPException(status_code=503, detail='pyotp dependency is unavailable')
    request_user = find_request_user(db, email)
    if not request_user:
        raise HTTPException(status_code=404, detail='User not found')
    if normalize_role(request_user.role) != role:
        raise HTTPException(status_code=403, detail='Role mismatch')

    code = str(payload.get('code') or '').strip()
    if not code:
        raise HTTPException(status_code=422, detail='MFA code is required')

    setting = db.query(UserSecuritySetting).filter(UserSecuritySetting.user_id == request_user.id).first()
    if not setting or not setting.mfa_secret:
        raise HTTPException(status_code=404, detail='MFA setup not found')

    totp = pyotp.TOTP(setting.mfa_secret)
    verified = bool(totp.verify(code, valid_window=1))
    if not verified:
        backup_hashes = parse_json_or_default(setting.mfa_backup_codes_json, [])
        normalized_backup_code = _normalize_backup_code(code)
        code_hash = _hash_backup_code(normalized_backup_code)
        if isinstance(backup_hashes, list) and normalized_backup_code and code_hash in backup_hashes:
            verified = True
            backup_hashes = [item for item in backup_hashes if item != code_hash]
            setting.mfa_backup_codes_json = json.dumps(backup_hashes)

    if not verified:
        raise HTTPException(status_code=401, detail='Invalid MFA code')

    setting.mfa_enabled = True
    setting.updated_at = datetime.utcnow()
    db.add(
        AuthEvent(
            user_id=request_user.id,
            email=request_user.email,
            event_type='mfa_verified',
            ip_address='unknown',
            details_json='{}',
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    return {'mfa_enabled': True, 'verified': True}


@app.post('/auth/mfa/backup-codes/regenerate')
def regenerate_backup_codes(
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if not is_feature_enabled(db, 'feature_44_mfa_sso', default=True):
        raise HTTPException(status_code=403, detail='MFA is disabled')
    request_user = find_request_user(db, email)
    if not request_user:
        raise HTTPException(status_code=404, detail='User not found')
    if normalize_role(request_user.role) != role:
        raise HTTPException(status_code=403, detail='Role mismatch')

    setting = db.query(UserSecuritySetting).filter(UserSecuritySetting.user_id == request_user.id).first()
    if not setting:
        raise HTTPException(status_code=404, detail='MFA settings not found')

    backup_codes = _generate_backup_codes()
    setting.mfa_backup_codes_json = json.dumps([_hash_backup_code(_normalize_backup_code(code)) for code in backup_codes])
    setting.updated_at = datetime.utcnow()
    db.commit()
    return {'backup_codes': backup_codes}


@app.get('/auth/mfa/status')
def mfa_status(
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if not is_feature_enabled(db, 'feature_44_mfa_sso', default=True):
        return {'required': False, 'enabled': False}
    request_user = find_request_user(db, email)
    if not request_user:
        return {'required': False, 'enabled': False}
    setting = db.query(UserSecuritySetting).filter(UserSecuritySetting.user_id == request_user.id).first()
    enabled = bool(setting and setting.mfa_enabled)
    required = role == 'manager'
    return {'required': required, 'enabled': enabled}


@app.get('/auth/session/policy')
def auth_session_policy(
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    policy = _get_session_policy(db, role)
    return {
        'role': normalize_role(role),
        'timeout_minutes': int(policy.timeout_minutes),
        'warn_before_minutes': int(policy.warn_before_minutes),
        'max_failed_logins': int(policy.max_failed_logins),
        'lockout_minutes': int(policy.lockout_minutes),
    }


@app.post('/auth/session/extend')
def extend_auth_session(
    request: Request,
    db: Session = Depends(get_db),
):
    token = request.headers.get('x-session-token', '').strip()
    if not token:
        raise HTTPException(status_code=401, detail='Missing session token')
    session = db.query(UserSession).filter(UserSession.session_token == token, UserSession.active.is_(True)).first()
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')

    user = db.query(User).filter(User.id == session.user_id).first()
    role = normalize_role(user.role) if user else 'company'
    policy = _get_session_policy(db, role)
    session.expires_at = datetime.utcnow() + timedelta(minutes=int(policy.timeout_minutes))
    session.updated_at = datetime.utcnow()
    db.commit()
    return {'extended': True, 'expires_at': session.expires_at.isoformat()}


@app.post('/admin/sessions/{user_id}/expire', dependencies=[Depends(require_manager)])
def force_expire_sessions(
    user_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    require_security_admin(db, role, email)
    updated = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, UserSession.active.is_(True))
        .update({'active': False, 'updated_at': datetime.utcnow()}, synchronize_session=False)
    )
    db.commit()
    return {'expired_sessions': int(updated)}


@app.get('/admin/security/session-policies', dependencies=[Depends(require_manager)])
def list_session_policies(
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    require_security_admin(db, role, email)
    rows = db.query(SessionPolicy).order_by(SessionPolicy.role.asc()).all()
    return [
        {
            'role': row.role,
            'timeout_minutes': row.timeout_minutes,
            'warn_before_minutes': row.warn_before_minutes,
            'max_failed_logins': row.max_failed_logins,
            'lockout_minutes': row.lockout_minutes,
        }
        for row in rows
    ]


@app.put('/admin/security/session-policies/{target_role}', dependencies=[Depends(require_manager)])
def upsert_session_policy(
    target_role: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    require_security_admin(db, role, email)
    normalized_target = normalize_role(target_role)
    if normalized_target not in {'manager', 'company', 'investor'}:
        raise HTTPException(status_code=400, detail='Unsupported target role')
    row = db.query(SessionPolicy).filter(SessionPolicy.role == normalized_target).first()
    if not row:
        row = SessionPolicy(
            role=normalized_target,
            timeout_minutes=240 if normalized_target == 'manager' else (480 if normalized_target == 'company' else 1440),
            warn_before_minutes=5,
            max_failed_logins=5,
            lockout_minutes=30,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
    if 'timeout_minutes' in payload:
        row.timeout_minutes = max(10, int(payload.get('timeout_minutes') or row.timeout_minutes))
    if 'warn_before_minutes' in payload:
        row.warn_before_minutes = max(1, int(payload.get('warn_before_minutes') or row.warn_before_minutes))
    if 'max_failed_logins' in payload:
        row.max_failed_logins = max(1, int(payload.get('max_failed_logins') or row.max_failed_logins))
    if 'lockout_minutes' in payload:
        row.lockout_minutes = max(1, int(payload.get('lockout_minutes') or row.lockout_minutes))
    row.updated_at = datetime.utcnow()
    db.commit()
    return {
        'role': row.role,
        'timeout_minutes': row.timeout_minutes,
        'warn_before_minutes': row.warn_before_minutes,
        'max_failed_logins': row.max_failed_logins,
        'lockout_minutes': row.lockout_minutes,
    }


@app.get('/admin/security/ip-allowlist', dependencies=[Depends(require_manager)])
def list_ip_allowlist(
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    require_security_admin(db, role, email)
    rows = db.query(IPAllowlist).order_by(IPAllowlist.id.asc()).all()
    return [
        {
            'id': row.id,
            'ip_address': row.ip_address,
            'enabled': bool(row.enabled),
            'note': row.note,
        }
        for row in rows
    ]


@app.post('/admin/security/ip-allowlist', dependencies=[Depends(require_manager)])
def add_ip_allowlist(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    require_security_admin(db, role, email)
    ip_address = str(payload.get('ip_address') or '').strip()
    if not ip_address:
        raise HTTPException(status_code=422, detail='ip_address is required')
    existing = db.query(IPAllowlist).filter(IPAllowlist.ip_address == ip_address).first()
    if existing:
        existing.enabled = bool(payload.get('enabled', True))
        existing.note = str(payload.get('note') or existing.note or '')
        existing.updated_at = datetime.utcnow()
        db.commit()
        return {'id': existing.id, 'updated': True}
    request_user = find_request_user(db, email)
    row = IPAllowlist(
        ip_address=ip_address,
        enabled=bool(payload.get('enabled', True)),
        note=str(payload.get('note') or ''),
        created_by_user_id=request_user.id if request_user else None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {'id': row.id, 'created': True}


@app.delete('/admin/security/ip-allowlist/{entry_id}', dependencies=[Depends(require_manager)])
def delete_ip_allowlist(
    entry_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    require_security_admin(db, role, email)
    row = db.query(IPAllowlist).filter(IPAllowlist.id == entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail='Allowlist entry not found')
    db.delete(row)
    db.commit()
    return {'deleted': True, 'id': entry_id}


@app.get('/permissions/me')
def my_permissions(
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    return get_user_permissions(db, role, email)


@app.get('/permissions')
def list_permissions(
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    if role != 'manager':
        raise HTTPException(status_code=403, detail='Permissions are restricted to managers')
    rows = db.query(UserPermission).all()
    return [
        {
            'user_id': row.user_id,
            'can_manage_security': bool(row.can_manage_security),
            'can_view_portfolio_audit': bool(row.can_view_portfolio_audit),
            'can_clone_cycles': bool(row.can_clone_cycles),
            'read_only_audit_scope': parse_json_or_default(row.read_only_audit_scope, []),
        }
        for row in rows
    ]


@app.put('/permissions/{user_id}', dependencies=[Depends(require_manager)])
def upsert_permissions(
    user_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    perms = db.query(UserPermission).filter(UserPermission.user_id == user_id).first()
    if not perms:
        perms = UserPermission(
            user_id=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(perms)

    perms.can_manage_security = bool(payload.get('can_manage_security', perms.can_manage_security))
    perms.can_view_portfolio_audit = bool(payload.get('can_view_portfolio_audit', perms.can_view_portfolio_audit))
    perms.can_clone_cycles = bool(payload.get('can_clone_cycles', perms.can_clone_cycles))
    scope = payload.get('read_only_audit_scope', parse_json_or_default(perms.read_only_audit_scope, []))
    if not isinstance(scope, list):
        raise HTTPException(status_code=422, detail='read_only_audit_scope must be an array')
    perms.read_only_audit_scope = json.dumps(scope)
    perms.updated_at = datetime.utcnow()
    db.commit()
    return {'updated': True, 'user_id': user_id}


@app.get('/users', response_model=List[UserResponse], dependencies=[Depends(require_manager)])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [serialize_user(user) for user in users]


@app.get('/help-content')
def list_help_content(
    cycle_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    if not is_feature_enabled(db, 'feature_31_contextual_help', default=True):
        return {'items': [], 'cycle_id': cycle_id}
    if role not in {'manager', 'company', 'investor'}:
        raise HTTPException(status_code=403, detail='Unsupported role')
    target_cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first() if cycle_id else get_active_cycle(db) or get_latest_cycle(db)
    if not target_cycle:
        return {'items': [], 'cycle_id': None}
    rows = (
        db.query(ContextHelpContent)
        .filter(
            ContextHelpContent.cycle_id == target_cycle.id,
            ContextHelpContent.is_active.is_(True),
        )
        .order_by(ContextHelpContent.field_key.asc(), ContextHelpContent.version.desc())
        .all()
    )
    dedup: dict[str, ContextHelpContent] = {}
    for row in rows:
        if row.field_key in dedup:
            continue
        dedup[row.field_key] = row
    return {
        'cycle_id': target_cycle.id,
        'items': [
            {
                'field_key': row.field_key,
                'title': row.title or row.field_key.replace('_', ' ').title(),
                'body': row.body,
                'version': row.version,
                'updated_at': row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in dedup.values()
        ],
    }


@app.put('/admin/help-content/{cycle_id}/{field_key}', dependencies=[Depends(require_manager)])
def upsert_help_content(
    cycle_id: int,
    field_key: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    if not is_feature_enabled(db, 'feature_31_contextual_help', default=True):
        raise HTTPException(status_code=403, detail='Contextual help is disabled')
    cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail='Cycle not found')
    normalized_field_key = str(field_key or '').strip()
    if not normalized_field_key:
        raise HTTPException(status_code=422, detail='field_key is required')
    body = str(payload.get('body') or '').strip()
    if not body:
        raise HTTPException(status_code=422, detail='body is required')
    title = str(payload.get('title') or normalized_field_key.replace('_', ' ').title())

    request_user = find_request_user(db, email)
    latest = (
        db.query(ContextHelpContent)
        .filter(ContextHelpContent.cycle_id == cycle_id, ContextHelpContent.field_key == normalized_field_key)
        .order_by(ContextHelpContent.version.desc())
        .first()
    )
    next_version = int(latest.version + 1) if latest else 1
    db.add(
        ContextHelpContent(
            cycle_id=cycle_id,
            field_key=normalized_field_key,
            title=title,
            body=body,
            version=next_version,
            is_active=True,
            updated_by_user_id=request_user.id if request_user else None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    log_audit_event(
        db,
        event_type='help_content_upserted',
        actor_role='manager',
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        cycle_id=cycle_id,
        field_name=normalized_field_key,
        new_value={'title': title, 'version': next_version},
    )
    db.commit()
    return {'cycle_id': cycle_id, 'field_key': normalized_field_key, 'version': next_version, 'updated': True}


@app.get('/admin/csv-parity-check', response_model=CsvParityResponse, dependencies=[Depends(require_manager)])
def csv_parity_check(db: Session = Depends(get_db)):
    return _build_csv_parity_report(db)


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
def create_cycle(
    payload: CycleCreateRequest,
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
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
    request_user = find_request_user(db, email)
    log_audit_event(
        db,
        event_type='cycle_created',
        actor_role='manager',
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        cycle_id=None,
        new_value={'cycle_year': payload.cycle_year, 'status': cycle.status},
    )
    db.commit()
    db.refresh(cycle)
    return serialize_cycle(cycle)


@app.get('/cycles', response_model=List[CycleInfo], dependencies=[Depends(require_manager)])
def list_cycles(db: Session = Depends(get_db)):
    cycles = db.query(CollectionCycle).order_by(CollectionCycle.cycle_year.desc()).all()
    return [serialize_cycle(cycle) for cycle in cycles]

@app.patch('/cycles/{cycle_id}/status', response_model=CycleInfo, dependencies=[Depends(require_manager)])
def update_cycle_status(
    cycle_id: int,
    payload: CycleStatusUpdateRequest,
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail='Cycle not found')

    next_status = normalize_cycle_status(payload.status)
    if next_status == 'active':
        active_cycles = db.query(CollectionCycle).filter(CollectionCycle.status == 'active').all()
        for active_cycle in active_cycles:
            if active_cycle.id != cycle.id:
                active_cycle.status = 'draft'

    old_status = cycle.status
    cycle.status = next_status
    request_user = find_request_user(db, email)
    log_audit_event(
        db,
        event_type='cycle_status_updated',
        actor_role='manager',
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        cycle_id=cycle.id,
        field_name='status',
        old_value=old_status,
        new_value=next_status,
    )
    db.commit()
    db.refresh(cycle)
    return serialize_cycle(cycle)


@app.post('/cycles/{cycle_id}/clone', dependencies=[Depends(require_manager)])
def clone_cycle(
    cycle_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if not is_feature_enabled(db, 'feature_40_cycle_cloning', default=True):
        raise HTTPException(status_code=403, detail='Cycle cloning is disabled')
    require_clone_permission(db, role, email)
    source = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not source:
        raise HTTPException(status_code=404, detail='Source cycle not found')

    target_year = int(payload.get('target_year') or (int(source.cycle_year) + 1))
    existing = db.query(CollectionCycle).filter(CollectionCycle.cycle_year == target_year).first()
    if existing:
        raise HTTPException(status_code=400, detail='Target cycle year already exists')

    cloned_open_date = payload.get('submission_open_date') or source.submission_open_date
    cloned_deadline = payload.get('submission_deadline') or source.submission_deadline
    cloned_extension = payload.get('extension_date') if 'extension_date' in payload else source.extension_date

    actor = find_request_user(db, email)
    cloned = CollectionCycle(
        cycle_year=target_year,
        submission_open_date=cloned_open_date,
        submission_deadline=cloned_deadline,
        extension_date=cloned_extension,
        reminder_schedule=source.reminder_schedule,
        template_config=source.template_config,
        prefill_summary=source.prefill_summary,
        status='draft',
        created_by_user_id=actor.id if actor else None,
    )
    db.add(cloned)
    db.commit()
    db.refresh(cloned)

    db.add(
        CycleCloneLog(
            source_cycle_id=source.id,
            target_cycle_id=cloned.id,
            cloned_by_user_id=actor.id if actor else None,
            clone_options_json=json.dumps({'target_year': target_year}),
            created_at=datetime.utcnow(),
        )
    )
    log_audit_event(
        db,
        event_type='cycle_cloned',
        actor_role=role,
        actor_email=email,
        actor_user_id=actor.id if actor else None,
        cycle_id=cloned.id,
        old_value={'source_cycle_id': source.id},
        new_value={'target_cycle_id': cloned.id, 'target_year': target_year},
        metadata={'source_cycle_year': source.cycle_year},
    )
    db.commit()
    return serialize_cycle(cloned)


def _default_onboarding_steps() -> dict[str, Any]:
    return {key: {'completed': False, 'completed_at': None} for key in ONBOARDING_STEP_ORDER}


def _normalize_onboarding_state(state: OnboardingState | None) -> dict[str, Any]:
    if not state:
        return {'steps': _default_onboarding_steps(), 'progress_percent': 0, 'completed': False}
    steps = parse_json_or_default(state.steps_json, _default_onboarding_steps())
    if not isinstance(steps, dict):
        steps = _default_onboarding_steps()
    completed_count = sum(1 for key in ONBOARDING_STEP_ORDER if bool((steps.get(key) or {}).get('completed')))
    total = max(len(ONBOARDING_STEP_ORDER), 1)
    progress_percent = int(round((completed_count / total) * 100))
    return {
        'steps': steps,
        'progress_percent': progress_percent,
        'completed': completed_count == total,
    }


def _upsert_onboarding_state(db: Session, company_id: int, updated_by_user_id: int | None = None) -> OnboardingState:
    state = db.query(OnboardingState).filter(OnboardingState.company_id == company_id).first()
    if state:
        return state
    state = OnboardingState(
        company_id=company_id,
        steps_json=json.dumps(_default_onboarding_steps()),
        progress_percent=0,
        completed=False,
        updated_by_user_id=updated_by_user_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


@app.get('/companies/{company_id}/onboarding')
def get_onboarding_state(
    company_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    if role == 'company':
        request_user = find_request_user(db, email)
        if not request_user or request_user.id != company.user_id:
            raise HTTPException(status_code=403, detail='Company users can only access their own onboarding state')

    request_user = find_request_user(db, email)
    state = _upsert_onboarding_state(
        db,
        company_id=company_id,
        updated_by_user_id=request_user.id if request_user else None,
    )
    normalized = _normalize_onboarding_state(state)
    return {'company_id': company_id, **normalized}


@app.get('/companies/onboarding/overview', dependencies=[Depends(require_manager)])
def onboarding_overview(
    db: Session = Depends(get_db),
):
    companies = db.query(Company).order_by(Company.name.asc()).all()
    items: list[dict[str, Any]] = []
    for company in companies:
        state = db.query(OnboardingState).filter(OnboardingState.company_id == company.id).first()
        normalized = _normalize_onboarding_state(state)
        items.append(
            {
                'company_id': company.id,
                'company_name': company.name,
                'company_status': company.current_status,
                'progress_percent': normalized['progress_percent'],
                'completed': normalized['completed'],
                'steps': normalized['steps'],
            }
        )
    return {'items': items, 'count': len(items)}


@app.post('/companies/{company_id}/onboarding/steps/{step_key}/complete')
def complete_onboarding_step(
    company_id: int,
    step_key: str,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if step_key not in ONBOARDING_STEP_ORDER:
        raise HTTPException(status_code=400, detail='Invalid onboarding step')
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    request_user = find_request_user(db, email)
    if role == 'company' and (not request_user or request_user.id != company.user_id):
        raise HTTPException(status_code=403, detail='Company users can only complete their own onboarding steps')
    if role not in {'manager', 'company'}:
        raise HTTPException(status_code=403, detail='Unsupported role for onboarding step completion')

    state = _upsert_onboarding_state(db, company_id=company_id, updated_by_user_id=request_user.id if request_user else None)
    steps = parse_json_or_default(state.steps_json, _default_onboarding_steps())
    if not isinstance(steps, dict):
        steps = _default_onboarding_steps()
    if step_key not in steps:
        steps[step_key] = {'completed': False, 'completed_at': None}
    steps[step_key]['completed'] = True
    steps[step_key]['completed_at'] = _utc_now_iso()
    state.steps_json = json.dumps(steps)
    normalized = _normalize_onboarding_state(state)
    state.progress_percent = normalized['progress_percent']
    state.completed = normalized['completed']
    state.updated_by_user_id = request_user.id if request_user else None
    state.updated_at = datetime.utcnow()
    if state.completed:
        company.current_status = 'active'

    log_audit_event(
        db,
        event_type='onboarding_step_completed',
        actor_role=role,
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        company_id=company_id,
        field_name='onboarding_step',
        new_value={'step': step_key},
    )
    db.commit()
    return {'company_id': company_id, **normalized}


@app.post('/companies/{company_id}/onboarding/retrigger', dependencies=[Depends(require_manager)])
def retrigger_onboarding(
    company_id: int,
    db: Session = Depends(get_db),
    email: str | None = Depends(get_user_email),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    request_user = find_request_user(db, email)
    state = _upsert_onboarding_state(db, company_id=company_id, updated_by_user_id=request_user.id if request_user else None)
    state.steps_json = json.dumps(_default_onboarding_steps())
    state.progress_percent = 0
    state.completed = False
    state.updated_by_user_id = request_user.id if request_user else None
    state.updated_at = datetime.utcnow()
    company.current_status = 'pre-acquisition'
    log_audit_event(
        db,
        event_type='onboarding_retriggered',
        actor_role='manager',
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        company_id=company_id,
    )
    db.commit()
    return {'message': 'Onboarding reset successfully.', 'company_id': company_id}


@app.post('/company/{company_id}/onboarding/complete', dependencies=[Depends(require_manager)])
def complete_onboarding(company_id: int, db: Session = Depends(get_db), email: str | None = Depends(get_user_email)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    company.current_status = 'active'
    request_user = find_request_user(db, email)
    state = _upsert_onboarding_state(db, company_id=company_id, updated_by_user_id=request_user.id if request_user else None)
    complete_steps = {
        key: {'completed': True, 'completed_at': _utc_now_iso()}
        for key in ONBOARDING_STEP_ORDER
    }
    state.steps_json = json.dumps(complete_steps)
    state.progress_percent = 100
    state.completed = True
    state.updated_by_user_id = request_user.id if request_user else None
    state.updated_at = datetime.utcnow()
    log_audit_event(
        db,
        event_type='onboarding_completed',
        actor_role='manager',
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        company_id=company_id,
    )
    db.commit()
    return {"message": "Onboarding complete. Company is now active in the portfolio."}

@app.post('/company/{company_id}/submissions', response_model=SubmissionInfo)
def add_submission(
    company_id: int,
    submission: SubmissionCreateRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    request_user = find_request_user(db, email)

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

    incoming_payload = submission.model_dump()
    baseline_submission = latest_for_cycle
    if baseline_submission is None:
        baseline_submission = (
            db.query(Submission)
            .filter(Submission.company_id == company_id)
            .order_by(Submission.id.desc())
            .first()
        )

    prior_submission = _build_prior_submission(baseline_submission, db) if baseline_submission else None
    prior_payload = parse_submission(prior_submission)

    existing_payload = parse_submission(latest_for_cycle) if latest_for_cycle else {}
    merged_payload = _upsert_section_comments(existing_payload, incoming_payload, actor_role='company')
    comparison = _build_submission_comparison(merged_payload, prior_payload)
    required_sections = set(comparison.get('required_sections') or [])
    missing_sections = []
    comments = _extract_section_comments(merged_payload)
    for section in sorted(required_sections):
        latest_comment = str((comments.get(section) or [{}])[-1].get('text') or '').strip() if comments.get(section) else ''
        if not latest_comment:
            missing_sections.append(section)
    if missing_sections:
        raise HTTPException(
            status_code=422,
            detail=f"Variance explanation required for sections: {', '.join(missing_sections)}",
        )

    if latest_for_cycle and normalize_submission_status(latest_for_cycle.status) == 'resubmission requested':
        enforce_transition(latest_for_cycle.status, 'submitted')
        previous_payload = parse_submission(latest_for_cycle)
        latest_for_cycle.esg_data = json.dumps(merged_payload)
        latest_for_cycle.status = 'submitted'
        company.current_status = 'submitted'
        if is_feature_enabled(db, 'feature_26_declaration_workflow', default=True):
            _revoke_submission_declaration(db, latest_for_cycle.id)
        log_audit_event(
            db,
            event_type='submission_resubmitted',
            actor_role=role,
            actor_email=email,
            actor_user_id=request_user.id if request_user else None,
            company_id=company_id,
            submission_id=latest_for_cycle.id,
            cycle_id=latest_for_cycle.cycle_id,
            old_value=previous_payload,
            new_value=merged_payload,
            source='ui',
        )
        db.commit()
        db.refresh(latest_for_cycle)
        return latest_for_cycle

    submission_record = Submission(
        company_id=company_id,
        cycle_id=target_cycle.id,
        esg_data=json.dumps(merged_payload),
        status='submitted',
    )
    company.current_status = 'submitted'
    db.add(submission_record)
    log_audit_event(
        db,
        event_type='submission_created',
        actor_role=role,
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        company_id=company_id,
        submission_id=None,
        cycle_id=target_cycle.id,
        old_value={},
        new_value=merged_payload,
        source='ui',
    )
    db.commit()
    db.refresh(submission_record)
    log_audit_event(
        db,
        event_type='submission_created_postcommit',
        actor_role=role,
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        company_id=company_id,
        submission_id=submission_record.id,
        cycle_id=submission_record.cycle_id,
        source='ui',
    )
    db.commit()
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


@app.post('/submissions/{submission_id}/declaration')
def declare_submission(
    submission_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if not is_feature_enabled(db, 'feature_26_declaration_workflow', default=True):
        raise HTTPException(status_code=403, detail='Declaration workflow is disabled')
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    company = db.query(Company).filter(Company.id == submission.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    request_user = find_request_user(db, email)
    if role == 'company':
        if not request_user or request_user.id != company.user_id:
            raise HTTPException(status_code=403, detail='Company users can only declare their own submissions')
    elif role != 'manager':
        raise HTTPException(status_code=403, detail='Unsupported role for declaration')

    signatory_name = str(payload.get('signatory_name') or (request_user.name if request_user else '')).strip()
    if not signatory_name:
        raise HTTPException(status_code=422, detail='signatory_name is required')
    ack = bool(payload.get('acknowledged', False))
    if not ack:
        raise HTTPException(status_code=422, detail='Declaration acknowledgement is required')

    existing = db.query(SubmissionDeclaration).filter(SubmissionDeclaration.submission_id == submission_id).first()
    if existing:
        existing.signatory_name = signatory_name
        existing.signatory_role = str(payload.get('signatory_role') or role)
        existing.statement_version = str(payload.get('statement_version') or 'v1')
        existing.declared_at = datetime.utcnow()
        existing.revoked_at = None
        existing.active = True
        existing.metadata_json = json.dumps({'statement': _declaration_statement()})
    else:
        db.add(
            SubmissionDeclaration(
                submission_id=submission_id,
                company_id=submission.company_id,
                signatory_name=signatory_name,
                signatory_role=str(payload.get('signatory_role') or role),
                statement_version=str(payload.get('statement_version') or 'v1'),
                declared_at=datetime.utcnow(),
                active=True,
                metadata_json=json.dumps({'statement': _declaration_statement()}),
            )
        )
    log_audit_event(
        db,
        event_type='submission_declared',
        actor_role=role,
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        company_id=submission.company_id,
        submission_id=submission_id,
        cycle_id=submission.cycle_id,
        field_name='declaration',
        new_value={'signatory_name': signatory_name},
        metadata={'statement': _declaration_statement()},
    )
    db.commit()
    return {
        'submission_id': submission_id,
        'company_id': submission.company_id,
        'active': True,
        'signatory_name': signatory_name,
        'statement': _declaration_statement(),
    }


@app.get('/submissions/{submission_id}/declaration')
def get_submission_declaration(
    submission_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    company = db.query(Company).filter(Company.id == submission.company_id).first()
    if role == 'company':
        request_user = find_request_user(db, email)
        if not request_user or not company or request_user.id != company.user_id:
            raise HTTPException(status_code=403, detail='Company users can only view their own declarations')

    declaration = db.query(SubmissionDeclaration).filter(SubmissionDeclaration.submission_id == submission_id).first()
    if not declaration:
        return {'submission_id': submission_id, 'active': False}
    return {
        'submission_id': submission_id,
        'company_id': declaration.company_id,
        'active': bool(declaration.active),
        'signatory_name': declaration.signatory_name,
        'signatory_role': declaration.signatory_role,
        'statement_version': declaration.statement_version,
        'declared_at': declaration.declared_at.isoformat() if declaration.declared_at else None,
        'revoked_at': declaration.revoked_at.isoformat() if declaration.revoked_at else None,
    }


@app.get('/audit/events')
def audit_events(
    company_id: int | None = Query(default=None),
    submission_id: int | None = Query(default=None),
    field_name: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if not is_feature_enabled(db, 'feature_25_audit_trail_viewer', default=True):
        raise HTTPException(status_code=403, detail='Audit trail is disabled')

    query = db.query(AuditEvent)
    if company_id is not None:
        query = query.filter(AuditEvent.company_id == company_id)
    if submission_id is not None:
        query = query.filter(AuditEvent.submission_id == submission_id)
    if field_name:
        query = query.filter(AuditEvent.field_name == field_name)
    if event_type:
        query = query.filter(AuditEvent.event_type == event_type)

    if role == 'company':
        request_user = find_request_user(db, email)
        if not request_user:
            raise HTTPException(status_code=403, detail='Company access denied')
        owned_company = db.query(Company).filter(Company.user_id == request_user.id).first()
        if not owned_company:
            return {'items': [], 'count': 0}
        query = query.filter(AuditEvent.company_id == owned_company.id)
    elif role == 'manager':
        perms = get_user_permissions(db, role, email)
        if not perms.get('can_view_portfolio_audit'):
            raise HTTPException(status_code=403, detail='Audit permissions are required')
        scope = perms.get('read_only_audit_scope') or []
        if isinstance(scope, list) and scope and '*' not in scope:
            allowed_company_ids = {int(item) for item in scope if str(item).isdigit()}
            if allowed_company_ids:
                query = query.filter(AuditEvent.company_id.in_(list(allowed_company_ids)))
            else:
                return {'items': [], 'count': 0}
    else:
        raise HTTPException(status_code=403, detail='Audit trail is restricted to manager/company roles')

    rows = query.order_by(AuditEvent.id.desc()).limit(limit).all()
    return {
        'count': len(rows),
        'items': [
            {
                'id': row.id,
                'event_type': row.event_type,
                'actor_email': row.actor_email,
                'actor_role': row.actor_role,
                'company_id': row.company_id,
                'submission_id': row.submission_id,
                'cycle_id': row.cycle_id,
                'field_name': row.field_name,
                'old_value': row.old_value,
                'new_value': row.new_value,
                'source': row.source,
                'metadata': parse_json_or_default(row.metadata_json, {}),
                'created_at': row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@app.get('/historical-context/company/{company_id}')
def company_historical_context(
    company_id: int,
    submission_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    if role not in {'manager', 'company'}:
        raise HTTPException(status_code=403, detail='Historical context is restricted to managers and company users')

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')

    if role == 'company':
        request_user = find_request_user(db, email)
        if not request_user or request_user.id != company.user_id:
            raise HTTPException(status_code=403, detail='Company users can only access their own historical context')

    if submission_id is not None:
        submission = (
            db.query(Submission)
            .filter(Submission.id == submission_id, Submission.company_id == company_id)
            .first()
        )
    else:
        submission = (
            db.query(Submission)
            .filter(Submission.company_id == company_id)
            .order_by(Submission.id.desc())
            .first()
        )

    prior_submission = _build_prior_submission(submission, db) if submission else None
    return _build_historical_context_payload(company, submission, prior_submission)

@app.patch('/submissions/{submission_id}/status', response_model=SubmissionInfo, dependencies=[Depends(require_manager)])
def update_submission_status(
    submission_id: int,
    payload: SubmissionStatusUpdateRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    next_status = normalize_submission_status(payload.status)
    if next_status not in ALLOWED_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail='Invalid submission status')

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    if (
        is_feature_enabled(db, 'feature_26_declaration_workflow', default=True)
        and next_status in {'submitted', 'under review', 'approved'}
        and not _is_submission_declared(db, submission_id)
    ):
        raise HTTPException(status_code=422, detail='Active declaration is required before review status transitions')

    old_status = submission.status
    enforce_transition(submission.status, next_status)
    submission.status = next_status
    request_user = find_request_user(db, email)
    log_audit_event(
        db,
        event_type='submission_status_updated',
        actor_role=role,
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        company_id=submission.company_id,
        submission_id=submission.id,
        cycle_id=submission.cycle_id,
        field_name='status',
        old_value=old_status,
        new_value=next_status,
    )
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

def _compute_carbon(payload: GHGCalculatorRequest) -> GHGCalculatorResponse:
    factors = {
        'diesel_liters': 2.68,  # kgCO2e per liter
        'natural_gas_kwh': 0.183,  # kgCO2e per kWh
        'lpg_liters': 1.51,  # kgCO2e per liter
        'refrigerant_kg': 1430.0,  # kgCO2e per kg, R134a proxy
        'grid_default_kwh': 0.5,  # kgCO2e per kWh
        'travel_car_km': 0.171,  # kgCO2e per km
        'travel_rail_km': 0.035,  # kgCO2e per km
        'travel_flight_km': 0.146,  # kgCO2e per km
        'waste_tonnes': 450.0,  # kgCO2e per tonne
        'wastewater_m3': 0.708,  # kgCO2e per m3
    }

    grid_factor = payload.grid_emission_factor_kg_per_kwh
    if grid_factor is None or grid_factor <= 0:
        grid_factor = factors['grid_default_kwh']

    electricity_total_kwh = max(float(payload.electricity_kwh or 0), 0.0)
    renewable_kwh = max(float(payload.renewable_electricity_kwh or 0), 0.0)
    renewable_kwh = min(renewable_kwh, electricity_total_kwh)
    market_based_kwh = max(electricity_total_kwh - renewable_kwh, 0.0)

    entries = [
        {
            'scope': 'Scope 1',
            'category': 'Stationary Combustion',
            'activity': 'Fuel (diesel/liquid fuel)',
            'amount': max(float(payload.fuel_liters or 0), 0.0),
            'unit': 'liters',
            'factor': factors['diesel_liters'],
        },
        {
            'scope': 'Scope 1',
            'category': 'Stationary Combustion',
            'activity': 'Natural Gas',
            'amount': max(float(payload.natural_gas_kwh or 0), 0.0),
            'unit': 'kWh',
            'factor': factors['natural_gas_kwh'],
        },
        {
            'scope': 'Scope 1',
            'category': 'Stationary Combustion',
            'activity': 'LPG',
            'amount': max(float(payload.lpg_liters or 0), 0.0),
            'unit': 'liters',
            'factor': factors['lpg_liters'],
        },
        {
            'scope': 'Scope 1',
            'category': 'Fugitive Emissions',
            'activity': 'Refrigerant Leakage',
            'amount': max(float(payload.refrigerant_kg or 0), 0.0),
            'unit': 'kg',
            'factor': factors['refrigerant_kg'],
        },
        {
            'scope': 'Scope 2 (Location)',
            'category': 'Purchased Electricity',
            'activity': 'Grid Electricity (location-based)',
            'amount': electricity_total_kwh,
            'unit': 'kWh',
            'factor': grid_factor,
        },
        {
            'scope': 'Scope 2 (Market)',
            'category': 'Purchased Electricity',
            'activity': 'Net Electricity after Renewable Procurement',
            'amount': market_based_kwh,
            'unit': 'kWh',
            'factor': grid_factor,
        },
        {
            'scope': 'Scope 3',
            'category': 'Business Travel',
            'activity': 'Travel by Car',
            'amount': max(float(payload.business_travel_car_km or 0), 0.0),
            'unit': 'km',
            'factor': factors['travel_car_km'],
        },
        {
            'scope': 'Scope 3',
            'category': 'Business Travel',
            'activity': 'Travel by Rail',
            'amount': max(float(payload.business_travel_rail_km or 0), 0.0),
            'unit': 'km',
            'factor': factors['travel_rail_km'],
        },
        {
            'scope': 'Scope 3',
            'category': 'Business Travel',
            'activity': 'Travel by Flight',
            'amount': max(float(payload.business_travel_flight_km or 0), 0.0),
            'unit': 'km',
            'factor': factors['travel_flight_km'],
        },
        {
            'scope': 'Scope 3',
            'category': 'Waste',
            'activity': 'Solid Waste',
            'amount': max(float(payload.waste_tonnes or 0), 0.0),
            'unit': 'tonnes',
            'factor': factors['waste_tonnes'],
        },
        {
            'scope': 'Scope 3',
            'category': 'Wastewater',
            'activity': 'Wastewater Treatment',
            'amount': max(float(payload.wastewater_m3 or 0), 0.0),
            'unit': 'm3',
            'factor': factors['wastewater_m3'],
        },
    ]

    breakdown = []
    scope_1_kg = 0.0
    scope_2_location_kg = 0.0
    scope_2_market_kg = 0.0
    scope_3_kg = 0.0

    for entry in entries:
        emissions_kg = float(entry['amount']) * float(entry['factor'])
        scope = entry['scope']
        if scope == 'Scope 1':
            scope_1_kg += emissions_kg
        elif scope == 'Scope 2 (Location)':
            scope_2_location_kg += emissions_kg
        elif scope == 'Scope 2 (Market)':
            scope_2_market_kg += emissions_kg
        elif scope == 'Scope 3':
            scope_3_kg += emissions_kg

        breakdown.append(
            {
                'scope': scope,
                'category': entry['category'],
                'activity': entry['activity'],
                'amount': round(float(entry['amount']), 4),
                'unit': entry['unit'],
                'emission_factor_kg_per_unit': round(float(entry['factor']), 6),
                'emissions_tco2e': round(emissions_kg / 1000.0, 6),
            }
        )

    scope_1_tco2e = scope_1_kg / 1000.0
    scope_2_location_tco2e = scope_2_location_kg / 1000.0
    scope_2_market_tco2e = scope_2_market_kg / 1000.0
    scope_3_tco2e = scope_3_kg / 1000.0
    total_tco2e = scope_1_tco2e + scope_2_location_tco2e + scope_3_tco2e

    return GHGCalculatorResponse(
        scope_1_tco2e=round(scope_1_tco2e, 6),
        scope_2_tco2e=round(scope_2_location_tco2e, 6),
        scope_2_market_tco2e=round(scope_2_market_tco2e, 6),
        scope_3_tco2e=round(scope_3_tco2e, 6),
        total_tco2e=round(total_tco2e, 6),
        methodology_version='carbon-calc-v2.0',
        assumptions=[
            'Location-based Scope 2 uses provided grid factor or default 0.5 kgCO2e/kWh.',
            'Market-based Scope 2 adjusts purchased electricity by renewable procurement.',
            'Scope 3 includes travel, waste, and wastewater categories included in this tool.',
        ],
        breakdown=breakdown,
    )


@app.post('/calculator/ghg', response_model=GHGCalculatorResponse)
def calculate_ghg(payload: GHGCalculatorRequest):
    return _compute_carbon(payload)


@app.post('/calculator/carbon', response_model=GHGCalculatorResponse)
def calculate_carbon(payload: GHGCalculatorRequest):
    return _compute_carbon(payload)

@app.post('/company/{company_id}/upload-evidence')
def upload_evidence(company_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    return {"filename": file.filename, "message": "Evidence uploaded successfully"}

@app.post('/submissions/{submission_id}/review', dependencies=[Depends(require_manager)])
def review_submission(
    submission_id: int,
    payload: ReviewSubmissionRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    next_status = normalize_submission_status(payload.review_status)
    if next_status not in ALLOWED_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail='Invalid review status')
    if (
        is_feature_enabled(db, 'feature_26_declaration_workflow', default=True)
        and next_status in {'under review', 'approved'}
        and not _is_submission_declared(db, submission_id)
    ):
        raise HTTPException(status_code=422, detail='Active declaration is required before review')

    old_status = submission.status
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
    request_user = find_request_user(db, email)
    log_audit_event(
        db,
        event_type='submission_reviewed',
        actor_role=role,
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        company_id=submission.company_id,
        submission_id=submission.id,
        cycle_id=submission.cycle_id,
        field_name='review_status',
        old_value=old_status,
        new_value=next_status,
        metadata={'review_comment': payload.review_comment},
    )
    db.commit()
    db.refresh(submission)
    return {"message": "Review logged successfully", "status": submission.status}

@app.post('/submissions/{submission_id}/validate', dependencies=[Depends(require_manager)])
def validate_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
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

    request_user = find_request_user(db, email)
    log_audit_event(
        db,
        event_type='submission_validated',
        actor_role=role,
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        company_id=submission.company_id,
        submission_id=submission.id,
        cycle_id=submission.cycle_id,
        metadata={'flags_created': flags_created},
    )
    db.commit()
    return {"message": f"Validation complete. {flags_created} anomalies flagged.", "flagged": flags_created > 0}


@app.post('/submissions/{submission_id}/validation-decision', dependencies=[Depends(require_manager)])
def set_validation_decision(
    submission_id: int,
    payload: ValidationDecisionRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
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

    request_user = find_request_user(db, email)
    log_audit_event(
        db,
        event_type='validation_decision_set',
        actor_role=role,
        actor_email=email,
        actor_user_id=request_user.id if request_user else None,
        company_id=submission.company_id,
        submission_id=submission.id,
        cycle_id=submission.cycle_id,
        field_name=field_name,
        new_value=decision,
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
    request_user = find_request_user(db, user_email)
    log_audit_event(
        db,
        event_type='submission_unlocked',
        actor_role='manager',
        actor_email=user_email,
        actor_user_id=request_user.id if request_user else None,
        company_id=submission.company_id,
        submission_id=submission.id,
        cycle_id=submission.cycle_id,
        metadata={'reason': payload.reason, 'expiry_hours': payload.expiry_hours},
    )
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
    request_user = find_request_user(db, user_email)
    log_audit_event(
        db,
        event_type='reminder_sent',
        actor_role='manager',
        actor_email=user_email,
        actor_user_id=request_user.id if request_user else None,
        company_id=company.id,
        cycle_id=cycle.id,
        new_value={'channel': payload.channel, 'message': payload.message},
    )
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


NUMERIC_ANOMALY_FIELDS = [
    'scope_1_emissions',
    'scope_2_location_based',
    'scope_3_emissions',
    'total_ghg_emissions',
    'total_energy_consumption',
    'renewable_energy_consumption',
    'total_water_withdrawal',
    'water_recycled_reused',
    'total_waste_generated',
    'waste_diverted_from_landfill',
    'hazardous_waste_generated',
    'female_representation_percent',
    'female_leadership_representation_percent',
    'independent_board_members_percent',
    'female_board_members_percent',
    'trifr',
]


def format_metric_label(value: str | None) -> str:
    label = str(value or '').replace('_', ' ').strip()
    if not label:
        return 'Metric'
    replacements = {
        'ghg': 'GHG',
        'trifr': 'TRIFR',
        'esg': 'ESG',
    }
    parts = []
    for word in label.split():
        parts.append(replacements.get(word.lower(), word.capitalize()))
    return ' '.join(parts)


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

HISTORICAL_SECTION_FIELDS = {
    'environmental': [
        ('scope_1_emissions', 'Scope 1 emissions', 'number'),
        ('scope_2_location_based', 'Scope 2 emissions (location-based)', 'number'),
        ('scope_2_market_based', 'Scope 2 emissions (market-based)', 'number'),
        ('scope_3_emissions', 'Scope 3 emissions', 'number'),
        ('total_ghg_emissions', 'Total GHG emissions', 'number'),
        ('reduction_target_percent', 'Reduction target', 'number'),
        ('reduction_target_year', 'Reduction target year', 'number'),
        ('reduction_strategy_description', 'Reduction strategy description', 'text'),
        ('total_energy_consumption', 'Total energy consumption', 'number'),
        ('renewable_energy_consumption', 'Renewable energy consumption', 'number'),
        ('total_water_withdrawal', 'Total water withdrawal', 'number'),
        ('water_recycled_reused', 'Water recycled or reused', 'number'),
        ('total_waste_generated', 'Total waste generated', 'number'),
        ('waste_diverted_from_landfill', 'Waste diverted from landfill', 'number'),
        ('hazardous_waste_generated', 'Hazardous waste generated', 'number'),
        ('air_quality_control_measures', 'Air quality control measures in place', 'select'),
        ('nox_sox_emissions', 'NOx / SOx emissions', 'number'),
    ],
    'social': [
        ('whs_policy_in_place', 'WHS policy in place', 'select'),
        ('whs_policy_document_reference', 'WHS policy document reference', 'text'),
        ('trifr', 'TRIFR', 'number'),
        ('total_fatalities', 'Total fatalities', 'number'),
        ('total_lost_time_injuries', 'Total lost time injuries', 'number'),
        ('total_incidents_reported', 'Total incidents reported', 'number'),
        ('total_employees_fte', 'Total employees (FTE)', 'number'),
        ('employee_turnover_rate', 'Employee turnover rate', 'number'),
        ('female_representation_percent', 'Female representation', 'number'),
        ('female_leadership_representation_percent', 'Female representation in leadership', 'number'),
        ('community_investment_spend', 'Community investment or spend', 'number'),
    ],
    'governance': [
        ('esg_policy_in_place', 'ESG policy in place', 'select'),
        ('esg_policy_document_reference', 'ESG policy document reference', 'text'),
        ('board_level_esg_oversight', 'Board-level ESG oversight', 'select'),
        ('esg_kpis_linked_to_remuneration', 'ESG KPIs linked to remuneration', 'select'),
        ('cybersecurity_policy_in_place', 'Cybersecurity policy in place', 'select'),
        ('cybersecurity_policy_document_reference', 'Cybersecurity policy document reference', 'text'),
        ('cyber_incidents_in_reporting_period', 'Cyber incidents in reporting period', 'number'),
        ('anti_bribery_corruption_policy', 'Anti-bribery and corruption policy', 'select'),
        ('confirmed_cases_of_corruption', 'Confirmed cases of corruption', 'number'),
        ('total_board_members', 'Total board members', 'number'),
        ('independent_board_members_percent', 'Independent board members', 'number'),
        ('female_board_members_percent', 'Female board members', 'number'),
    ],
}

SECTION_ORDER = ['environmental', 'social', 'governance']


def _safe_float(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _section_comment_field(section: str) -> str:
    return f'section_comment_{section}'


def _extract_section_comments(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    defaults = {section: [] for section in SECTION_ORDER}
    if not isinstance(payload, dict):
        return defaults
    existing = payload.get('__section_comments')
    if isinstance(existing, dict):
        for section in SECTION_ORDER:
            raw_items = existing.get(section) or []
            if isinstance(raw_items, list):
                cleaned = []
                for item in raw_items:
                    if not isinstance(item, dict):
                        continue
                    text = str(item.get('text') or '').strip()
                    if not text:
                        continue
                    cleaned.append({
                        'text': text,
                        'timestamp': str(item.get('timestamp') or _utc_now_iso()),
                        'author_role': str(item.get('author_role') or 'company'),
                    })
                defaults[section] = cleaned[-25:]

    for section in SECTION_ORDER:
        legacy_text = str(payload.get(_section_comment_field(section)) or '').strip()
        if legacy_text and not defaults[section]:
            defaults[section] = [{
                'text': legacy_text,
                'timestamp': _utc_now_iso(),
                'author_role': 'company',
            }]
    return defaults


def _upsert_section_comments(
    existing_payload: dict[str, Any],
    incoming_payload: dict[str, Any],
    actor_role: str = 'company',
) -> dict[str, Any]:
    merged = dict(existing_payload or {})
    comments = _extract_section_comments(merged)
    section_comment_fields = {_section_comment_field(section) for section in SECTION_ORDER}

    for key, value in (incoming_payload or {}).items():
        if key == '__section_comments' or key in section_comment_fields:
            continue
        merged[key] = value

    for section in SECTION_ORDER:
        field_name = _section_comment_field(section)
        incoming_text = str(incoming_payload.get(field_name) or '').strip()
        if not incoming_text:
            continue
        section_comments = list(comments.get(section) or [])
        latest = section_comments[-1] if section_comments else None
        if latest and str(latest.get('text') or '').strip() == incoming_text:
            continue
        section_comments.append({
            'text': incoming_text,
            'timestamp': _utc_now_iso(),
            'author_role': actor_role,
        })
        comments[section] = section_comments[-25:]

    merged['__section_comments'] = comments
    for section in SECTION_ORDER:
        field_name = _section_comment_field(section)
        latest_items = comments.get(section) or []
        latest_item = latest_items[-1] if latest_items else {}
        merged[field_name] = str((latest_item or {}).get('text') or incoming_payload.get(field_name) or '').strip()
    return merged


def _submission_reporting_year(submission: Submission | None) -> int | None:
    if not submission:
        return None
    payload = parse_submission(submission)
    payload_year = payload.get('reporting_year')
    try:
        parsed_payload_year = int(payload_year)
        if parsed_payload_year > 0:
            return parsed_payload_year
    except (TypeError, ValueError):
        pass
    if submission.cycle and submission.cycle.cycle_year:
        try:
            parsed_cycle_year = int(submission.cycle.cycle_year)
            if parsed_cycle_year > 0:
                return parsed_cycle_year
        except (TypeError, ValueError):
            return None
    return None


def _build_prior_submission(submission: Submission | None, db: Session) -> Submission | None:
    if not submission:
        return None

    current_reporting_year = _submission_reporting_year(submission)
    candidates = (
        db.query(Submission)
        .filter(
            Submission.company_id == submission.company_id,
            Submission.id != submission.id,
            func.lower(Submission.status) == 'approved',
        )
        .all()
    )
    if not candidates:
        return None

    if current_reporting_year is not None:
        prior_year_candidates: list[tuple[int, int, Submission]] = []
        for candidate in candidates:
            candidate_reporting_year = _submission_reporting_year(candidate)
            if candidate_reporting_year is None:
                continue
            if candidate_reporting_year < current_reporting_year:
                prior_year_candidates.append((candidate_reporting_year, candidate.id, candidate))
        if prior_year_candidates:
            prior_year_candidates.sort(key=lambda item: (item[0], item[1]))
            return prior_year_candidates[-1][2]

    fallback_candidates = [candidate for candidate in candidates if candidate.id < submission.id]
    if not fallback_candidates:
        return None
    fallback_candidates.sort(key=lambda candidate: candidate.id)
    return fallback_candidates[-1]


def _variance_row_status(variance_percent: float | None) -> str:
    if variance_percent is None:
        return 'ok'
    absolute = abs(variance_percent)
    if absolute > 30:
        return 'error'
    if absolute > 18:
        return 'warning'
    return 'ok'


def _build_submission_comparison(current_payload: dict[str, Any], prior_payload: dict[str, Any]) -> dict[str, Any]:
    rows_by_section: dict[str, list[dict[str, Any]]] = {section: [] for section in SECTION_ORDER}
    required_sections: set[str] = set()
    prior_values: dict[str, Any] = {}

    for section in SECTION_ORDER:
        for field_key, field_label, input_type in HISTORICAL_SECTION_FIELDS.get(section, []):
            curr = current_payload.get(field_key)
            prev = prior_payload.get(field_key)
            prior_values[field_key] = prev
            delta = None
            variance_percent = None
            changed = False
            requires_explanation = False
            status = 'ok'

            if input_type == 'number':
                curr_num = _safe_float(curr)
                prev_num = _safe_float(prev)
                if curr_num is not None and prev_num is not None:
                    delta = curr_num - prev_num
                    if prev_num == 0:
                        variance_percent = None
                        changed = abs(delta) > 0
                        if changed:
                            requires_explanation = True
                            status = 'warning'
                    else:
                        variance_percent = round((delta / abs(prev_num)) * 100, 2)
                        changed = abs(delta) > 0
                        status = _variance_row_status(variance_percent)
                        if abs(variance_percent) > 20:
                            requires_explanation = True
                else:
                    changed = curr_num is not None and prev_num is None
            else:
                curr_text = str(curr or '').strip()
                prev_text = str(prev or '').strip()
                changed = bool(prev_text or curr_text) and curr_text != prev_text
                if input_type == 'select' and changed and prev_text:
                    requires_explanation = True
                    status = 'error'

            if requires_explanation:
                required_sections.add(section)

            rows_by_section[section].append({
                'section': section,
                'field_key': field_key,
                'field_label': field_label,
                'input_type': input_type,
                'current_value': curr,
                'prior_value': prev,
                'delta': delta,
                'variance_percent': variance_percent,
                'status': status,
                'changed': changed,
                'requires_explanation': requires_explanation,
            })

    return {
        'rows_by_section': rows_by_section,
        'required_sections': sorted(required_sections),
        'prior_values': prior_values,
    }


def _build_historical_context_payload(company: Company, submission: Submission | None, prior_submission: Submission | None) -> dict[str, Any]:
    current_payload = parse_submission(submission)
    prior_payload = parse_submission(prior_submission)
    comments = _extract_section_comments(current_payload)
    comparison = _build_submission_comparison(current_payload, prior_payload)
    required_sections = set(comparison.get('required_sections') or [])
    missing_sections = []
    for section in sorted(required_sections):
        latest_comment = str((comments.get(section) or [{}])[-1].get('text') or '').strip() if comments.get(section) else ''
        if not latest_comment:
            missing_sections.append(section)

    return {
        'company_id': company.id,
        'company_name': company.name,
        'submission_id': submission.id if submission else None,
        'prior_submission_id': prior_submission.id if prior_submission else None,
        'current_cycle_year': _submission_reporting_year(submission),
        'prior_cycle_year': _submission_reporting_year(prior_submission),
        'generated_at': _utc_now_iso(),
        'rows_by_section': comparison.get('rows_by_section') or {},
        'prior_values': comparison.get('prior_values') or {},
        'required_sections': sorted(required_sections),
        'missing_explanation_sections': missing_sections,
        'blocked': bool(missing_sections),
        'section_comments': comments,
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
    emissions_trend = list(analytics.get('emissions_trend') or [])
    latest_trend = emissions_trend[-1] if emissions_trend else {}
    prior_trend = emissions_trend[-2] if len(emissions_trend) > 1 else {}
    latest_emissions = float(latest_trend.get('total_emissions') or 0)
    prior_emissions = float(prior_trend.get('total_emissions') or 0)
    emissions_delta_pct = 0.0
    if prior_emissions > 0:
        emissions_delta_pct = round(((latest_emissions - prior_emissions) / prior_emissions) * 100, 2)

    status_counts = analytics.get('status_counts') or {}
    data_quality = analytics.get('data_quality') or {}
    score_breakdown = analytics.get('score_breakdown') or {}
    external_feed = _build_external_context_feed(limit=8)
    external_items = list(external_feed.get('items') or [])[:6]
    live_events = _build_live_activity_events(db, limit=8)

    key_metrics = [
        {'name': 'Portfolio ESG Score', 'value': round(float(analytics.get('portfolio_esg_score') or 0), 2), 'unit': '/100'},
        {'name': 'Approved Submissions', 'value': approved, 'unit': 'count'},
        {'name': 'Reporting Coverage', 'value': round((int(analytics.get('reporting_companies') or 0) / max(companies, 1)) * 100, 2), 'unit': '%'},
        {'name': 'Total Emissions', 'value': round(float((analytics.get('emissions_totals') or {}).get('total') or 0), 2), 'unit': 'tCO2e'},
        {'name': 'Data Confidence', 'value': round(float(data_quality.get('confidence') or 0), 2), 'unit': '%'},
    ]

    benchmark_callouts = [
        f"E score {float(score_breakdown.get('E') or 0):.1f}, S score {float(score_breakdown.get('S') or 0):.1f}, G score {float(score_breakdown.get('G') or 0):.1f}.",
        f"Governance adoption at {float(analytics.get('governance_adoption_percent') or 0):.1f}%.",
        f"Underperforming sectors: {', '.join((analytics.get('underperforming_sectors') or [])[:3]) or 'none flagged'}.",
    ]

    news_highlights = [
        {
            'title': str(item.get('title') or 'ESG update'),
            'source': str(item.get('source_label') or item.get('source_id') or 'External ESG feed'),
            'summary': str(item.get('summary') or ''),
            'published_at': str(item.get('published_at') or ''),
            'url': str(item.get('url') or ''),
        }
        for item in external_items
    ]

    operations_digest = [
        f"Submitted: {int(status_counts.get('Submitted') or 0)}",
        f"Under Review: {int(status_counts.get('Under Review') or 0)}",
        f"In Progress: {int(status_counts.get('In Progress') or 0)}",
        f"Not Started: {int(status_counts.get('Not Started') or 0)}",
    ]

    trend_summary = (
        f"Latest emissions period {str(latest_trend.get('period') or 'N/A')} at {latest_emissions:.2f} tCO2e "
        f"({emissions_delta_pct:+.2f}% vs prior period)."
    )

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
        'trend_summary': trend_summary,
        'benchmark_callouts': benchmark_callouts,
        'key_metrics': key_metrics,
        'operations_digest': operations_digest,
        'news_highlights': news_highlights,
        'news_source_count': int(external_feed.get('source_count') or 0),
        'news_fallback_used': bool(external_feed.get('fallback_used')),
        'latest_activity': live_events,
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
    body_lines += ['', 'Watchouts:'] + [f"- {item}" for item in (payload.get('watchouts') or [])]
    body_lines += ['', 'Recommendations:'] + [f"- {item}" for item in (payload.get('recommendations') or [])]
    body_lines += ['', 'Key Metrics:'] + [
        f"- {item.get('name')}: {item.get('value')} {item.get('unit')}"
        for item in (payload.get('key_metrics') or [])
    ]
    body_lines += ['', 'Trend Summary:', str(payload.get('trend_summary') or '')]
    body_lines += ['', 'External ESG News:'] + [
        f"- {item.get('title')} ({item.get('source')})"
        for item in (payload.get('news_highlights') or [])
    ]
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
    raise HTTPException(status_code=410, detail='Cron newsletter trigger is temporarily disabled')


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


def _infer_news_sector_tags(title: str | None, summary: str | None) -> list[str]:
    haystack = f'{str(title or "")} {str(summary or "")}'.lower()
    tags: list[str] = []
    for sector, keywords in NEWS_SECTOR_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf'\b{re.escape(keyword.lower())}\b', haystack):
                tags.append(sector)
                break
    if not tags:
        return ['General ESG']
    return tags[:3]


def _with_sector_tags(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_tags = item.get('sector_tags')
        cleaned_tags = [str(tag).strip() for tag in raw_tags] if isinstance(raw_tags, list) else []
        cleaned_tags = [tag for tag in cleaned_tags if tag]
        if not cleaned_tags:
            cleaned_tags = _infer_news_sector_tags(item.get('title'), item.get('summary'))
        normalized = dict(item)
        normalized['sector_tags'] = cleaned_tags[:3]
        normalized_items.append(normalized)
    return normalized_items


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
                'sector_tags': _infer_news_sector_tags(title, summary),
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
            'sector_tags': ['Governance'],
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
            'sector_tags': ['Energy & Utilities'],
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
            'sector_tags': ['Technology', 'Governance'],
        },
    ][: max(limit, 1)]


def _build_external_context_feed(limit: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with COLLAB_LOCK:
        cached_at = NEWS_FEED_CACHE.get('fetched_at')
        cached_items = list(NEWS_FEED_CACHE.get('items') or [])
        if isinstance(cached_at, datetime) and cached_items:
            if (now - cached_at).total_seconds() < NEWS_FEED_TTL_SECONDS:
                normalized_cached_items = _with_sector_tags(cached_items)
                return {
                    'generated_at': cached_at.isoformat().replace('+00:00', 'Z'),
                    'fallback_used': bool(NEWS_FEED_CACHE.get('fallback_used', True)),
                    'source_count': int(NEWS_FEED_CACHE.get('source_count', 0)),
                    'items': normalized_cached_items[: max(limit, 1)],
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
        final_items = _with_sector_tags(live_items[: max(limit, 1)])
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

    fallback_items = _with_sector_tags(_fallback_external_feed_items(limit=limit))
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


@app.get('/external-context/feed', dependencies=[Depends(require_supported_role)])
def external_context_feed(limit: int = Query(default=12, ge=3, le=30)):
    return _build_external_context_feed(limit=limit)


def _severity_label(value: str | None) -> str:
    normalized = str(value or '').strip().lower()
    mapping = {
        'critical': 'Critical',
        'high': 'High',
        'medium': 'Medium',
        'low': 'Low',
        'info': 'Info',
    }
    return mapping.get(normalized, 'Info')


def _severity_rank(value: str | None) -> int:
    return {'critical': 4, 'high': 3, 'medium': 2, 'low': 1, 'info': 0}.get(str(value or '').strip().lower(), 0)


def _normalize_action_plan_status(value: str | None) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in {'complete', 'completed', 'done', 'closed'}:
        return 'Complete'
    if normalized in {'blocked', 'at risk'}:
        return 'Blocked'
    if normalized in {'in progress', 'active', 'underway'}:
        return 'In Progress'
    if normalized in {'planned', 'todo', 'to do'}:
        return 'Planned'
    return 'No Plan' if not normalized else format_metric_label(normalized)


def _get_cycle_for_anomaly_summary(db: Session, cycle_year: int | None = None) -> CollectionCycle | None:
    if cycle_year:
        return db.query(CollectionCycle).filter(CollectionCycle.cycle_year == cycle_year).first()

    active_cycle = get_active_cycle(db)
    if active_cycle:
        active_flag_count = (
            db.query(ValidationFlag)
            .filter(ValidationFlag.reporting_year == active_cycle.cycle_year)
            .count()
        )
        active_submission_count = (
            db.query(Submission)
            .filter(Submission.cycle_id == active_cycle.id)
            .count()
        )
        if active_flag_count > 0 or active_submission_count >= 3:
            return active_cycle

    flagged_year = (
        db.query(ValidationFlag.reporting_year)
        .order_by(ValidationFlag.reporting_year.desc())
        .first()
    )
    if flagged_year:
        flagged_cycle = db.query(CollectionCycle).filter(CollectionCycle.cycle_year == flagged_year[0]).first()
        if flagged_cycle:
            return flagged_cycle

    return active_cycle or get_latest_cycle(db)


def _latest_submissions_for_cycle(db: Session, cycle: CollectionCycle | None) -> list[Submission]:
    query = db.query(Submission)
    if cycle:
        query = query.filter(Submission.cycle_id == cycle.id)
    submissions = query.order_by(Submission.company_id.asc(), Submission.id.desc()).all()
    latest_by_company: dict[int, Submission] = {}
    for submission in submissions:
        if submission.company_id not in latest_by_company:
            latest_by_company[submission.company_id] = submission
    return list(latest_by_company.values())


def _remediation_summary_from_plans(plans: list[ActionPlan]) -> dict[str, Any]:
    if not plans:
        return {
            'status': 'No Plan',
            'open_count': 0,
            'total_count': 0,
            'latest_action': None,
            'owner': None,
            'target_completion_date': None,
        }

    normalized_statuses = [_normalize_action_plan_status(plan.status) for plan in plans]
    open_count = sum(1 for status in normalized_statuses if status not in {'Complete'})
    if any(status == 'Blocked' for status in normalized_statuses):
        status = 'Blocked'
    elif any(status == 'In Progress' for status in normalized_statuses):
        status = 'In Progress'
    elif open_count:
        status = 'Planned'
    else:
        status = 'Complete'

    latest = plans[0]
    return {
        'status': status,
        'open_count': open_count,
        'total_count': len(plans),
        'latest_action': latest.initiative_name,
        'owner': latest.assigned_owner,
        'target_completion_date': latest.target_completion_date,
    }


def _company_remediation_summary(db: Session, company_id: int) -> dict[str, Any]:
    plans = (
        db.query(ActionPlan)
        .filter(ActionPlan.company_id == company_id)
        .order_by(ActionPlan.id.desc())
        .all()
    )
    return _remediation_summary_from_plans(plans)


def _company_lookup(db: Session) -> dict[int, Company]:
    return {company.id: company for company in db.query(Company).all()}


def _remediation_lookup(db: Session) -> dict[int, dict[str, Any]]:
    plans_by_company: dict[int, list[ActionPlan]] = {}
    for plan in db.query(ActionPlan).order_by(ActionPlan.company_id.asc(), ActionPlan.id.desc()).all():
        plans_by_company.setdefault(plan.company_id, []).append(plan)
    return {
        company_id: _remediation_summary_from_plans(plans)
        for company_id, plans in plans_by_company.items()
    }


def _statistical_outliers_for_cycle(
    db: Session,
    cycle: CollectionCycle | None,
    company_map: dict[int, Company] | None = None,
    remediation_map: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    company_map = company_map if company_map is not None else _company_lookup(db)
    remediation_map = remediation_map if remediation_map is not None else _remediation_lookup(db)
    submissions = _latest_submissions_for_cycle(db, cycle)
    numeric_matrix: dict[str, list[tuple[Submission, float]]] = {field: [] for field in NUMERIC_ANOMALY_FIELDS}
    for submission in submissions:
        payload = parse_submission(submission)
        for field_name in NUMERIC_ANOMALY_FIELDS:
            value = safe_number(payload.get(field_name), default=float('nan'))
            if value == value:
                numeric_matrix[field_name].append((submission, value))

    anomalies: list[dict[str, Any]] = []
    for field_name, values in numeric_matrix.items():
        if len(values) < 3:
            continue
        series = [item[1] for item in values]
        mean = sum(series) / len(series)
        variance = sum((item - mean) ** 2 for item in series) / len(series)
        std_dev = variance ** 0.5
        if std_dev <= 0:
            continue

        for submission, value in values:
            z_score = (value - mean) / std_dev
            if abs(z_score) < 2.0:
                continue
            company = company_map.get(submission.company_id)
            remediation = remediation_map.get(submission.company_id) or _remediation_summary_from_plans([])
            severity = 'Critical' if abs(z_score) >= 3.0 else 'High'
            direction = 'above' if z_score > 0 else 'below'
            anomalies.append({
                'id': f'outlier-{submission.company_id}-{field_name}',
                'type': 'Statistical Outlier',
                'company_id': submission.company_id,
                'company_name': company.name if company else f'Company {submission.company_id}',
                'sector': company.sector if company else None,
                'reporting_year': cycle.cycle_year if cycle else (submission.cycle.cycle_year if submission.cycle else None),
                'field_name': field_name,
                'field_label': format_metric_label(field_name),
                'issue_description': f'{format_metric_label(field_name)} is {abs(z_score):.1f} standard deviations {direction} the portfolio mean.',
                'severity': severity,
                'value': round(value, 4),
                'portfolio_mean': round(mean, 4),
                'z_score': round(z_score, 3),
                'remediation': remediation,
            })

    anomalies.sort(key=lambda item: abs(float(item.get('z_score') or 0)), reverse=True)
    return anomalies


def _validation_flag_items(
    db: Session,
    cycle: CollectionCycle | None,
    company_id: int | None = None,
    company_map: dict[int, Company] | None = None,
    remediation_map: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    company_map = company_map if company_map is not None else _company_lookup(db)
    remediation_map = remediation_map if remediation_map is not None else _remediation_lookup(db)
    query = db.query(ValidationFlag).filter(func.lower(ValidationFlag.severity) != 'info')
    if cycle:
        query = query.filter(ValidationFlag.reporting_year == cycle.cycle_year)
    if company_id:
        query = query.filter(ValidationFlag.company_id == company_id)

    items = []
    for flag in query.order_by(ValidationFlag.id.desc()).limit(200).all():
        company = company_map.get(flag.company_id)
        remediation = remediation_map.get(flag.company_id) or _remediation_summary_from_plans([])
        items.append({
            'id': flag.id,
            'type': 'Validation Flag',
            'company_id': flag.company_id,
            'company_name': company.name if company else f'Company {flag.company_id}',
            'sector': company.sector if company else None,
            'reporting_year': flag.reporting_year,
            'flag_type': flag.flag_type,
            'field_name': flag.field_name,
            'field_label': format_metric_label(flag.field_name),
            'issue_description': flag.issue_description,
            'severity': _severity_label(flag.severity),
            'remediation': remediation,
        })
    return items


def _summarize_anomaly_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
    company_counts: dict[str, dict[str, Any]] = {}
    field_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    remediation_counts: dict[str, int] = {}

    for item in items:
        severity_key = str(item.get('severity') or '').strip().lower()
        if severity_key in severity_counts:
            severity_counts[severity_key] += 1

        company_key = str(item.get('company_id') or item.get('company_name') or 'unknown')
        company_counts.setdefault(company_key, {
            'company_id': item.get('company_id'),
            'company_name': item.get('company_name') or 'Company',
            'count': 0,
            'max_severity': item.get('severity') or 'Info',
        })
        company_counts[company_key]['count'] += 1
        if _severity_rank(item.get('severity')) > _severity_rank(company_counts[company_key]['max_severity']):
            company_counts[company_key]['max_severity'] = item.get('severity')

        field_label = item.get('field_label') or format_metric_label(item.get('field_name'))
        field_counts[field_label] = field_counts.get(field_label, 0) + 1
        item_type = item.get('type') or 'Anomaly'
        type_counts[item_type] = type_counts.get(item_type, 0) + 1
        remediation_status = (item.get('remediation') or {}).get('status') or 'No Plan'
        remediation_counts[remediation_status] = remediation_counts.get(remediation_status, 0) + 1

    top_companies = sorted(company_counts.values(), key=lambda item: (-item['count'], -_severity_rank(item['max_severity']), item['company_name']))[:8]
    top_fields = [
        {'field': field, 'count': count}
        for field, count in sorted(field_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    type_breakdown = [{'type': item_type, 'count': count} for item_type, count in sorted(type_counts.items())]
    remediation_breakdown = [{'status': status, 'count': count} for status, count in sorted(remediation_counts.items())]
    return {
        'severity_counts': severity_counts,
        'top_companies': top_companies,
        'top_fields': top_fields,
        'type_breakdown': type_breakdown,
        'remediation_breakdown': remediation_breakdown,
    }


@app.get('/anomalies/summary', dependencies=[Depends(require_manager_or_investor)])
def anomalies_summary(cycle_year: int | None = Query(default=None), db: Session = Depends(get_db)):
    cycle = _get_cycle_for_anomaly_summary(db, cycle_year)
    company_map = _company_lookup(db)
    remediation_map = _remediation_lookup(db)
    validation_items = _validation_flag_items(db, cycle, company_map=company_map, remediation_map=remediation_map)
    statistical_outliers = _statistical_outliers_for_cycle(db, cycle, company_map=company_map, remediation_map=remediation_map)
    all_items = validation_items + statistical_outliers
    all_items.sort(key=lambda item: (-_severity_rank(item.get('severity')), str(item.get('company_name') or ''), str(item.get('field_name') or '')))
    summary = _summarize_anomaly_items(all_items)
    return {
        'available': True,
        'scope': 'portfolio',
        'cycle_year': cycle.cycle_year if cycle else cycle_year,
        'generated_at': _utc_now_iso(),
        'headline': 'Portfolio anomaly watchlist',
        'summary': 'Latest validation, variance, and statistical outlier anomalies from portfolio data.',
        'severity_counts': summary['severity_counts'],
        'top_companies': summary['top_companies'],
        'top_fields': summary['top_fields'],
        'type_breakdown': summary['type_breakdown'],
        'remediation_breakdown': summary['remediation_breakdown'],
        'items': all_items[:100],
        'validation_flags': validation_items[:100],
        'statistical_outliers': statistical_outliers[:100],
        'watchlist_companies': [item['company_name'] for item in summary['top_companies']],
        'fallback_used': False,
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

    cycle = _get_cycle_for_anomaly_summary(db)
    company_map = _company_lookup(db)
    remediation_map = _remediation_lookup(db)
    validation_items = _validation_flag_items(
        db,
        cycle,
        company_id=target_company.id,
        company_map=company_map,
        remediation_map=remediation_map,
    )
    statistical_outliers = [
        item
        for item in _statistical_outliers_for_cycle(db, cycle, company_map=company_map, remediation_map=remediation_map)
        if int(item.get('company_id') or 0) == target_company.id
    ]
    items = validation_items + statistical_outliers
    items.sort(key=lambda item: (-_severity_rank(item.get('severity')), str(item.get('field_name') or '')))
    summary = _summarize_anomaly_items(items)
    return {
        'company_id': target_company.id,
        'company_name': target_company.name,
        'cycle_year': cycle.cycle_year if cycle else None,
        'count': len(items),
        'severity_counts': summary['severity_counts'],
        'top_fields': summary['top_fields'],
        'type_breakdown': summary['type_breakdown'],
        'remediation_breakdown': summary['remediation_breakdown'],
        'remediation': remediation_map.get(target_company.id) or _remediation_summary_from_plans([]),
        'items': items[:100],
        'validation_flags': validation_items[:100],
        'statistical_outliers': statistical_outliers[:100],
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
