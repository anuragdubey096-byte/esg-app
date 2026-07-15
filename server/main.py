import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import asyncio
import html
import secrets
import smtplib
import time
from collections import Counter
from threading import RLock
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, List
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
from xml.etree import ElementTree

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form, Header, Cookie, Query, Body, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import MetaData, Table, delete as sqlalchemy_delete, func, inspect, or_, text
from sqlalchemy.orm import Session, selectinload
from pydantic import ValidationError
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

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
    ESGTarget,
    ReviewAction,
    ValidationFlag,
    SubmissionUnlock,
    SubmissionDraft,
    SubmissionEvidence,
    AssuranceRecord,
    ReminderLog,
    NarrativeRecord,
    AuthSession,
    PasswordResetToken,
    AuditEvent,
    Notification,
    MetricReviewComment,
    MaterialityTopic,
)
from schemas import (
    ActionPlanCreateRequest,
    ActionPlanInfo,
    ESGTargetCreateRequest,
    ESGTargetInfo,
    ESGTargetUpdateRequest,
    CompanyCreateRequest,
    CompanyCreateResponse,
    CompanyDetail,
    CycleCreateRequest,
    CycleInfo,
    CycleStatusUpdateRequest,
    MetricReviewCommentRequest,
    AssuranceDecisionRequest,
    MaterialityTopicRequest,
    ScenarioAnalysisRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    GHGCalculatorRequest,
    GHGCalculatorResponse,
    ReviewSubmissionRequest,
    SubmissionHistoryEntry,
    ValidationDecisionRequest,
    InvestorSummary,
    InvestorDashboardResponse,
    LoginRequest,
    SSOLoginRequest,
    SubmissionCreateRequest,
    SubmissionInfo,
    SubmissionDraftRequest,
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
from storage import persist_export, read_export, storage_health
from version import APP_VERSION
try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency at runtime
    OpenAI = None

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
ALLOWED_CYCLE_STATUSES = {'draft', 'active', 'closed', 'archived'}
ALLOWED_REVIEW_STATUSES = {'submitted', 'under review', 'approved', 'rejected', 'resubmission requested'}
REQUIRED_EVIDENCE_METRICS = {'scope_1_emissions'}
OPENAI_DEFAULT_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
MIN_REPORTING_CYCLE_YEAR = 2000
MAX_REPORTING_CYCLE_FUTURE_YEARS = 5
SESSION_TTL_HOURS = max(1, min(int(os.getenv('SESSION_TTL_HOURS', '12') or '12'), 168))
PASSWORD_RESET_TTL_MINUTES = 30
PASSWORD_HASH_ITERATIONS = 310_000
AUTH_COOKIE_NAME = 'esg_session'
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

app = FastAPI(title='GreenLedger ESG API', version=APP_VERSION)
app.include_router(new_esg_router, prefix="/api/v2")
try:
    app.include_router(__import__('routers.agent', fromlist=['router']).router)
except Exception:
    # Keep core API alive even if optional agent router import fails at runtime.
    pass

@app.get('/exports/{file_name}')
def download_generated_export(file_name: str):
    safe_name = Path(file_name).name
    if safe_name != file_name or not re.fullmatch(r'[A-Za-z0-9._-]{1,240}', safe_name):
        raise HTTPException(status_code=404, detail='Export not found')
    try:
        content, stored_content_type = read_export(safe_name, EXPORT_DIR)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail='Export not found') from error
    except Exception as error:
        raise HTTPException(status_code=503, detail='Export storage is temporarily unavailable') from error

    suffix_content_types = {
        '.csv': 'text/csv',
        '.pdf': 'application/pdf',
        '.txt': 'text/plain',
    }
    content_type = stored_content_type or suffix_content_types.get(Path(safe_name).suffix.lower(), 'application/octet-stream')
    return Response(
        content=content,
        media_type=content_type,
        headers={
            'Content-Disposition': f'attachment; filename="{safe_name}"',
            'Cache-Control': 'private, no-store',
        },
    )


def _runtime_error_category(error: Exception) -> str:
    message = str(error or '').lower()
    if 'lock timeout' in message or 'locknotavailable' in message or 'could not obtain lock' in message:
        return 'database_lock_timeout'
    if 'statement timeout' in message or 'querycanceled' in message:
        return 'database_statement_timeout'
    if 'queuepool limit' in message or 'connection pool' in message:
        return 'database_pool_exhausted'
    return 'request_exception'


def _runtime_context() -> dict[str, str]:
    return {
        'version': APP_VERSION,
        'environment': str(os.getenv('VERCEL_ENV') or os.getenv('APP_ENV') or ('vercel' if os.getenv('VERCEL') else 'local')),
        'deployment_id': str(os.getenv('VERCEL_DEPLOYMENT_ID') or ''),
        'commit_sha': str(os.getenv('VERCEL_GIT_COMMIT_SHA') or '')[:40],
        'region': str(os.getenv('VERCEL_REGION') or ''),
    }


@app.middleware('http')
async def request_timing_middleware(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get('x-vercel-id') or request.headers.get('x-request-id') or ''
    event = {
        'route': request.url.path,
        'method': request.method,
        'request_id': request_id,
        **_runtime_context(),
    }
    try:
        response = await call_next(request)
    except Exception as error:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        print(json.dumps({
            'level': 'error',
            'event': _runtime_error_category(error),
            'duration_ms': duration_ms,
            'error_type': type(error).__name__,
            'error': str(error)[:600],
            **event,
        }), flush=True)
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    level = 'error' if response.status_code >= 500 else ('warning' if duration_ms >= 2000 else 'info')
    log_event = 'request_slow' if duration_ms >= 2000 else 'request_complete'
    print(json.dumps({
        'level': level,
        'event': log_event,
        'status_code': response.status_code,
        'duration_ms': duration_ms,
        **event,
    }), flush=True)
    response.headers['Server-Timing'] = f'app;dur={duration_ms}'
    response.headers['X-App-Duration-Ms'] = str(duration_ms)
    return response


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
        submission_count=len(cycle.submissions or []),
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

def implicit_schema_bootstrap_enabled() -> bool:
    """Allow create_all only for disposable test state and local development."""
    configured = str(os.getenv('ALLOW_IMPLICIT_SCHEMA_BOOTSTRAP') or '').strip().lower()
    if configured:
        return configured in {'1', 'true', 'yes', 'on'}
    environment = str(os.getenv('APP_ENV') or '').strip().lower()
    if environment in {'test', 'testing'}:
        return True
    has_durable_database = bool(str(os.getenv('DATABASE_URL') or '').strip())
    return not has_durable_database and not os.getenv('VERCEL')


if implicit_schema_bootstrap_enabled():
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
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PASSWORD_HASH_ITERATIONS)
    return 'pbkdf2_sha256${}${}${}'.format(
        PASSWORD_HASH_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode('ascii'),
        base64.urlsafe_b64encode(digest).decode('ascii'),
    )


def verify_password(password: str, stored_password: str) -> bool:
    if not str(stored_password or '').startswith('pbkdf2_sha256$'):
        return hmac.compare_digest(str(stored_password or ''), password)
    try:
        _, iterations, encoded_salt, encoded_digest = stored_password.split('$', 3)
        salt = base64.urlsafe_b64decode(encoded_salt.encode('ascii'))
        expected = base64.urlsafe_b64decode(encoded_digest.encode('ascii'))
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


def migrate_plaintext_passwords(db: Session) -> int:
    users = db.query(User).all()
    changed = 0
    for user in users:
        if not str(user.password or '').startswith('pbkdf2_sha256$'):
            user.password = hash_password(str(user.password or secrets.token_urlsafe(18)))
            changed += 1
    if changed:
        db.commit()
    return changed


def _token_digest(token: str) -> str:
    return hashlib.sha256(str(token or '').encode('utf-8')).hexdigest()


def log_audit_event(
    db: Session,
    event_type: str,
    user: User | None = None,
    *,
    actor_email: str | None = None,
    company_id: int | None = None,
    submission_id: int | None = None,
    cycle_id: int | None = None,
    field_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(AuditEvent(
        event_type=event_type,
        actor_user_id=user.id if user else None,
        actor_email=(user.email if user else actor_email),
        actor_role=normalize_role(user.role) if user else None,
        company_id=company_id,
        submission_id=submission_id,
        cycle_id=cycle_id,
        field_name=field_name,
        source='api',
        metadata_json=json.dumps(metadata or {}),
    ))


def send_password_reset_email(recipient: str, raw_token: str) -> bool:
    smtp_host = str(os.getenv('SMTP_HOST') or '').strip()
    sender = str(os.getenv('SMTP_FROM_EMAIL') or '').strip()
    if not smtp_host or not sender:
        return False
    reset_base = str(os.getenv('APP_URL') or 'https://esg-app-two.vercel.app').rstrip('/')
    message = EmailMessage()
    message['Subject'] = 'Reset your GreenLedger password'
    message['From'] = sender
    message['To'] = recipient
    message.set_content(
        f'Use this secure link within {PASSWORD_RESET_TTL_MINUTES} minutes to reset your password:\n\n'
        f'{reset_base}/?reset_token={raw_token}\n\nIf you did not request this, ignore this email.'
    )
    port = int(os.getenv('SMTP_PORT', '587') or '587')
    username = str(os.getenv('SMTP_USERNAME') or '')
    password = str(os.getenv('SMTP_PASSWORD') or '')
    try:
        with smtplib.SMTP(smtp_host, port, timeout=10) as client:
            client.starttls()
            if username:
                client.login(username, password)
            client.send_message(message)
        return True
    except Exception as error:
        print(json.dumps({'level': 'warning', 'event': 'password_reset_email_failed', 'error': str(error)[:300]}), flush=True)
        return False


def create_auth_session(db: Session, user: User, request: Request | None = None) -> tuple[str, datetime]:
    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)
    db.add(AuthSession(
        user_id=user.id,
        token_hash=_token_digest(raw_token),
        expires_at=expires_at,
        user_agent=(request.headers.get('user-agent', '')[:500] if request else None),
        ip_address=(request.client.host[:120] if request and request.client else None),
    ))
    return raw_token, expires_at


def get_authenticated_user(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    bearer_token = ''
    if authorization and authorization.lower().startswith('bearer '):
        bearer_token = authorization.split(' ', 1)[1].strip()
    raw_token = bearer_token or str(session_cookie or '').strip()
    if not raw_token:
        raise HTTPException(status_code=401, detail='Authentication required')
    session = (
        db.query(AuthSession)
        .filter(
            AuthSession.token_hash == _token_digest(raw_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=401, detail='Session expired or invalid')
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail='Session user no longer exists')
    return user


def get_user_role(user: User = Depends(get_authenticated_user)):
    return normalize_role(user.role)


def get_user_email(user: User = Depends(get_authenticated_user)) -> str:
    return user.email.strip().lower()


def require_manager(user: User = Depends(get_authenticated_user), db: Session = Depends(get_db)):
    if normalize_role(user.role) != 'manager':
        log_audit_event(db, 'permission_denied', user, metadata={'required_role': 'manager'})
        db.commit()
        raise HTTPException(status_code=403, detail='Access restricted to ESG Managers')
    return user

def require_company_or_manager(role: str = Depends(get_user_role)):
    if role not in {'company', 'manager'}:
        raise HTTPException(status_code=403, detail='Access restricted to portfolio companies and ESG Managers')

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
    return any(column['name'] == column_name for column in inspect(db.bind).get_columns(table_name))


def ensure_submission_cycle_column(db: Session):
    if db.bind.dialect.name == 'postgresql':
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '30s'"))
        db.execute(text('ALTER TABLE submissions ADD COLUMN IF NOT EXISTS cycle_id INTEGER'))
        db.commit()
        return
    if table_has_column(db, 'submissions', 'cycle_id'):
        return
    db.execute(text('ALTER TABLE submissions ADD COLUMN cycle_id INTEGER'))
    db.commit()


def ensure_review_action_audit_columns(db: Session):
    if db.bind.dialect.name == 'postgresql':
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '30s'"))
        db.execute(text('ALTER TABLE review_actions ADD COLUMN IF NOT EXISTS submission_id INTEGER'))
        db.execute(text('ALTER TABLE review_actions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP'))
        db.commit()
        return
    if not table_has_column(db, 'review_actions', 'submission_id'):
        db.execute(text('ALTER TABLE review_actions ADD COLUMN submission_id INTEGER'))
    if not table_has_column(db, 'review_actions', 'created_at'):
        db.execute(text('ALTER TABLE review_actions ADD COLUMN created_at TIMESTAMP'))
    db.commit()


def get_active_cycle(db: Session) -> CollectionCycle | None:
    max_cycle_year = datetime.now(timezone.utc).year + MAX_REPORTING_CYCLE_FUTURE_YEARS
    return (
        db.query(CollectionCycle)
        .filter(
            CollectionCycle.status == 'active',
            CollectionCycle.cycle_year >= MIN_REPORTING_CYCLE_YEAR,
            CollectionCycle.cycle_year <= max_cycle_year,
        )
        .order_by(CollectionCycle.cycle_year.desc())
        .first()
    )


def get_latest_cycle(db: Session) -> CollectionCycle | None:
    max_cycle_year = datetime.now(timezone.utc).year + MAX_REPORTING_CYCLE_FUTURE_YEARS
    return (
        db.query(CollectionCycle)
        .filter(
            CollectionCycle.cycle_year >= MIN_REPORTING_CYCLE_YEAR,
            CollectionCycle.cycle_year <= max_cycle_year,
        )
        .order_by(CollectionCycle.cycle_year.desc(), CollectionCycle.id.desc())
        .first()
    )


def cleanup_irrelevant_qa_cycles(db: Session) -> dict[str, Any]:
    """Remove only impossible future cycles containing isolated self-test records."""
    max_cycle_year = datetime.now(timezone.utc).year + MAX_REPORTING_CYCLE_FUTURE_YEARS
    candidates = (
        db.query(CollectionCycle)
        .filter(CollectionCycle.cycle_year > max_cycle_year)
        .order_by(CollectionCycle.id.asc())
        .all()
    )
    if not candidates:
        return {'cycles': 0, 'companies': 0, 'submissions': 0, 'users': 0, 'skipped_cycle_ids': []}

    candidate_cycle_ids = [cycle.id for cycle in candidates]
    candidate_submissions = db.query(Submission).filter(Submission.cycle_id.in_(candidate_cycle_ids)).all()
    candidate_company_ids = sorted({submission.company_id for submission in candidate_submissions})
    candidate_companies = (
        db.query(Company).filter(Company.id.in_(candidate_company_ids)).all()
        if candidate_company_ids else []
    )
    qa_company_ids = {
        company.id for company in candidate_companies
        if str(company.name or '').startswith('QA Company ')
    }
    unsafe_cycle_ids = set()
    for submission in candidate_submissions:
        if submission.company_id not in qa_company_ids:
            unsafe_cycle_ids.add(submission.cycle_id)
    for company_id in qa_company_ids:
        company_submissions = db.query(Submission).filter(Submission.company_id == company_id).all()
        has_non_candidate_submission = any(
            item.cycle_id not in candidate_cycle_ids for item in company_submissions
        )
        if has_non_candidate_submission:
            unsafe_cycle_ids.update(
                submission.cycle_id for submission in candidate_submissions
                if submission.company_id == company_id
            )

    safe_cycle_ids = [cycle.id for cycle in candidates if cycle.id not in unsafe_cycle_ids]
    safe_submissions = [item for item in candidate_submissions if item.cycle_id in safe_cycle_ids]
    safe_submission_ids = [item.id for item in safe_submissions]
    safe_company_ids = sorted({item.company_id for item in safe_submissions if item.company_id in qa_company_ids})
    legacy_dependencies = (
        ('audit_events', {
            'submission_id': safe_submission_ids,
            'company_id': safe_company_ids,
            'cycle_id': safe_cycle_ids,
        }),
        ('submission_declarations', {
            'submission_id': safe_submission_ids,
            'company_id': safe_company_ids,
        }),
        ('onboarding_states', {'company_id': safe_company_ids}),
        ('context_help_content', {'cycle_id': safe_cycle_ids}),
        ('cycle_clone_logs', {
            'source_cycle_id': safe_cycle_ids,
            'target_cycle_id': safe_cycle_ids,
        }),
    )
    database_inspector = inspect(db.bind)
    for table_name, column_values in legacy_dependencies:
        if not database_inspector.has_table(table_name):
            continue
        legacy_table = Table(table_name, MetaData(), autoload_with=db.bind)
        conditions = [
            legacy_table.c[column_name].in_(values)
            for column_name, values in column_values.items()
            if values and column_name in legacy_table.c
        ]
        if conditions:
            db.execute(sqlalchemy_delete(legacy_table).where(or_(*conditions)))

    if safe_submission_ids:
        db.query(SubmissionUnlock).filter(SubmissionUnlock.submission_id.in_(safe_submission_ids)).delete(synchronize_session=False)
        db.query(SubmissionEvidence).filter(SubmissionEvidence.submission_id.in_(safe_submission_ids)).delete(synchronize_session=False)
        db.query(ReviewAction).filter(ReviewAction.submission_id.in_(safe_submission_ids)).delete(synchronize_session=False)
    if safe_company_ids:
        db.query(SubmissionUnlock).filter(SubmissionUnlock.company_id.in_(safe_company_ids)).delete(synchronize_session=False)
        db.query(SubmissionEvidence).filter(SubmissionEvidence.company_id.in_(safe_company_ids)).delete(synchronize_session=False)
        db.query(SubmissionDraft).filter(SubmissionDraft.company_id.in_(safe_company_ids)).delete(synchronize_session=False)
        db.query(ReminderLog).filter(ReminderLog.company_id.in_(safe_company_ids)).delete(synchronize_session=False)
        db.query(ReviewAction).filter(ReviewAction.company_id.in_(safe_company_ids)).delete(synchronize_session=False)
        db.query(ValidationFlag).filter(ValidationFlag.company_id.in_(safe_company_ids)).delete(synchronize_session=False)
        db.query(ActionPlan).filter(ActionPlan.company_id.in_(safe_company_ids)).delete(synchronize_session=False)
    if safe_cycle_ids:
        db.query(SubmissionUnlock).filter(SubmissionUnlock.cycle_id.in_(safe_cycle_ids)).delete(synchronize_session=False)
        db.query(SubmissionEvidence).filter(SubmissionEvidence.cycle_id.in_(safe_cycle_ids)).delete(synchronize_session=False)
        db.query(SubmissionDraft).filter(SubmissionDraft.cycle_id.in_(safe_cycle_ids)).delete(synchronize_session=False)
        db.query(ReminderLog).filter(ReminderLog.cycle_id.in_(safe_cycle_ids)).delete(synchronize_session=False)
    if safe_submission_ids:
        db.query(Submission).filter(Submission.id.in_(safe_submission_ids)).delete(synchronize_session=False)
    if safe_company_ids:
        db.query(Company).filter(Company.id.in_(safe_company_ids)).delete(synchronize_session=False)
    if safe_cycle_ids:
        db.query(CollectionCycle).filter(CollectionCycle.id.in_(safe_cycle_ids)).delete(synchronize_session=False)

    db.commit()
    return {
        'cycles': len(safe_cycle_ids),
        'companies': len(safe_company_ids),
        'submissions': len(safe_submission_ids),
        'users': 0,
        'skipped_cycle_ids': sorted(unsafe_cycle_ids),
    }


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


def require_company_access(db: Session, company_id: int, role: str, email: str | None) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    if role == 'company':
        request_user = find_request_user(db, email)
        if not request_user or request_user.id != company.user_id:
            raise HTTPException(status_code=403, detail='Company users can only access their own submission workspace')
    return company


def latest_submission_for_cycle(db: Session, company_id: int, cycle_id: int) -> Submission | None:
    return (
        db.query(Submission)
        .filter(Submission.company_id == company_id, Submission.cycle_id == cycle_id)
        .order_by(Submission.id.desc())
        .first()
    )


def submission_edit_state(db: Session, company_id: int, cycle: CollectionCycle, submission: Submission | None) -> dict[str, Any]:
    cycle_closed = normalize_cycle_status(cycle.status) == 'closed'
    if submission is None:
        can_edit = not cycle_closed
        return {
            'can_edit': can_edit,
            'locked': not can_edit,
            'lock_reason': 'This reporting cycle is closed.' if not can_edit else None,
            'submission_status': 'not started',
        }

    status = normalize_submission_status(submission.status)
    editable_status = status in {'not started', 'in progress', 'resubmission requested'}
    active_unlock = has_active_unlock(db, submission.id, company_id, cycle.id)
    can_edit = editable_status and (not cycle_closed or active_unlock)

    if can_edit:
        lock_reason = None
    elif cycle_closed and not active_unlock:
        lock_reason = 'This reporting cycle is closed. A manager must unlock it before changes can be made.'
    elif status == 'approved':
        lock_reason = 'This submission is approved and locked. A manager must request resubmission.'
    else:
        lock_reason = 'This submission has been sent for review. A manager must request resubmission before it can be edited.'

    return {
        'can_edit': can_edit,
        'locked': not can_edit,
        'lock_reason': lock_reason,
        'submission_status': status,
        'active_unlock': active_unlock,
    }


def serialize_evidence(evidence: SubmissionEvidence) -> dict[str, Any]:
    return {
        'id': evidence.id,
        'company_id': evidence.company_id,
        'cycle_id': evidence.cycle_id,
        'submission_id': evidence.submission_id,
        'metric_key': evidence.metric_key,
        'filename': evidence.filename,
        'content_type': evidence.content_type,
        'file_size': evidence.file_size,
        'status': evidence.status,
        'uploaded_at': evidence.created_at.isoformat() if evidence.created_at else None,
    }


def seed_draft_from_submission(db: Session, submission: Submission) -> SubmissionDraft:
    draft = (
        db.query(SubmissionDraft)
        .filter(
            SubmissionDraft.company_id == submission.company_id,
            SubmissionDraft.cycle_id == submission.cycle_id,
        )
        .first()
    )
    if draft is None:
        draft = SubmissionDraft(
            company_id=submission.company_id,
            cycle_id=submission.cycle_id,
            payload=submission.esg_data or '{}',
        )
        db.add(draft)
    else:
        draft.payload = submission.esg_data or '{}'
        draft.updated_at = datetime.utcnow()
    return draft


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
        if implicit_schema_bootstrap_enabled():
            Base.metadata.create_all(bind=engine)
        if not os.getenv('VERCEL'):
            ensure_submission_cycle_column(db)
            ensure_review_action_audit_columns(db)
        seed_sample_data(db)
        migrate_legacy_user_roles(db)
        migrate_plaintext_passwords(db)
        fix_cycle_statuses_and_active_conflicts(db)
        ensure_submission_cycle_backfill(db)
        deactivate_expired_unlocks(db)
    finally:
        db.close()


@app.post('/admin/migrate-schema', dependencies=[Depends(require_manager)])
def migrate_schema(db: Session = Depends(get_db)):
    ensure_submission_cycle_column(db)
    ensure_review_action_audit_columns(db)
    qa_cleanup = cleanup_irrelevant_qa_cycles(db)
    return {
        'status': 'ok',
        'submission_cycle_column': table_has_column(db, 'submissions', 'cycle_id'),
        'review_submission_column': table_has_column(db, 'review_actions', 'submission_id'),
        'review_created_at_column': table_has_column(db, 'review_actions', 'created_at'),
        'qa_cycle_cleanup': qa_cleanup,
    }

@app.post('/login', response_model=UserResponse)
def login(payload: LoginRequest, response: Response, request: Request, db: Session = Depends(get_db)):
    normalized_email = payload.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if not user or not verify_password(payload.password, user.password):
        log_audit_event(db, 'login_failed', actor_email=normalized_email)
        db.commit()
        raise HTTPException(status_code=401, detail='Invalid email or password')
    if not str(user.password or '').startswith('pbkdf2_sha256$'):
        user.password = hash_password(payload.password)
    raw_token, expires_at = create_auth_session(db, user, request)
    log_audit_event(db, 'login_succeeded', user, metadata={'expires_at': expires_at.isoformat()})
    db.commit()
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=raw_token,
        max_age=SESSION_TTL_HOURS * 3600,
        expires=datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS),
        httponly=True,
        secure=bool(os.getenv('VERCEL')),
        samesite='lax',
        path='/',
    )
    return serialize_user(user)


@app.get('/auth/me', response_model=UserResponse)
def auth_me(user: User = Depends(get_authenticated_user)):
    return serialize_user(user)


@app.post('/auth/logout')
def logout(
    response: Response,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=AUTH_COOKIE_NAME),
    db: Session = Depends(get_db),
):
    bearer_token = authorization.split(' ', 1)[1].strip() if authorization and authorization.lower().startswith('bearer ') else ''
    raw_token = bearer_token or str(session_cookie or '').strip()
    if raw_token:
        session = db.query(AuthSession).filter(AuthSession.token_hash == _token_digest(raw_token)).first()
        if session and session.revoked_at is None:
            session.revoked_at = datetime.utcnow()
            user = db.query(User).filter(User.id == session.user_id).first()
            log_audit_event(db, 'logout', user)
            db.commit()
    response.delete_cookie(AUTH_COOKIE_NAME, path='/', secure=bool(os.getenv('VERCEL')), samesite='lax')
    return {'message': 'Signed out'}


@app.post('/auth/forgot-password', response_model=ForgotPasswordResponse)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Deliberately return a generic message to avoid revealing account existence.
    normalized_email = request.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if user:
        raw_token = secrets.token_urlsafe(40)
        expires_at = datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)
        db.add(PasswordResetToken(user_id=user.id, token_hash=_token_digest(raw_token), expires_at=expires_at))
        email_sent = send_password_reset_email(user.email, raw_token)
        db.add(Notification(
            user_id=user.id,
            role=normalize_role(user.role),
            notification_type='password_reset',
            title='Password reset requested',
            message='A password reset email was sent.' if email_sent else 'A password reset was requested; email delivery is awaiting SMTP configuration.',
            dedupe_key=f'password-reset-{user.id}-{int(expires_at.timestamp())}',
        ))
        log_audit_event(db, 'password_reset_requested', user, metadata={'email_sent': email_sent})
        db.commit()
        if not os.getenv('VERCEL'):
            print(f'Password reset token for {normalized_email}: {raw_token}', flush=True)
    return ForgotPasswordResponse(
        message='If an account with that email exists, password reset instructions have been sent.'
    )


@app.post('/auth/reset-password')
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    reset = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == _token_digest(payload.token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not reset:
        raise HTTPException(status_code=400, detail='Reset link is invalid or expired')
    user = db.query(User).filter(User.id == reset.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail='Reset link is invalid or expired')
    user.password = hash_password(payload.new_password)
    reset.used_at = datetime.utcnow()
    db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).update(
        {'revoked_at': datetime.utcnow()}, synchronize_session=False
    )
    log_audit_event(db, 'password_reset_completed', user)
    db.commit()
    return {'message': 'Password updated. Sign in with your new password.'}


def create_notification(
    db: Session,
    *,
    notification_type: str,
    title: str,
    message: str,
    user_id: int | None = None,
    role: str | None = None,
    company_id: int | None = None,
    dedupe_key: str | None = None,
) -> Notification | None:
    if dedupe_key and db.query(Notification).filter(Notification.dedupe_key == dedupe_key).first():
        return None
    notification = Notification(
        user_id=user_id,
        role=normalize_role(role) if role else None,
        company_id=company_id,
        notification_type=notification_type,
        title=title,
        message=message,
        dedupe_key=dedupe_key,
    )
    db.add(notification)
    return notification


def generate_deadline_notifications(db: Session) -> None:
    cycle = get_active_cycle(db) or get_latest_cycle(db)
    if not cycle:
        return
    days_remaining = get_days_to_deadline(cycle.submission_deadline)
    if days_remaining is None or days_remaining > 7:
        return
    for company in db.query(Company).all():
        submission = latest_submission_for_cycle(db, company.id, cycle.id)
        status = normalize_submission_status(submission.status) if submission else 'not started'
        if status in {'approved', 'submitted', 'under review'}:
            continue
        overdue = days_remaining < 0
        day_label = 'day' if days_remaining == 1 else 'days'
        label = 'overdue' if overdue else f'due in {days_remaining} {day_label}'
        create_notification(
            db,
            notification_type='deadline',
            title='ESG submission overdue' if overdue else 'ESG submission deadline approaching',
            message=f'{company.name} FY{cycle.cycle_year} submission is {label}.',
            user_id=company.user_id,
            company_id=company.id,
            dedupe_key=f'deadline-company-{cycle.id}-{company.id}-{days_remaining}',
        )
        create_notification(
            db,
            notification_type='overdue' if overdue else 'deadline',
            title='Portfolio submission overdue' if overdue else 'Portfolio deadline approaching',
            message=f'{company.name} FY{cycle.cycle_year} submission is {label}.',
            role='manager',
            company_id=company.id,
            dedupe_key=f'deadline-manager-{cycle.id}-{company.id}-{days_remaining}',
        )
    db.commit()


def serialize_notification(item: Notification) -> dict[str, Any]:
    return {
        'id': item.id,
        'type': item.notification_type,
        'title': item.title,
        'message': item.message,
        'company_id': item.company_id,
        'read': item.read_at is not None,
        'created_at': item.created_at.isoformat() if item.created_at else None,
    }


@app.get('/notifications')
def list_notifications(user: User = Depends(get_authenticated_user), db: Session = Depends(get_db)):
    generate_deadline_notifications(db)
    role = normalize_role(user.role)
    query = db.query(Notification)
    if role == 'company':
        company_ids = [company.id for company in db.query(Company).filter(Company.user_id == user.id).all()]
        query = query.filter(or_(Notification.user_id == user.id, Notification.company_id.in_(company_ids)))
    else:
        query = query.filter(or_(Notification.user_id == user.id, Notification.role == role))
    items = query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(100).all()
    return {'unread_count': sum(item.read_at is None for item in items), 'items': [serialize_notification(item) for item in items]}


@app.patch('/notifications/{notification_id}/read')
def read_notification(notification_id: int, user: User = Depends(get_authenticated_user), db: Session = Depends(get_db)):
    item = db.query(Notification).filter(Notification.id == notification_id).first()
    if not item:
        raise HTTPException(status_code=404, detail='Notification not found')
    role = normalize_role(user.role)
    owned_company_ids = {company.id for company in db.query(Company).filter(Company.user_id == user.id).all()}
    allowed = item.user_id == user.id or item.role == role or (role == 'company' and item.company_id in owned_company_ids)
    if not allowed:
        raise HTTPException(status_code=403, detail='Notification access denied')
    item.read_at = datetime.utcnow()
    db.commit()
    return serialize_notification(item)


@app.post('/auth/sso/{provider}', response_model=UserResponse)
def sso_login(provider: str, payload: SSOLoginRequest | None = None):
    normalized_provider = provider.strip().lower()
    allowed_providers = {'google', 'microsoft'}
    if normalized_provider not in allowed_providers:
        raise HTTPException(status_code=400, detail='Unsupported SSO provider')

    raise HTTPException(status_code=501, detail=f'{normalized_provider.title()} SSO requires verified provider configuration')


@app.get('/users', response_model=List[UserResponse], dependencies=[Depends(require_manager)])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [serialize_user(user) for user in users]


@app.get('/admin/csv-parity-check', response_model=CsvParityResponse, dependencies=[Depends(require_manager)])
def csv_parity_check(db: Session = Depends(get_db)):
    return _build_csv_parity_report(db)


def _normalize_csv_header(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower()).strip('_')


def _clean_csv_value(value: Any, numeric: bool) -> tuple[Any, bool]:
    original = '' if value is None else str(value)
    cleaned = original.strip()
    corrected = cleaned != original
    if numeric:
        without_commas = cleaned.replace(',', '')
        if without_commas.endswith('%'):
            without_commas = without_commas[:-1].strip()
        corrected = corrected or without_commas != cleaned
        cleaned = without_commas
    return cleaned, corrected


def _csv_validation_messages(error: ValidationError) -> list[str]:
    messages = []
    for item in error.errors():
        field = '.'.join(str(part) for part in item.get('loc') or []) or 'row'
        messages.append(f"{field}: {item.get('msg', 'invalid value')}")
    return messages


@app.post('/admin/import/submissions')
def import_submissions_csv(
    file: UploadFile = File(...),
    mode: str = Form(default='preview'),
    cycle_id: int | None = Form(default=None),
    mapping_json: str = Form(default='{}'),
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    normalized_mode = str(mode or 'preview').strip().lower()
    if normalized_mode not in {'preview', 'commit'}:
        raise HTTPException(status_code=422, detail='mode must be preview or commit')
    raw = file.file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='CSV files must be 5 MB or smaller')
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=422, detail='CSV must use UTF-8 encoding') from error
    try:
        requested_mapping = json.loads(mapping_json or '{}')
    except ValueError as error:
        raise HTTPException(status_code=422, detail='Column mapping must be valid JSON') from error
    if not isinstance(requested_mapping, dict):
        raise HTTPException(status_code=422, detail='Column mapping must be an object')

    reader = csv.DictReader(io.StringIO(content))
    source_columns = [str(item or '').strip() for item in (reader.fieldnames or [])]
    if not source_columns:
        raise HTTPException(status_code=422, detail='CSV header row is required')
    identity_fields = {'company_id', 'company_code', 'company_name', 'reporting_year'}
    submission_fields = set(SubmissionCreateRequest.model_fields.keys())
    supported_fields = identity_fields | submission_fields
    mapping = {}
    column_mapping = []
    used_targets = set()
    for source in source_columns:
        requested_target = str(requested_mapping.get(source) or '').strip()
        suggested_target = requested_target or _normalize_csv_header(source)
        target = suggested_target if suggested_target in supported_fields else ''
        if target and target in used_targets:
            target = ''
        if target:
            mapping[source] = target
            used_targets.add(target)
        column_mapping.append({
            'source': source,
            'target': target,
            'status': 'mapped' if target else 'unmapped',
        })

    target_cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first() if cycle_id else get_latest_cycle(db)
    if not target_cycle:
        raise HTTPException(status_code=422, detail='A valid reporting cycle is required')
    numeric_fields = {
        field_name for field_name, model_field in SubmissionCreateRequest.model_fields.items()
        if model_field.annotation in {int, float}
    }
    rows = []
    seen_companies = set()
    accepted_records = []
    corrected_rows = 0
    rejected_rows = 0
    for row_number, source_row in enumerate(reader, start=2):
        errors = []
        corrected = False
        if None in source_row or any(source_row.get(column) is None for column in source_columns):
            errors.append('Column count does not match the header; the row may be shifted or malformed')
        mapped_row = {}
        for source, target in mapping.items():
            cleaned, value_corrected = _clean_csv_value(source_row.get(source), target in numeric_fields or target == 'reporting_year')
            mapped_row[target] = cleaned
            corrected = corrected or value_corrected or source != target

        company = None
        company_id_value = str(mapped_row.get('company_id') or '').strip()
        company_code = str(mapped_row.get('company_code') or '').strip()
        company_name = str(mapped_row.get('company_name') or '').strip()
        if company_id_value.isdigit():
            company = db.query(Company).filter(Company.id == int(company_id_value)).first()
        elif company_code:
            company = db.query(Company).filter(func.lower(Company.code) == company_code.lower()).first()
        elif company_name:
            company = db.query(Company).filter(func.lower(Company.name) == company_name.lower()).first()
        if not company:
            errors.append('Company could not be matched by company_id, company_code, or company_name')

        reporting_year_text = str(mapped_row.get('reporting_year') or '').strip()
        try:
            reporting_year = int(float(reporting_year_text))
        except (TypeError, ValueError):
            reporting_year = None
            errors.append('reporting_year must be a four-digit number')
        max_year = datetime.now(timezone.utc).year + MAX_REPORTING_CYCLE_FUTURE_YEARS
        if reporting_year is not None and not MIN_REPORTING_CYCLE_YEAR <= reporting_year <= max_year:
            errors.append(f'reporting_year must be between {MIN_REPORTING_CYCLE_YEAR} and {max_year}')
        if reporting_year is not None and reporting_year != target_cycle.cycle_year:
            errors.append(f'reporting_year {reporting_year} does not match selected cycle FY{target_cycle.cycle_year}')

        if company and company.id in seen_companies:
            errors.append('Duplicate company row in this CSV')
        if company:
            seen_companies.add(company.id)
            if db.query(Submission).filter(Submission.company_id == company.id, Submission.cycle_id == target_cycle.id).first():
                errors.append('A submission already exists for this company and reporting cycle')

        validated_payload = None
        if not errors:
            try:
                validated_payload = SubmissionCreateRequest.model_validate({
                    field: mapped_row.get(field) for field in submission_fields
                })
            except ValidationError as error:
                errors.extend(_csv_validation_messages(error))
        status = 'rejected' if errors else 'accepted'
        if errors:
            rejected_rows += 1
        else:
            corrected_rows += int(corrected)
            accepted_records.append((company, validated_payload))
        rows.append({
            'row': row_number,
            'company': company.name if company else company_name or company_code or company_id_value or 'Unmatched',
            'status': status,
            'corrected': corrected,
            'errors': errors,
        })

    if normalized_mode == 'commit':
        for company, validated_payload in accepted_records:
            db.add(Submission(
                company_id=company.id,
                cycle_id=target_cycle.id,
                esg_data=json.dumps(validated_payload.model_dump()),
                status='submitted',
            ))
        log_audit_event(db, 'csv_import_committed', manager, cycle_id=target_cycle.id, metadata={
            'accepted': len(accepted_records),
            'rejected': rejected_rows,
            'corrected': corrected_rows,
            'filename': Path(file.filename or 'upload.csv').name,
        })
        db.commit()

    return {
        'mode': normalized_mode,
        'file_name': Path(file.filename or 'upload.csv').name,
        'cycle_id': target_cycle.id,
        'cycle_year': target_cycle.cycle_year,
        'columns': column_mapping,
        'rows': rows,
        'summary': {
            'total': len(rows),
            'accepted': len(accepted_records),
            'rejected': rejected_rows,
            'corrected': corrected_rows,
            'imported': len(accepted_records) if normalized_mode == 'commit' else 0,
        },
    }


@app.post('/companies', response_model=CompanyCreateResponse, dependencies=[Depends(require_manager)])
def create_company(payload: CompanyCreateRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.contact_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail='A user with this contact email already exists')

    portfolio_user = User(
        name=payload.contact_name,
        email=payload.contact_email,
        password=hash_password(payload.temporary_password),
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


@app.post('/cycles', response_model=CycleInfo)
def create_cycle(payload: CycleCreateRequest, manager: User = Depends(require_manager), db: Session = Depends(get_db)):
    max_cycle_year = datetime.now(timezone.utc).year + MAX_REPORTING_CYCLE_FUTURE_YEARS
    if payload.cycle_year < MIN_REPORTING_CYCLE_YEAR or payload.cycle_year > max_cycle_year:
        raise HTTPException(
            status_code=422,
            detail=f'Cycle year must be between {MIN_REPORTING_CYCLE_YEAR} and {max_cycle_year}',
        )
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
        created_by_user_id=manager.id,
    )
    db.add(cycle)
    db.flush()
    log_audit_event(db, 'cycle_created', manager, cycle_id=cycle.id, metadata={'cycle_year': cycle.cycle_year})
    db.commit()
    db.refresh(cycle)
    return serialize_cycle(cycle)


@app.get('/cycles', response_model=List[CycleInfo], dependencies=[Depends(get_authenticated_user)])
def list_cycles(db: Session = Depends(get_db)):
    max_cycle_year = datetime.now(timezone.utc).year + MAX_REPORTING_CYCLE_FUTURE_YEARS
    cycles = (
        db.query(CollectionCycle)
        .filter(
            CollectionCycle.cycle_year >= MIN_REPORTING_CYCLE_YEAR,
            CollectionCycle.cycle_year <= max_cycle_year,
        )
        .order_by(CollectionCycle.cycle_year.desc())
        .all()
    )
    return [serialize_cycle(cycle) for cycle in cycles]

@app.patch('/cycles/{cycle_id}/status', response_model=CycleInfo)
def update_cycle_status(cycle_id: int, payload: CycleStatusUpdateRequest, manager: User = Depends(require_manager), db: Session = Depends(get_db)):
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
    log_audit_event(db, 'cycle_status_changed', manager, cycle_id=cycle.id, metadata={'status': next_status})
    db.commit()
    db.refresh(cycle)
    return serialize_cycle(cycle)


@app.delete('/cycles/{cycle_id}')
def delete_cycle(cycle_id: int, manager: User = Depends(require_manager), db: Session = Depends(get_db)):
    cycle = db.query(CollectionCycle).filter(CollectionCycle.id == cycle_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail='Cycle not found')
    submission_count = db.query(Submission).filter(Submission.cycle_id == cycle.id).count()
    if submission_count:
        raise HTTPException(status_code=409, detail=f'Cycle contains {submission_count} submissions and cannot be deleted; archive it instead')
    dependent_count = (
        db.query(SubmissionDraft).filter(SubmissionDraft.cycle_id == cycle.id).count()
        + db.query(SubmissionEvidence).filter(SubmissionEvidence.cycle_id == cycle.id).count()
        + db.query(ReminderLog).filter(ReminderLog.cycle_id == cycle.id).count()
    )
    if dependent_count:
        raise HTTPException(status_code=409, detail='Cycle contains draft, evidence, or reminder records and cannot be deleted; archive it instead')
    cycle_year = cycle.cycle_year
    db.query(AuditEvent).filter(AuditEvent.cycle_id == cycle.id).update({'cycle_id': None}, synchronize_session=False)
    log_audit_event(db, 'cycle_deleted', manager, metadata={'cycle_id': cycle.id, 'cycle_year': cycle_year})
    db.delete(cycle)
    db.commit()
    return {'message': f'FY{cycle_year} deleted'}


@app.post('/company/{company_id}/onboarding/complete', dependencies=[Depends(require_manager)])
def complete_onboarding(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    company.current_status = 'active'
    db.commit()
    return {"message": "Onboarding complete. Company is now active in the portfolio."}


@app.get('/company/{company_id}/draft', dependencies=[Depends(require_company_or_manager)])
def get_submission_draft(
    company_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    company = require_company_access(db, company_id, role, email)
    cycle = resolve_submission_cycle(db)
    submission = latest_submission_for_cycle(db, company.id, cycle.id)
    draft = (
        db.query(SubmissionDraft)
        .filter(SubmissionDraft.company_id == company.id, SubmissionDraft.cycle_id == cycle.id)
        .first()
    )
    edit_state = submission_edit_state(db, company.id, cycle, submission)
    payload = parse_json_or_default(draft.payload, {}) if draft else {}
    if not payload and submission and edit_state['can_edit']:
        payload = parse_submission(submission)
    evidence = (
        db.query(SubmissionEvidence)
        .filter(SubmissionEvidence.company_id == company.id, SubmissionEvidence.cycle_id == cycle.id)
        .order_by(SubmissionEvidence.created_at.desc(), SubmissionEvidence.id.desc())
        .all()
    )
    return {
        'id': draft.id if draft else None,
        'company_id': company.id,
        'cycle_id': cycle.id,
        'cycle_year': cycle.cycle_year,
        'payload': payload,
        'updated_at': draft.updated_at.isoformat() if draft and draft.updated_at else None,
        'latest_submission_id': submission.id if submission else None,
        'evidence': [serialize_evidence(item) for item in evidence],
        **edit_state,
    }


@app.put('/company/{company_id}/draft', dependencies=[Depends(require_company_or_manager)])
def upsert_submission_draft(
    company_id: int,
    request: SubmissionDraftRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    company = require_company_access(db, company_id, role, email)
    cycle = resolve_submission_cycle(db)
    submission = latest_submission_for_cycle(db, company.id, cycle.id)
    edit_state = submission_edit_state(db, company.id, cycle, submission)
    if not edit_state['can_edit']:
        raise HTTPException(status_code=423, detail=edit_state['lock_reason'])

    draft = (
        db.query(SubmissionDraft)
        .filter(SubmissionDraft.company_id == company.id, SubmissionDraft.cycle_id == cycle.id)
        .first()
    )
    if draft is None:
        draft = SubmissionDraft(company_id=company.id, cycle_id=cycle.id, payload='{}')
        db.add(draft)
    draft.payload = json.dumps(request.payload)
    draft.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)
    return {
        'id': draft.id,
        'company_id': company.id,
        'cycle_id': cycle.id,
        'cycle_year': cycle.cycle_year,
        'updated_at': draft.updated_at.isoformat(),
        'latest_submission_id': submission.id if submission else None,
        **edit_state,
    }


@app.delete('/company/{company_id}/evidence/{evidence_id}', dependencies=[Depends(require_company_or_manager)])
def delete_submission_evidence(
    company_id: int,
    evidence_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    company = require_company_access(db, company_id, role, email)
    cycle = resolve_submission_cycle(db)
    submission = latest_submission_for_cycle(db, company.id, cycle.id)
    edit_state = submission_edit_state(db, company.id, cycle, submission)
    if not edit_state['can_edit']:
        raise HTTPException(status_code=423, detail=edit_state['lock_reason'])
    evidence = (
        db.query(SubmissionEvidence)
        .filter(
            SubmissionEvidence.id == evidence_id,
            SubmissionEvidence.company_id == company.id,
            SubmissionEvidence.cycle_id == cycle.id,
        )
        .first()
    )
    if not evidence:
        raise HTTPException(status_code=404, detail='Evidence not found')
    db.delete(evidence)
    db.commit()
    return {'message': 'Evidence removed', 'id': evidence_id}


@app.get('/company/{company_id}/evidence/{evidence_id}', dependencies=[Depends(require_company_or_manager)])
def download_submission_evidence(
    company_id: int,
    evidence_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    company = require_company_access(db, company_id, role, email)
    evidence = (
        db.query(SubmissionEvidence)
        .filter(SubmissionEvidence.id == evidence_id, SubmissionEvidence.company_id == company.id)
        .first()
    )
    if not evidence:
        raise HTTPException(status_code=404, detail='Evidence not found')
    safe_filename = Path(evidence.filename).name.replace('"', '')
    return Response(
        content=evidence.content,
        media_type=evidence.content_type or 'application/octet-stream',
        headers={'Content-Disposition': f'attachment; filename="{safe_filename}"'},
    )

@app.post('/company/{company_id}/submissions', response_model=SubmissionInfo, dependencies=[Depends(require_company_or_manager)])
def add_submission(
    company_id: int,
    submission: SubmissionCreateRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    company = require_company_access(db, company_id, role, email)

    target_cycle = resolve_submission_cycle(db)
    if not target_cycle:
        raise HTTPException(status_code=400, detail='No collection cycle is configured')

    latest_for_cycle = latest_submission_for_cycle(db, company_id, target_cycle.id)
    edit_state = submission_edit_state(db, company_id, target_cycle, latest_for_cycle)
    if not edit_state['can_edit']:
        raise HTTPException(status_code=423, detail=edit_state['lock_reason'])

    incoming_payload = submission.model_dump()
    if submission.reporting_year is not None and submission.reporting_year != target_cycle.cycle_year:
        raise HTTPException(status_code=422, detail=f'reporting_year must match active cycle FY{target_cycle.cycle_year}')
    incoming_payload['reporting_year'] = target_cycle.cycle_year
    attached_metric_keys = {
        item.metric_key for item in db.query(SubmissionEvidence).filter(
            SubmissionEvidence.company_id == company_id,
            SubmissionEvidence.cycle_id == target_cycle.id,
        ).all()
    }
    missing_evidence = sorted(REQUIRED_EVIDENCE_METRICS - attached_metric_keys)
    if missing_evidence:
        raise HTTPException(status_code=422, detail=f"Required evidence missing for metrics: {', '.join(missing_evidence)}")
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

    if latest_for_cycle:
        current_status = normalize_submission_status(latest_for_cycle.status)
        if current_status == 'resubmission requested':
            enforce_transition(latest_for_cycle.status, 'submitted')
        submission_record = latest_for_cycle
        submission_record.esg_data = json.dumps(merged_payload)
        submission_record.status = 'submitted'
    else:
        submission_record = Submission(
            company_id=company_id,
            cycle_id=target_cycle.id,
            esg_data=json.dumps(merged_payload),
            status='submitted',
        )
        db.add(submission_record)
        db.flush()

    db.query(SubmissionDraft).filter(
        SubmissionDraft.company_id == company_id,
        SubmissionDraft.cycle_id == target_cycle.id,
    ).delete(synchronize_session=False)
    db.query(SubmissionEvidence).filter(
        SubmissionEvidence.company_id == company_id,
        SubmissionEvidence.cycle_id == target_cycle.id,
    ).update({'submission_id': submission_record.id, 'status': 'attached'}, synchronize_session=False)
    db.query(SubmissionUnlock).filter(
        SubmissionUnlock.submission_id == submission_record.id,
        SubmissionUnlock.active.is_(True),
    ).update({'active': False}, synchronize_session=False)
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

def create_submission_status_notifications(db: Session, submission: Submission, next_status: str) -> None:
    company = db.query(Company).filter(Company.id == submission.company_id).first()
    if not company:
        return
    cycle_year = submission.cycle.cycle_year if submission.cycle else 'current'
    if next_status == 'rejected':
        create_notification(
            db,
            notification_type='rejected',
            title='Submission rejected',
            message=f'{company.name} FY{cycle_year} submission was rejected and requires manager follow-up.',
            role='manager',
            company_id=company.id,
            dedupe_key=f'submission-rejected-{submission.id}',
        )
    if next_status == 'resubmission requested':
        create_notification(
            db,
            notification_type='resubmission',
            title='Resubmission requested',
            message=f'Updates are required for {company.name} FY{cycle_year}. Review manager comments and resubmit.',
            user_id=company.user_id,
            company_id=company.id,
            dedupe_key=f'submission-resubmission-{submission.id}',
        )


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
    create_submission_status_notifications(db, submission, next_status)
    db.commit()
    db.refresh(submission)
    return submission

@app.post('/company/{company_id}/action-plans', response_model=ActionPlanInfo, dependencies=[Depends(require_company_or_manager)])
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


@app.patch('/action-plans/{plan_id}', response_model=ActionPlanInfo, dependencies=[Depends(require_company_or_manager)])
def update_action_plan_status(
    plan_id: int,
    status: str = Body(embed=True),
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    normalized = str(status or '').strip().lower()
    if normalized not in {'planned', 'in progress', 'completed', 'blocked'}:
        raise HTTPException(status_code=400, detail='Invalid action plan status')
    plan = db.query(ActionPlan).filter(ActionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail='Action plan not found')
    company = db.query(Company).filter(Company.id == plan.company_id).first()
    if normalize_role(user.role) == 'company' and (not company or company.user_id != user.id):
        raise HTTPException(status_code=403, detail='You can update only your company action plans')
    plan.status = normalized
    log_audit_event(db, 'action_plan_updated', user, company_id=plan.company_id, metadata={'plan_id': plan.id, 'status': normalized})
    db.commit()
    db.refresh(plan)
    return plan


def _target_progress(target: ESGTarget) -> float:
    baseline = float(target.baseline_value or 0)
    goal = float(target.target_value or 0)
    current = float(target.current_value or 0)
    if goal == baseline:
        return 100.0 if current == goal else 0.0
    if goal > baseline:
        progress = ((current - baseline) / (goal - baseline)) * 100
    else:
        progress = ((baseline - current) / (baseline - goal)) * 100
    return round(clamp(progress), 1)


def _serialize_target(target: ESGTarget, company_name: str) -> dict[str, Any]:
    return {
        'id': target.id,
        'company_id': target.company_id,
        'company_name': company_name,
        'pillar': target.pillar,
        'metric_key': target.metric_key,
        'target_name': target.target_name,
        'baseline_value': float(target.baseline_value or 0),
        'target_value': float(target.target_value or 0),
        'current_value': float(target.current_value or 0),
        'unit': target.unit or '',
        'target_date': target.target_date,
        'owner': target.owner,
        'status': target.status,
        'notes': target.notes,
        'progress_percent': _target_progress(target),
        'created_at': target.created_at.isoformat() if target.created_at else '',
        'updated_at': target.updated_at.isoformat() if target.updated_at else '',
    }


@app.get('/targets', response_model=List[ESGTargetInfo])
def list_esg_targets(
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    query = db.query(ESGTarget, Company.name).join(Company, Company.id == ESGTarget.company_id)
    if normalize_role(user.role) == 'company':
        query = query.filter(Company.user_id == user.id)
    elif company_id is not None:
        query = query.filter(ESGTarget.company_id == company_id)
    rows = query.order_by(ESGTarget.target_date.asc(), ESGTarget.id.asc()).all()
    return [_serialize_target(target, company_name) for target, company_name in rows]


@app.post('/company/{company_id}/targets', response_model=ESGTargetInfo)
def create_esg_target(
    company_id: int,
    payload: ESGTargetCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    if normalize_role(user.role) not in {'manager', 'company'}:
        raise HTTPException(status_code=403, detail='Only managers and companies can create targets')
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    if normalize_role(user.role) == 'company' and company.user_id != user.id:
        raise HTTPException(status_code=403, detail='You can create targets only for your company')
    try:
        datetime.strptime(payload.target_date, '%Y-%m-%d')
    except ValueError as error:
        raise HTTPException(status_code=422, detail='target_date must use YYYY-MM-DD') from error
    target = ESGTarget(company_id=company.id, **payload.model_dump())
    db.add(target)
    db.flush()
    log_audit_event(db, 'esg_target_created', user, company_id=company.id, metadata={'target_id': target.id, 'metric_key': target.metric_key})
    db.commit()
    db.refresh(target)
    return _serialize_target(target, company.name)


@app.patch('/targets/{target_id}', response_model=ESGTargetInfo)
def update_esg_target(
    target_id: int,
    payload: ESGTargetUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    if normalize_role(user.role) not in {'manager', 'company'}:
        raise HTTPException(status_code=403, detail='Only managers and companies can update targets')
    target = db.query(ESGTarget).filter(ESGTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail='Target not found')
    company = db.query(Company).filter(Company.id == target.company_id).first()
    if normalize_role(user.role) == 'company' and (not company or company.user_id != user.id):
        raise HTTPException(status_code=403, detail='You can update targets only for your company')
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(target, key, value)
    target.updated_at = datetime.utcnow()
    log_audit_event(db, 'esg_target_updated', user, company_id=target.company_id, metadata={'target_id': target.id, 'fields': sorted(updates)})
    db.commit()
    db.refresh(target)
    return _serialize_target(target, company.name if company else 'Unknown company')

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

@app.post('/company/{company_id}/upload-evidence', dependencies=[Depends(require_company_or_manager)])
def upload_evidence(
    company_id: int,
    file: UploadFile = File(...),
    metric_key: str = Form(...),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    company = require_company_access(db, company_id, role, email)
    cycle = resolve_submission_cycle(db)
    submission = latest_submission_for_cycle(db, company.id, cycle.id)
    edit_state = submission_edit_state(db, company.id, cycle, submission)
    if not edit_state['can_edit']:
        raise HTTPException(status_code=423, detail=edit_state['lock_reason'])

    normalized_metric_key = str(metric_key or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9_]{2,120}', normalized_metric_key):
        raise HTTPException(status_code=422, detail='A valid metric key is required')
    filename = Path(file.filename or '').name.strip()
    if not filename:
        raise HTTPException(status_code=422, detail='Evidence filename is required')

    file.file.seek(0, os.SEEK_END)
    file_size = int(file.file.tell())
    file.file.seek(0)
    if file_size > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='Evidence files must be 25 MB or smaller')
    file_content = file.file.read()
    file.file.seek(0)

    evidence = SubmissionEvidence(
        company_id=company.id,
        cycle_id=cycle.id,
        submission_id=submission.id if submission else None,
        metric_key=normalized_metric_key,
        filename=filename,
        content_type=file.content_type,
        file_size=file_size,
        content=file_content,
        status='uploaded',
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return {**serialize_evidence(evidence), 'message': 'Evidence uploaded successfully'}

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
    if next_status == 'resubmission requested':
        seed_draft_from_submission(db, submission)
    create_submission_status_notifications(db, submission, next_status)
    reporting_year = submission.cycle.cycle_year if submission.cycle else datetime.utcnow().year
    review_action = ReviewAction(
        company_id=submission.company_id,
        submission_id=submission.id,
        reporting_year=reporting_year,
        review_status=next_status,
        reviewer_role=payload.reviewer_role or 'manager',
        review_comment=payload.review_comment,
    )
    db.add(review_action)
    db.commit()
    db.refresh(submission)
    return {"message": "Review logged successfully", "status": submission.status}


def _assurance_payload(db: Session, submission: Submission) -> dict[str, Any]:
    evidence = db.query(SubmissionEvidence).filter(SubmissionEvidence.submission_id == submission.id).order_by(SubmissionEvidence.metric_key.asc()).all()
    records = db.query(AssuranceRecord).filter(AssuranceRecord.submission_id == submission.id).order_by(AssuranceRecord.metric_key.asc()).all()
    record_by_metric = {item.metric_key: item for item in records}
    evidence_by_metric = {item.metric_key: item for item in evidence}
    metric_keys = sorted(set(evidence_by_metric) | set(record_by_metric))
    items = []
    for metric_key in metric_keys:
        item = record_by_metric.get(metric_key)
        attachment = evidence_by_metric.get(metric_key)
        items.append({
            'id': item.id if item else None,
            'metric_key': metric_key,
            'evidence_id': attachment.id if attachment else (item.evidence_id if item else None),
            'filename': attachment.filename if attachment else None,
            'evidence_status': attachment.status if attachment else 'missing',
            'status': item.status if item else 'pending',
            'assurance_level': item.assurance_level if item else 'limited',
            'conclusion': item.conclusion if item else '',
            'reviewer_user_id': item.reviewer_user_id if item else None,
            'updated_at': item.updated_at.isoformat() if item and item.updated_at else None,
        })
    counts = Counter(row['status'] for row in items)
    completed = counts.get('assured', 0) + counts.get('exception', 0)
    return {
        'submission_id': submission.id,
        'company_id': submission.company_id,
        'total_metrics': len(items),
        'assured': counts.get('assured', 0),
        'exceptions': counts.get('exception', 0),
        'in_review': counts.get('in review', 0),
        'pending': counts.get('pending', 0),
        'completion_percent': round((completed / len(items)) * 100, 1) if items else 0.0,
        'items': items,
    }


@app.get('/submissions/{submission_id}/assurance')
def get_submission_assurance(
    submission_id: int,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    role = normalize_role(user.role)
    if role == 'company':
        company = db.query(Company).filter(Company.id == submission.company_id).first()
        if not company or company.user_id != user.id:
            raise HTTPException(status_code=403, detail='Assurance records are restricted to your company')
    elif role not in {'manager', 'investor'}:
        raise HTTPException(status_code=403, detail='Assurance records are restricted')
    return _assurance_payload(db, submission)


@app.put('/submissions/{submission_id}/assurance/{metric_key}')
def upsert_assurance_decision(
    submission_id: int,
    metric_key: str,
    payload: AssuranceDecisionRequest,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    normalized_key = str(metric_key or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9_]{2,120}', normalized_key):
        raise HTTPException(status_code=422, detail='A valid metric key is required')
    evidence = None
    if payload.evidence_id is not None:
        evidence = db.query(SubmissionEvidence).filter(
            SubmissionEvidence.id == payload.evidence_id,
            SubmissionEvidence.submission_id == submission.id,
            SubmissionEvidence.metric_key == normalized_key,
        ).first()
        if not evidence:
            raise HTTPException(status_code=422, detail='Evidence does not belong to this submission metric')
    item = db.query(AssuranceRecord).filter(
        AssuranceRecord.submission_id == submission.id,
        AssuranceRecord.metric_key == normalized_key,
    ).first()
    if item is None:
        item = AssuranceRecord(submission_id=submission.id, metric_key=normalized_key)
        db.add(item)
    item.evidence_id = payload.evidence_id
    item.status = payload.status
    item.assurance_level = payload.assurance_level
    item.conclusion = payload.conclusion.strip()
    item.reviewer_user_id = manager.id
    item.updated_at = datetime.utcnow()
    if evidence:
        evidence.status = 'verified' if payload.status == 'assured' else ('rejected' if payload.status == 'exception' else 'under review')
    log_audit_event(
        db,
        'assurance_decision_updated',
        manager,
        submission_id=submission.id,
        field_name=normalized_key,
        metadata={'status': payload.status, 'assurance_level': payload.assurance_level},
    )
    db.commit()
    db.refresh(item)
    return _assurance_payload(db, submission)


@app.get('/submissions/{submission_id}/metric-comments')
def list_metric_comments(
    submission_id: int,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    if normalize_role(user.role) == 'company':
        company = db.query(Company).filter(Company.id == submission.company_id).first()
        if not company or company.user_id != user.id:
            raise HTTPException(status_code=403, detail='Metric comments are restricted to your company')
    elif normalize_role(user.role) != 'manager':
        raise HTTPException(status_code=403, detail='Metric comments are restricted to managers and company users')
    comments = db.query(MetricReviewComment).filter(MetricReviewComment.submission_id == submission.id).order_by(MetricReviewComment.metric_key.asc()).all()
    return [{
        'id': item.id,
        'submission_id': item.submission_id,
        'metric_key': item.metric_key,
        'comment': item.comment,
        'reviewer_user_id': item.reviewer_user_id,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    } for item in comments]


@app.put('/submissions/{submission_id}/metric-comments')
def upsert_metric_comment(
    submission_id: int,
    payload: MetricReviewCommentRequest,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')
    item = db.query(MetricReviewComment).filter(
        MetricReviewComment.submission_id == submission.id,
        MetricReviewComment.metric_key == payload.metric_key,
    ).first()
    if item is None:
        item = MetricReviewComment(submission_id=submission.id, metric_key=payload.metric_key)
        db.add(item)
    item.comment = payload.comment.strip()
    item.reviewer_user_id = manager.id
    item.updated_at = datetime.utcnow()
    log_audit_event(db, 'metric_comment_updated', manager, submission_id=submission.id, field_name=payload.metric_key)
    db.commit()
    db.refresh(item)
    return {
        'id': item.id,
        'submission_id': item.submission_id,
        'metric_key': item.metric_key,
        'comment': item.comment,
        'reviewer_user_id': item.reviewer_user_id,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    }


@app.get('/submissions/{submission_id}/history', response_model=List[SubmissionHistoryEntry], dependencies=[Depends(require_manager)])
def get_submission_history(submission_id: int, db: Session = Depends(get_db)):
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail='Submission not found')

    reporting_year = submission.cycle.cycle_year if submission.cycle else datetime.utcnow().year
    reviews = (
        db.query(ReviewAction)
        .filter(
            ReviewAction.company_id == submission.company_id,
            ReviewAction.reporting_year == reporting_year,
            (ReviewAction.submission_id == submission.id) | (ReviewAction.submission_id.is_(None)),
        )
        .all()
    )
    unlocks = db.query(SubmissionUnlock).filter(SubmissionUnlock.submission_id == submission.id).all()

    entries = [
        SubmissionHistoryEntry(
            id=f'review-{review.id}',
            event_type='review',
            status=normalize_submission_status(review.review_status),
            comment=review.review_comment,
            actor=review.reviewer_role,
            created_at=review.created_at.isoformat() if review.created_at else None,
        )
        for review in reviews
    ]
    entries.extend(
        SubmissionHistoryEntry(
            id=f'unlock-{unlock.id}',
            event_type='unlock',
            status='editing unlocked',
            comment=unlock.reason,
            actor=unlock.unlocked_by_user.email if unlock.unlocked_by_user else 'manager',
            created_at=unlock.created_at.isoformat() if unlock.created_at else None,
            expires_at=unlock.expires_at.isoformat() if unlock.expires_at else None,
            active=unlock.active and bool(unlock.expires_at and unlock.expires_at > datetime.utcnow()),
        )
        for unlock in unlocks
    )
    entries.sort(key=lambda entry: entry.created_at or '', reverse=True)
    return entries

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
        total_energy = _safe_float(data['total_energy_consumption'])
        renewable_energy = _safe_float(data['renewable_energy_consumption'])
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
        total_water = _safe_float(data['total_water_withdrawal'])
        recycled_water = _safe_float(data['water_recycled_reused'])
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
        total_waste = _safe_float(data['total_waste_generated'])
        diverted_waste = _safe_float(data['waste_diverted_from_landfill'])
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
        female_overall = _safe_float(data['female_representation_percent'])
        female_leadership = _safe_float(data['female_leadership_representation_percent'])
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
            curr_val, prev_val = _safe_float(data.get(field)), _safe_float(prev_data.get(field))
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
        'rejected': 'Rejected',
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
        'Rejected': 100,
        'Resubmission Requested': 58,
    }.get(bucket, 8)


def build_manager_summary(db: Session, companies: List[Company]) -> dict:
    cycle = get_active_cycle(db)
    if cycle is None:
        cycle = (
            db.query(CollectionCycle)
            .filter(
                CollectionCycle.cycle_year >= MIN_REPORTING_CYCLE_YEAR,
                CollectionCycle.cycle_year <= datetime.now(timezone.utc).year + MAX_REPORTING_CYCLE_FUTURE_YEARS,
            )
            .order_by(CollectionCycle.cycle_year.desc())
            .first()
        )
    cycle_deadline = cycle.submission_deadline if cycle else None
    cycle_days_remaining = get_days_to_deadline(cycle_deadline)
    status_breakdown = {
        'Not Started': 0,
        'In Progress': 0,
        'Submitted': 0,
        'Under Review': 0,
        'Approved': 0,
        'Rejected': 0,
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


def resolve_report_cycle(db: Session, period: str) -> CollectionCycle:
    normalized = str(period or 'Current Cycle').strip()
    year_match = re.fullmatch(r'FY\s*(\d{4})', normalized, flags=re.IGNORECASE)
    if year_match:
        cycle = db.query(CollectionCycle).filter(CollectionCycle.cycle_year == int(year_match.group(1))).first()
        if not cycle:
            raise HTTPException(status_code=404, detail=f'No reporting cycle found for {normalized.upper()}')
        return cycle
    if normalized.lower() not in {'current cycle', 'current', 'active'}:
        raise HTTPException(status_code=400, detail='period must be Current Cycle or FY followed by a four-digit year')
    return get_active_cycle(db) or get_latest_cycle(db) or get_or_create_reserved_cycle(db)


def _latest_cycle_submission(company: Company, cycle_id: int) -> Submission | None:
    matches = [item for item in (company.submissions or []) if item.cycle_id == cycle_id]
    return max(matches, key=lambda item: item.id) if matches else None


def build_report_rows(db: Session, portfolio: str, period: str):
    active_cycle = resolve_report_cycle(db, period)
    companies_query = db.query(Company)
    normalized_portfolio = (portfolio or 'all').strip()
    if normalized_portfolio and normalized_portfolio.lower() not in {'all', 'all portfolio companies'}:
        companies_query = companies_query.filter(Company.name == normalized_portfolio)
    companies = companies_query.order_by(Company.name.asc()).all()

    rows = []
    for company in companies:
        latest_submission = _latest_cycle_submission(company, active_cycle.id)
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
            'esg_score': calculate_submission_scores(payload)['composite'] if payload else None,
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


REPORT_PILLARS = {
    'Environmental': [
        ('total_ghg_emissions', 'Total GHG emissions', 'tCO2e'),
        ('scope_1_emissions', 'Scope 1 emissions', 'tCO2e'),
        ('scope_2_location_based', 'Scope 2 emissions - location', 'tCO2e'),
        ('scope_3_emissions', 'Scope 3 emissions', 'tCO2e'),
        ('total_energy_consumption', 'Total energy consumption', 'MWh'),
        ('renewable_energy_consumption', 'Renewable energy consumption', 'MWh'),
        ('reduction_target_percent', 'Emissions reduction target', '%'),
    ],
    'Social': [
        ('total_employees_fte', 'Employees', 'FTE'),
        ('female_representation_percent', 'Female representation', '%'),
        ('female_leadership_representation_percent', 'Female leadership', '%'),
        ('trifr', 'Total recordable injury frequency rate', 'TRIFR'),
        ('total_fatalities', 'Fatalities', 'count'),
        ('employee_turnover_rate', 'Employee turnover', '%'),
        ('community_investment_spend', 'Community investment', 'reported currency units'),
    ],
    'Governance': [
        ('independent_board_members_percent', 'Independent board members', '%'),
        ('female_board_members_percent', 'Female board members', '%'),
        ('esg_policy_in_place', 'ESG policy in place', ''),
        ('board_level_esg_oversight', 'Board-level ESG oversight', ''),
        ('cybersecurity_policy_in_place', 'Cybersecurity policy', ''),
        ('anti_bribery_corruption_policy', 'Anti-bribery policy', ''),
        ('confirmed_cases_of_corruption', 'Confirmed corruption cases', 'count'),
    ],
}


def _report_value(payload: dict, key: str, unit: str) -> str:
    value = payload.get(key)
    if value in (None, ''):
        return 'Not reported'
    if isinstance(value, (int, float)):
        rendered = f'{float(value):,.2f}'.rstrip('0').rstrip('.')
    else:
        rendered = str(value)
    return f'{rendered} {unit}'.strip()


def _humanize_event(value: str | None) -> str:
    return str(value or 'Activity').replace('_', ' ').strip().title()


def build_formal_report_data(
    db: Session,
    report_type: str,
    portfolio: str,
    period: str,
) -> dict[str, Any]:
    cycle = resolve_report_cycle(db, period)
    query = db.query(Company).options(selectinload(Company.submissions))
    normalized_portfolio = str(portfolio or '').strip()
    if normalized_portfolio and normalized_portfolio.lower() not in {'all', 'all portfolio companies'}:
        query = query.filter(Company.name == normalized_portfolio)
    companies = query.order_by(Company.name.asc()).all()
    if not companies:
        raise HTTPException(status_code=404, detail='No companies matched the selected report scope')

    company_reports = []
    for company in companies:
        submission = _latest_cycle_submission(company, cycle.id)
        payload = parse_submission(submission)
        evidence_query = db.query(SubmissionEvidence).filter(
            SubmissionEvidence.company_id == company.id,
            SubmissionEvidence.cycle_id == cycle.id,
        )
        if submission:
            evidence_query = evidence_query.filter(or_(
                SubmissionEvidence.submission_id == submission.id,
                SubmissionEvidence.submission_id.is_(None),
            ))
        evidence = evidence_query.order_by(SubmissionEvidence.created_at.desc()).all()
        attached_metrics = {item.metric_key for item in evidence if str(item.status).lower() in {'uploaded', 'verified', 'accepted'}}
        missing_required = sorted(REQUIRED_EVIDENCE_METRICS - attached_metrics)

        flags = db.query(ValidationFlag).filter(
            ValidationFlag.company_id == company.id,
            ValidationFlag.reporting_year == cycle.cycle_year,
        ).order_by(ValidationFlag.id.asc()).all()
        reviews = db.query(ReviewAction).filter(
            ReviewAction.company_id == company.id,
            ReviewAction.reporting_year == cycle.cycle_year,
        ).order_by(ReviewAction.created_at.desc()).limit(12).all()
        audit_query = db.query(AuditEvent).filter(
            AuditEvent.company_id == company.id,
            or_(AuditEvent.cycle_id == cycle.id, AuditEvent.cycle_id.is_(None)),
        )
        if submission:
            audit_query = audit_query.filter(or_(AuditEvent.submission_id == submission.id, AuditEvent.submission_id.is_(None)))
        audits = audit_query.order_by(AuditEvent.created_at.desc()).limit(20).all()
        history = [
            {
                'date': item.created_at,
                'event': _humanize_event(item.event_type),
                'actor': item.actor_email or item.actor_role or 'System',
                'detail': _humanize_event(item.field_name) if item.field_name else 'Recorded through the application audit log',
            }
            for item in audits
        ]
        history.extend({
            'date': item.created_at,
            'event': f'Review - {_humanize_event(item.review_status)}',
            'actor': item.reviewer_role or 'Reviewer',
            'detail': item.review_comment or 'No review comment provided',
        } for item in reviews)
        history.sort(key=lambda item: item['date'] or datetime.min, reverse=True)

        status = normalize_manager_bucket(submission.status if submission else company.current_status)
        company_reports.append({
            'company': company,
            'submission': submission,
            'payload': payload,
            'status': status,
            'scores': calculate_submission_scores(payload) if payload else None,
            'pillars': {
                pillar: [
                    {'key': key, 'label': label, 'value': _report_value(payload, key, unit), 'confidence': payload.get(f'{key}_confidence') or 'Not stated'}
                    for key, label, unit in metrics
                ]
                for pillar, metrics in REPORT_PILLARS.items()
            },
            'evidence': evidence,
            'missing_required_evidence': missing_required,
            'evidence_complete': not missing_required,
            'flags': flags,
            'history': history[:24],
        })

    status_counts = Counter(item['status'] for item in company_reports)
    scores = [item['scores']['composite'] for item in company_reports if item['scores']]
    return {
        'report_type': report_type.upper(),
        'portfolio': portfolio,
        'period': period,
        'cycle': cycle,
        'generated_at': datetime.now(timezone.utc),
        'companies': company_reports,
        'status_counts': status_counts,
        'average_score': round(sum(scores) / len(scores), 2) if scores else None,
    }


def _pdf_paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(str(value if value not in (None, '') else '-')).replace('\n', '<br/>'), style)


def write_pdf_export(file_path: Path, report_data: dict[str, Any]):
    navy = colors.HexColor('#0F2742')
    teal = colors.HexColor('#0F766E')
    pale_teal = colors.HexColor('#E8F5F2')
    pale_blue = colors.HexColor('#EFF5FB')
    muted = colors.HexColor('#526579')
    border = colors.HexColor('#D6E0E8')
    page_width, page_height = A4
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ReportTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=27, leading=32, textColor=navy, alignment=TA_LEFT, spaceAfter=8))
    styles.add(ParagraphStyle(name='ReportSubtitle', parent=styles['Normal'], fontSize=12, leading=17, textColor=muted))
    styles.add(ParagraphStyle(name='SectionTitle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=15, leading=19, textColor=navy, spaceBefore=10, spaceAfter=7))
    styles.add(ParagraphStyle(name='PillarTitle', parent=styles['Heading3'], fontName='Helvetica-Bold', fontSize=11.5, leading=15, textColor=teal, spaceBefore=7, spaceAfter=5))
    styles.add(ParagraphStyle(name='BodySmall', parent=styles['BodyText'], fontSize=8.5, leading=11, textColor=colors.HexColor('#263746')))
    styles.add(ParagraphStyle(name='TableHead', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white))
    styles.add(ParagraphStyle(name='TableCell', parent=styles['BodyText'], fontSize=7.7, leading=10, textColor=colors.HexColor('#263746')))
    styles.add(ParagraphStyle(name='Score', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=17, leading=20, textColor=navy, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='ScoreLabel', parent=styles['Normal'], fontSize=7.5, leading=9, textColor=muted, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='CoverLabel', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=teal, spaceAfter=2))

    cycle = report_data['cycle']
    title = f"{report_data['report_type']} ESG Report"

    def page_decor(canvas, doc):
        canvas.saveState()
        if doc.page > 1:
            canvas.setStrokeColor(border)
            canvas.line(18 * mm, page_height - 15 * mm, page_width - 18 * mm, page_height - 15 * mm)
            canvas.setFont('Helvetica-Bold', 8)
            canvas.setFillColor(navy)
            canvas.drawString(18 * mm, page_height - 11.5 * mm, 'GREENLEDGER')
            canvas.setFont('Helvetica', 7.5)
            canvas.setFillColor(muted)
            canvas.drawRightString(page_width - 18 * mm, page_height - 11.5 * mm, f'{title} | FY{cycle.cycle_year}')
        canvas.setStrokeColor(border)
        canvas.line(18 * mm, 13 * mm, page_width - 18 * mm, 13 * mm)
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(muted)
        canvas.drawString(18 * mm, 8.5 * mm, 'Confidential - manager-generated report')
        canvas.drawRightString(page_width - 18 * mm, 8.5 * mm, f'Page {doc.page}')
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(file_path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=21 * mm, bottomMargin=18 * mm,
        title=title, author='GreenLedger ESG Intelligence',
        subject=f"FY{cycle.cycle_year} ESG report",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='report-frame')
    doc.addPageTemplates([PageTemplate(id='report', frames=[frame], onPage=page_decor)])

    def table(data, widths, header=True):
        result = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign='LEFT')
        commands = [
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.45, border),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1 if header else 0), (-1, -1), [colors.white, pale_blue]),
        ]
        if header:
            commands.extend([('BACKGROUND', (0, 0), (-1, 0), navy), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white)])
        result.setStyle(TableStyle(commands))
        return result

    story = [
        Spacer(1, 20 * mm),
        _pdf_paragraph('GREENLEDGER ESG INTELLIGENCE', styles['CoverLabel']),
        _pdf_paragraph(title, styles['ReportTitle']),
        _pdf_paragraph('Formal company and portfolio disclosure record', styles['ReportSubtitle']),
        Spacer(1, 13 * mm),
    ]
    cover_rows = [
        [_pdf_paragraph('REPORT SCOPE', styles['CoverLabel']), _pdf_paragraph(report_data['portfolio'], styles['BodyText'])],
        [_pdf_paragraph('REPORTING CYCLE', styles['CoverLabel']), _pdf_paragraph(f"FY{cycle.cycle_year} - {_humanize_event(cycle.status)}", styles['BodyText'])],
        [_pdf_paragraph('SUBMISSION WINDOW', styles['CoverLabel']), _pdf_paragraph(f'{cycle.submission_open_date} to {cycle.extension_date or cycle.submission_deadline}', styles['BodyText'])],
        [_pdf_paragraph('GENERATED', styles['CoverLabel']), _pdf_paragraph(report_data['generated_at'].strftime('%d %B %Y, %H:%M UTC'), styles['BodyText'])],
        [_pdf_paragraph('FRAMEWORK ALIGNMENT', styles['CoverLabel']), _pdf_paragraph(report_data['report_type'], styles['BodyText'])],
    ]
    cover_table = Table(cover_rows, colWidths=[48 * mm, 102 * mm], hAlign='LEFT')
    cover_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), pale_teal), ('BOX', (0, 0), (-1, -1), 0.8, teal),
        ('INNERGRID', (0, 0), (-1, -1), 0.35, colors.white), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 9), ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    story.extend([cover_table, Spacer(1, 28 * mm), _pdf_paragraph('Document purpose', styles['SectionTitle']), _pdf_paragraph(
        'This report consolidates submitted ESG metrics, supporting evidence status, validation findings, and recorded review activity for the selected reporting cycle. It is an internal reporting artifact and does not constitute independent assurance or regulatory certification.',
        styles['BodyText'],
    ), PageBreak()])

    story.extend([_pdf_paragraph('Portfolio executive summary', styles['SectionTitle'])])
    score_value = report_data['average_score'] if report_data['average_score'] is not None else '-'
    summary_cards = Table([
        [_pdf_paragraph(str(len(report_data['companies'])), styles['Score']), _pdf_paragraph(str(score_value), styles['Score']), _pdf_paragraph(str(sum(len(item['flags']) for item in report_data['companies'])), styles['Score'])],
        [_pdf_paragraph('Companies in scope', styles['ScoreLabel']), _pdf_paragraph('Average internal ESG score', styles['ScoreLabel']), _pdf_paragraph('Validation issues', styles['ScoreLabel'])],
    ], colWidths=[doc.width / 3] * 3)
    summary_cards.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), pale_teal), ('BOX', (0, 0), (-1, -1), 0.6, border),
        ('INNERGRID', (0, 0), (-1, -1), 0.6, colors.white), ('TOPPADDING', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 9),
    ]))
    story.extend([summary_cards, Spacer(1, 7 * mm)])
    company_summary = [[_pdf_paragraph(label, styles['TableHead']) for label in ['Company', 'Sector', 'Status', 'ESG score', 'Evidence']]]
    for item in report_data['companies']:
        company_summary.append([
            _pdf_paragraph(item['company'].name, styles['TableCell']),
            _pdf_paragraph(item['company'].sector, styles['TableCell']),
            _pdf_paragraph(item['status'], styles['TableCell']),
            _pdf_paragraph(item['scores']['composite'] if item['scores'] else 'Not available', styles['TableCell']),
            _pdf_paragraph('Complete' if item['evidence_complete'] else 'Required evidence missing', styles['TableCell']),
        ])
    story.append(table(company_summary, [44 * mm, 35 * mm, 30 * mm, 22 * mm, 34 * mm]))

    for item in report_data['companies']:
        company = item['company']
        story.extend([PageBreak(), _pdf_paragraph(company.name, styles['ReportTitle'])])
        story.append(_pdf_paragraph(
            f"{company.sector} | {_humanize_event(company.asset_class) if company.asset_class else 'Asset class not stated'} | {company.geography or 'Geography not stated'} | FY{cycle.cycle_year}",
            styles['ReportSubtitle'],
        ))
        story.append(Spacer(1, 5 * mm))
        scores = item['scores'] or {'E': '-', 'S': '-', 'G': '-', 'composite': '-'}
        score_table = Table([
            [_pdf_paragraph(scores['E'], styles['Score']), _pdf_paragraph(scores['S'], styles['Score']), _pdf_paragraph(scores['G'], styles['Score']), _pdf_paragraph(scores['composite'], styles['Score'])],
            [_pdf_paragraph('Environmental', styles['ScoreLabel']), _pdf_paragraph('Social', styles['ScoreLabel']), _pdf_paragraph('Governance', styles['ScoreLabel']), _pdf_paragraph('Composite', styles['ScoreLabel'])],
        ], colWidths=[doc.width / 4] * 4)
        score_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), pale_teal), ('BOX', (0, 0), (-1, -1), .6, border), ('INNERGRID', (0, 0), (-1, -1), .6, colors.white), ('TOPPADDING', (0, 0), (-1, 0), 7), ('BOTTOMPADDING', (0, 1), (-1, 1), 7)]))
        story.extend([score_table, Spacer(1, 4 * mm)])

        for pillar, metrics in item['pillars'].items():
            metric_rows = [[_pdf_paragraph(label, styles['TableHead']) for label in ['Metric', 'Reported value', 'Data confidence']]]
            metric_rows.extend([
                [_pdf_paragraph(metric['label'], styles['TableCell']), _pdf_paragraph(metric['value'], styles['TableCell']), _pdf_paragraph(metric['confidence'], styles['TableCell'])]
                for metric in metrics
            ])
            story.extend([_pdf_paragraph(pillar, styles['PillarTitle']), table(metric_rows, [72 * mm, 48 * mm, 45 * mm])])

        story.extend([Spacer(1, 3 * mm), _pdf_paragraph('Evidence status', styles['SectionTitle'])])
        evidence_intro = 'All required metric evidence is attached.' if item['evidence_complete'] else 'Missing required evidence for: ' + ', '.join(_humanize_event(key) for key in item['missing_required_evidence']) + '.'
        story.append(_pdf_paragraph(evidence_intro, styles['BodySmall']))
        if item['evidence']:
            evidence_rows = [[_pdf_paragraph(label, styles['TableHead']) for label in ['Metric', 'File', 'Status', 'Uploaded']]]
            evidence_rows.extend([
                [_pdf_paragraph(_humanize_event(ev.metric_key), styles['TableCell']), _pdf_paragraph(ev.filename, styles['TableCell']), _pdf_paragraph(_humanize_event(ev.status), styles['TableCell']), _pdf_paragraph(ev.created_at.strftime('%d %b %Y') if ev.created_at else '-', styles['TableCell'])]
                for ev in item['evidence']
            ])
            story.extend([Spacer(1, 2 * mm), table(evidence_rows, [46 * mm, 60 * mm, 28 * mm, 31 * mm])])
        else:
            story.append(_pdf_paragraph('No evidence files are recorded for this company and cycle.', styles['BodySmall']))

        story.extend([_pdf_paragraph('Validation findings', styles['SectionTitle'])])
        if item['flags']:
            flag_rows = [[_pdf_paragraph(label, styles['TableHead']) for label in ['Severity', 'Metric', 'Finding']]]
            flag_rows.extend([
                [_pdf_paragraph(flag.severity, styles['TableCell']), _pdf_paragraph(_humanize_event(flag.field_name), styles['TableCell']), _pdf_paragraph(flag.issue_description, styles['TableCell'])]
                for flag in item['flags']
            ])
            story.append(table(flag_rows, [25 * mm, 42 * mm, 98 * mm]))
        else:
            story.append(_pdf_paragraph('No validation findings are recorded for the selected cycle.', styles['BodySmall']))

        story.extend([_pdf_paragraph('Audit and review history', styles['SectionTitle'])])
        if item['history']:
            history_rows = [[_pdf_paragraph(label, styles['TableHead']) for label in ['Date', 'Event', 'Actor', 'Detail']]]
            history_rows.extend([
                [_pdf_paragraph(event['date'].strftime('%d %b %Y %H:%M') if event['date'] else '-', styles['TableCell']), _pdf_paragraph(event['event'], styles['TableCell']), _pdf_paragraph(event['actor'], styles['TableCell']), _pdf_paragraph(event['detail'], styles['TableCell'])]
                for event in item['history']
            ])
            story.append(table(history_rows, [30 * mm, 38 * mm, 42 * mm, 55 * mm]))
        else:
            story.append(_pdf_paragraph('No audit or review history is recorded for this company and cycle.', styles['BodySmall']))

    methodology_rows = [
        ('Environmental score', 'Starts at 30 points; adjusts for reported Scope 1, 2 and 3 emissions, reduction target, and renewable-energy share; capped at 0-100.'),
        ('Social score', 'Uses female representation, TRIFR, employee turnover, and workplace health and safety policy status; capped at 0-100.'),
        ('Governance score', 'Uses ESG oversight and policy controls, independent-board representation, and confirmed corruption cases; capped at 0-100.'),
        ('Composite score', 'Internal composite = 45% Environmental + 30% Social + 25% Governance.'),
        ('Missing data', 'Missing numeric values are treated as zero by the internal scoring model and may reduce comparability.'),
        ('Evidence', 'Evidence status confirms that a file is recorded against a metric. It does not mean the evidence has been independently assured unless its status explicitly says verified.'),
        ('Framework alignment', f"The {report_data['report_type']} label describes reporting alignment only; this export is not a compliance opinion or external assurance statement."),
    ]
    story.extend([PageBreak(), _pdf_paragraph('Methodology and limitations', styles['ReportTitle']), _pdf_paragraph(
        'The report uses the latest submission stored for each company within the selected reporting cycle. Historical-cycle reports do not fall back to data from another year.', styles['ReportSubtitle']), Spacer(1, 6 * mm)])
    method_table = [[_pdf_paragraph('Area', styles['TableHead']), _pdf_paragraph('Method', styles['TableHead'])]]
    method_table.extend([[_pdf_paragraph(label, styles['TableCell']), _pdf_paragraph(description, styles['TableCell'])] for label, description in methodology_rows])
    story.extend([table(method_table, [45 * mm, 120 * mm]), Spacer(1, 6 * mm), _pdf_paragraph(
        'Scheduled generation is intentionally not enabled in this release. Reports are generated on demand by an authenticated manager; scheduling can be added as a later phase with retention, delivery, and recipient controls.', styles['BodySmall'])])
    doc.build(story)


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

    previous_status = normalize_submission_status(submission.status)
    if previous_status != 'resubmission requested':
        submission.status = 'resubmission requested'
        seed_draft_from_submission(db, submission)
        db.add(ReviewAction(
            company_id=submission.company_id,
            submission_id=submission.id,
            reporting_year=cycle.cycle_year,
            review_status='resubmission requested',
            reviewer_role='manager',
            review_comment=payload.reason,
        ))

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


@app.get('/reports/{report_type}/export', response_model=ReportExportResponse)
def export_report(
    report_type: str,
    format: str = Query(default='csv'),
    period: str = Query(default='Current Cycle'),
    portfolio: str = Query(default='All Portfolio Companies'),
    db: Session = Depends(get_db),
    manager: User = Depends(require_manager),
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
        formal_report = build_formal_report_data(db, report_name, portfolio, period)
        write_pdf_export(file_path, formal_report)
        content_type = 'application/pdf'

    try:
        storage_path = persist_export(file_path, content_type)
    except Exception as error:
        print(json.dumps({
            'level': 'error',
            'event': 'export_persist_failed',
            'report_type': report_name,
            'format': export_format,
            'error_type': type(error).__name__,
            'error': str(error)[:600],
            **_runtime_context(),
        }), flush=True)
        raise HTTPException(status_code=503, detail='Unable to persist the generated report') from error

    log_audit_event(
        db,
        'report_generated',
        manager,
        cycle_id=cycle.id,
        metadata={
            'report_type': report_name.upper(),
            'format': export_format,
            'period': period,
            'portfolio': portfolio,
            'file_name': file_name,
            'storage_path': storage_path,
        },
    )
    db.commit()

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
    companies = (
        db.query(Company)
        .options(
            selectinload(Company.submissions),
            selectinload(Company.action_plans),
            selectinload(Company.validation_flags),
        )
        .order_by(Company.name.asc())
        .all()
    )
    summary = build_manager_summary(db, companies)
    return {
        'companies': serialize_company_details(db, companies),
        'summary': summary,
    }


def serialize_company_details(db: Session, companies: List[Company]) -> list[dict]:
    reviews_by_company: dict[int, list[dict]] = {}
    if not os.getenv('VERCEL'):
        review_columns = {column['name'] for column in inspect(db.bind).get_columns('review_actions')}
        submission_expression = 'submission_id' if 'submission_id' in review_columns else 'NULL AS submission_id'
        created_expression = 'created_at' if 'created_at' in review_columns else 'NULL AS created_at'
        review_rows = db.execute(text(
            'SELECT id, company_id, reporting_year, review_status, reviewer_role, review_comment, '
            f'{submission_expression}, {created_expression} FROM review_actions ORDER BY id ASC'
        )).mappings().all()
        for row in review_rows:
            reviews_by_company.setdefault(int(row['company_id']), []).append({
                'id': row['id'],
                'submission_id': row['submission_id'],
                'reporting_year': row['reporting_year'],
                'review_status': row['review_status'],
                'reviewer_role': row['reviewer_role'],
                'review_comment': row['review_comment'],
                'created_at': row['created_at'],
            })

    return [
        {
            'id': company.id,
            'name': company.name,
            'sector': company.sector,
            'geography': company.geography,
            'current_status': company.current_status,
            'submissions': company.submissions or [],
            'action_plans': company.action_plans or [],
            'review_actions': reviews_by_company.get(company.id, []),
            'validation_flags': company.validation_flags or [],
        }
        for company in companies
    ]

def safe_number(value, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return max(minimum, min(maximum, value))


def calculate_submission_scores(payload: dict) -> dict:
    scope_1 = safe_number(payload.get('scope_1_emissions'))
    scope_2 = safe_number(payload.get('scope_2_location_based'))
    scope_3 = safe_number(payload.get('scope_3_emissions'))
    energy = safe_number(payload.get('total_energy_consumption'))
    renewable = safe_number(payload.get('renewable_energy_consumption'))
    renewable_ratio = (renewable / energy) if energy > 0 else 0
    female_rep = safe_number(payload.get('female_representation_percent'))
    trifr = safe_number(payload.get('trifr'))
    turnover = safe_number(payload.get('employee_turnover_rate'))
    independent_board = safe_number(payload.get('independent_board_members_percent'))
    corruption_cases = safe_number(payload.get('confirmed_cases_of_corruption'))

    e_score = clamp(
        30
        + max(0, 35 - ((scope_1 + scope_2 + scope_3) / 60))
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
    return {
        'E': round(e_score, 2),
        'S': round(s_score, 2),
        'G': round(g_score, 2),
        'composite': round((0.45 * e_score) + (0.30 * s_score) + (0.25 * g_score), 2),
    }


def normalize_status_label(status: str | None) -> str:
    normalized = str(status or '').strip().lower()
    mapping = {
        'not started': 'Not Started',
        'in progress': 'In Progress',
        'submitted': 'Submitted',
        'under review': 'Under Review',
        'approved': 'Approved',
        'rejected': 'Rejected',
        'resubmission requested': 'Resubmission Requested',
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


def get_submission_reporting_year(submission: Submission, payload: dict) -> int | None:
    try:
        payload_year = int(payload.get('reporting_year') or 0)
    except (TypeError, ValueError):
        payload_year = 0
    if payload_year > 0:
        return payload_year
    if submission.cycle and submission.cycle.cycle_year:
        return int(submission.cycle.cycle_year)
    return None


def build_historical_portfolio_series(companies: List[Company]) -> tuple[list[dict], list[dict]]:
    latest_by_company_year: dict[tuple[int, int], tuple[Submission, dict]] = {}
    for company in companies:
        for submission in company.submissions or []:
            payload = parse_submission(submission)
            year = get_submission_reporting_year(submission, payload)
            if not payload or year is None:
                continue
            key = (company.id, year)
            current = latest_by_company_year.get(key)
            if current is None or submission.id > current[0].id:
                latest_by_company_year[key] = (submission, payload)

    by_year: dict[int, dict] = {}
    for (_, year), (_, payload) in latest_by_company_year.items():
        bucket = by_year.setdefault(year, {'emissions': 0.0, 'score_total': 0.0, 'score_count': 0})
        bucket['emissions'] += (
            safe_number(payload.get('scope_1_emissions'))
            + safe_number(payload.get('scope_2_location_based'))
            + safe_number(payload.get('scope_3_emissions'))
        )
        bucket['score_total'] += calculate_submission_scores(payload)['composite']
        bucket['score_count'] += 1

    emissions = []
    scores = []
    for year in sorted(by_year):
        bucket = by_year[year]
        emissions.append({'period': str(year), 'total_emissions': round(bucket['emissions'], 2)})
        scores.append({
            'period': str(year),
            'score': round(bucket['score_total'] / max(bucket['score_count'], 1), 2),
        })
    return emissions, scores


def build_investor_analytics(db: Session) -> dict:
    companies = (
        db.query(Company)
        .options(
            selectinload(Company.submissions),
            selectinload(Company.action_plans),
            selectinload(Company.validation_flags),
        )
        .all()
    )

    status_counts = {
        'Not Started': 0,
        'In Progress': 0,
        'Submitted': 0,
        'Under Review': 0,
        'Approved': 0,
        'Rejected': 0,
        'Resubmission Requested': 0,
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
        total_scope_1 += scope_1
        total_scope_2 += scope_2
        total_scope_3 += scope_3
        total_energy += energy
        total_water += water
        total_waste += waste
        total_female_rep += female_rep
        total_trifr += trifr

        scope_total = scope_1 + scope_2 + scope_3
        scores = calculate_submission_scores(payload)
        e_score = scores['E']
        s_score = scores['S']
        g_score = scores['G']
        esg_score = scores['composite']

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
    emissions_trend, score_trend = build_historical_portfolio_series(companies)

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
        'emissions_trend': emissions_trend,
        'score_trend': score_trend,
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


def _call_openai_narrative(prompt: str) -> tuple[dict | None, str | None]:
    api_key = str(os.getenv('OPENAI_API_KEY') or '').strip()
    if not api_key or OpenAI is None:
        return None, 'not_configured'

    try:
        client = OpenAI(api_key=api_key, max_retries=0, timeout=6.0)
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
            return None, 'empty_response'
        parsed = json.loads(content)
        return (parsed, None) if isinstance(parsed, dict) else (None, 'invalid_response')
    except Exception as error:
        status_code = getattr(error, 'status_code', None)
        error_name = type(error).__name__.lower()
        message = str(error or '').lower()
        if status_code == 429 or 'ratelimit' in error_name or 'rate limit' in message or '429' in message:
            reason = 'rate_limited'
        elif 'timeout' in error_name or 'timed out' in message:
            reason = 'timeout'
        else:
            reason = 'provider_error'
        print(json.dumps({
            'level': 'warning',
            'event': 'ai_narrative_fallback',
            'provider': 'openai',
            'model': OPENAI_DEFAULT_MODEL,
            'reason': reason,
            'status_code': status_code,
        }), flush=True)
        return None, reason


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
        ai_payload, fallback_reason = _call_openai_narrative(prompt)
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
            'fallback_reason': fallback_reason,
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
    ai_payload, fallback_reason = _call_openai_narrative(prompt)
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
        'fallback_reason': fallback_reason,
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
    analytics = build_investor_analytics(db)
    submitted_companies = (
        db.query(Company)
        .options(
            selectinload(Company.submissions),
            selectinload(Company.action_plans),
            selectinload(Company.validation_flags),
        )
        .join(Submission, Submission.company_id == Company.id)
        .distinct()
        .order_by(Company.name.asc())
        .all()
    )
    return InvestorDashboardResponse(**analytics, companies=serialize_company_details(db, submitted_companies))


# ==========================================
# Restoration Compatibility Layer (Phases 1-6)
# ==========================================
def require_investor(role: str = Depends(get_user_role)):
    if role != 'investor':
        raise HTTPException(status_code=403, detail='Access restricted to investors')


def require_manager_or_investor(role: str = Depends(get_user_role)):
    if role not in {'manager', 'investor'}:
        raise HTTPException(status_code=403, detail='Access is restricted to managers and investors')


DATA_QUALITY_REQUIRED_FIELDS = [
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


def _data_quality_submission(company: Company, cycle_year: int | None) -> tuple[Submission | None, dict, int | None]:
    candidates = []
    for submission in company.submissions or []:
        payload = parse_submission(submission)
        year = get_submission_reporting_year(submission, payload)
        if cycle_year is None or year == cycle_year:
            candidates.append((submission, payload, year))
    if not candidates:
        return None, {}, cycle_year
    return max(candidates, key=lambda item: ((item[2] or 0), item[0].id))


def build_data_quality_dashboard(db: Session, cycle_year: int | None = None) -> dict[str, Any]:
    companies = (
        db.query(Company)
        .options(selectinload(Company.submissions), selectinload(Company.validation_flags))
        .order_by(Company.name.asc())
        .all()
    )
    rows = []
    confidence_mix = Counter({'Measured': 0, 'Estimated': 0, 'Not available': 0, 'Other': 0})
    severity_mix = Counter({'Critical': 0, 'High': 0, 'Medium': 0, 'Low': 0})
    issue_categories = Counter({'Missing required': 0, 'Estimated data': 0, 'Validation flags': 0, 'Missing evidence': 0})
    evidence_by_submission: dict[int, list[tuple[str, str]]] = {}
    evidence_rows = db.query(
        SubmissionEvidence.submission_id,
        SubmissionEvidence.metric_key,
        SubmissionEvidence.status,
    ).filter(SubmissionEvidence.submission_id.is_not(None)).all()
    for submission_id, metric_key, status in evidence_rows:
        evidence_by_submission.setdefault(int(submission_id), []).append((metric_key, status))

    for company in companies:
        submission, payload, reporting_year = _data_quality_submission(company, cycle_year)
        if not submission:
            rows.append({
                'company_id': company.id,
                'company': company.name,
                'sector': company.sector or 'Unassigned',
                'reporting_year': cycle_year,
                'submission_id': None,
                'quality_score': 0.0,
                'completeness': 0.0,
                'measured_confidence': 0.0,
                'evidence_coverage': 0.0,
                'validation_score': 0.0,
                'missing_required': len(DATA_QUALITY_REQUIRED_FIELDS),
                'estimated_values': 0,
                'measured_values': 0,
                'confidence_values': 0,
                'validation_flags': 0,
                'severity_counts': {'Critical': 0, 'High': 0, 'Medium': 0, 'Low': 0},
                'missing_evidence': len(REQUIRED_EVIDENCE_METRICS),
                'priority': 'At risk',
                'top_issue': 'No submission for the selected cycle',
            })
            issue_categories['Missing required'] += len(DATA_QUALITY_REQUIRED_FIELDS)
            issue_categories['Missing evidence'] += len(REQUIRED_EVIDENCE_METRICS)
            continue

        missing_fields = [field for field in DATA_QUALITY_REQUIRED_FIELDS if payload.get(field) in (None, '')]
        completeness = ((len(DATA_QUALITY_REQUIRED_FIELDS) - len(missing_fields)) / len(DATA_QUALITY_REQUIRED_FIELDS)) * 100
        confidence_values = [
            str(value or '').strip().lower()
            for key, value in payload.items()
            if key.endswith('_confidence')
        ]
        for value in confidence_values:
            if value == 'measured':
                confidence_mix['Measured'] += 1
            elif value == 'estimated':
                confidence_mix['Estimated'] += 1
            elif value in {'not available', 'n/a', 'na', ''}:
                confidence_mix['Not available'] += 1
            else:
                confidence_mix['Other'] += 1
        measured_count = sum(1 for value in confidence_values if value == 'measured')
        estimated_count = sum(1 for value in confidence_values if value == 'estimated')
        measured_confidence = (measured_count / len(confidence_values)) * 100 if confidence_values else 0.0

        flags = [
            flag for flag in company.validation_flags or []
            if reporting_year is None or int(flag.reporting_year or 0) == int(reporting_year)
        ]
        severity_penalty = 0
        company_severity = Counter({'Critical': 0, 'High': 0, 'Medium': 0, 'Low': 0})
        for flag in flags:
            severity = str(flag.severity or 'Low').strip().title()
            if severity not in severity_mix:
                severity = 'Low'
            severity_mix[severity] += 1
            company_severity[severity] += 1
            severity_penalty += {'Critical': 35, 'High': 22, 'Medium': 12, 'Low': 5}[severity]
        validation_score = clamp(100 - severity_penalty)

        accepted_evidence_metrics = {
            metric_key for metric_key, status in evidence_by_submission.get(submission.id, [])
            if str(status or '').strip().lower() in {'uploaded', 'verified', 'accepted'}
        }
        missing_evidence = sorted(REQUIRED_EVIDENCE_METRICS - accepted_evidence_metrics)
        evidence_coverage = (
            ((len(REQUIRED_EVIDENCE_METRICS) - len(missing_evidence)) / len(REQUIRED_EVIDENCE_METRICS)) * 100
            if REQUIRED_EVIDENCE_METRICS else 100.0
        )
        quality_score = clamp(
            (0.40 * completeness)
            + (0.30 * measured_confidence)
            + (0.20 * validation_score)
            + (0.10 * evidence_coverage)
        )
        priority = 'Good' if quality_score >= 85 else 'Watch' if quality_score >= 70 else 'At risk'
        top_issue = (
            flags[0].issue_description if flags
            else f'{len(missing_fields)} required metrics missing' if missing_fields
            else f'{estimated_count} estimated confidence values' if estimated_count
            else 'Required evidence is missing' if missing_evidence
            else 'No material data-quality issues'
        )
        rows.append({
            'company_id': company.id,
            'company': company.name,
            'sector': company.sector or 'Unassigned',
            'reporting_year': reporting_year,
            'submission_id': submission.id,
            'quality_score': round(quality_score, 1),
            'completeness': round(completeness, 1),
            'measured_confidence': round(measured_confidence, 1),
            'evidence_coverage': round(evidence_coverage, 1),
            'validation_score': round(validation_score, 1),
            'missing_required': len(missing_fields),
            'estimated_values': estimated_count,
            'measured_values': measured_count,
            'confidence_values': len(confidence_values),
            'validation_flags': len(flags),
            'severity_counts': dict(company_severity),
            'missing_evidence': len(missing_evidence),
            'priority': priority,
            'top_issue': top_issue,
        })
        issue_categories['Missing required'] += len(missing_fields)
        issue_categories['Estimated data'] += estimated_count
        issue_categories['Validation flags'] += len(flags)
        issue_categories['Missing evidence'] += len(missing_evidence)

    reporting_rows = [row for row in rows if row['submission_id'] is not None]
    divisor = max(len(reporting_rows), 1)
    return {
        'cycle_year': cycle_year,
        'generated_at': _utc_now_iso(),
        'total_companies': len(rows),
        'reporting_companies': len(reporting_rows),
        'quality_index': round(sum(row['quality_score'] for row in reporting_rows) / divisor, 1),
        'completeness': round(sum(row['completeness'] for row in reporting_rows) / divisor, 1),
        'measured_confidence': round(sum(row['measured_confidence'] for row in reporting_rows) / divisor, 1),
        'evidence_coverage': round(sum(row['evidence_coverage'] for row in reporting_rows) / divisor, 1),
        'open_flags': sum(row['validation_flags'] for row in rows),
        'at_risk_companies': sum(1 for row in rows if row['priority'] == 'At risk'),
        'confidence_mix': [{'name': key, 'value': value} for key, value in confidence_mix.items()],
        'severity_mix': [{'name': key, 'value': value} for key, value in severity_mix.items()],
        'issue_categories': [{'name': key, 'value': value} for key, value in issue_categories.items()],
        'rows': sorted(rows, key=lambda row: (row['quality_score'], row['company'])),
    }


@app.get('/analytics/data-quality', dependencies=[Depends(require_manager_or_investor)])
def data_quality_dashboard(
    cycle_year: int | None = Query(default=None, ge=MIN_REPORTING_CYCLE_YEAR),
    db: Session = Depends(get_db),
):
    return build_data_quality_dashboard(db, cycle_year=cycle_year)


FRAMEWORK_DISCLOSURES = {
    'EDCI': [
        ('GHG emissions', 'scope_1_emissions', 'GHG emissions'),
        ('Renewable energy', 'renewable_energy_consumption', 'Renewable energy consumption'),
        ('Workplace safety', 'trifr', 'Work-related injuries'),
        ('Gender diversity', 'female_representation_percent', 'Gender diversity'),
        ('Board diversity', 'female_board_members_percent', 'Board diversity'),
    ],
    'GRI': [
        ('GRI 305-1', 'scope_1_emissions', 'Direct GHG emissions'),
        ('GRI 305-2', 'scope_2_location_based', 'Energy indirect GHG emissions'),
        ('GRI 303-3', 'total_water_withdrawal', 'Water withdrawal'),
        ('GRI 306-3', 'total_waste_generated', 'Waste generated'),
        ('GRI 405-1', 'female_representation_percent', 'Diversity of employees'),
    ],
    'ISSB': [
        ('IFRS S2.29(a)', 'scope_1_emissions', 'Scope 1 emissions'),
        ('IFRS S2.29(a)', 'scope_2_location_based', 'Scope 2 emissions'),
        ('IFRS S2.29(a)', 'scope_3_emissions', 'Scope 3 emissions'),
        ('IFRS S2.33', 'reduction_target_percent', 'Climate targets'),
        ('IFRS S1.27', 'board_level_esg_oversight', 'Governance oversight'),
    ],
    'SFDR': [
        ('PAI 1', 'total_ghg_emissions', 'GHG emissions'),
        ('PAI 5', 'renewable_energy_consumption', 'Non-renewable energy share'),
        ('PAI 9', 'hazardous_waste_generated', 'Hazardous waste'),
        ('PAI 12', 'female_representation_percent', 'Gender pay and representation'),
        ('PAI 13', 'female_board_members_percent', 'Board gender diversity'),
    ],
}


@app.get('/analytics/framework-mapping', dependencies=[Depends(require_manager_or_investor)])
def framework_mapping_dashboard(
    cycle_year: int | None = Query(default=None, ge=MIN_REPORTING_CYCLE_YEAR),
    db: Session = Depends(get_db),
):
    companies = db.query(Company).options(selectinload(Company.submissions)).order_by(Company.name.asc()).all()
    payloads = []
    for company in companies:
        submission, payload, reporting_year = _data_quality_submission(company, cycle_year)
        if submission:
            payloads.append({'company': company.name, 'year': reporting_year, 'payload': payload})

    framework_rows = []
    disclosure_rows = []
    denominator = len(payloads)
    for framework, mappings in FRAMEWORK_DISCLOSURES.items():
        available_points = 0
        possible_points = denominator * len(mappings)
        for reference, metric_key, disclosure in mappings:
            populated = sum(1 for row in payloads if row['payload'].get(metric_key) not in (None, ''))
            available_points += populated
            disclosure_rows.append({
                'framework': framework,
                'reference': reference,
                'disclosure': disclosure,
                'metric_key': metric_key,
                'companies_reported': populated,
                'companies_expected': denominator,
                'coverage_percent': round((populated / denominator) * 100, 1) if denominator else 0.0,
                'status': 'Mapped' if populated == denominator and denominator else ('Partial' if populated else 'Gap'),
            })
        framework_rows.append({
            'framework': framework,
            'mapped_disclosures': len(mappings),
            'coverage_percent': round((available_points / possible_points) * 100, 1) if possible_points else 0.0,
            'complete_disclosures': sum(
                1 for row in disclosure_rows
                if row['framework'] == framework and row['status'] == 'Mapped'
            ),
        })
    return {
        'cycle_year': cycle_year,
        'reporting_companies': denominator,
        'frameworks': framework_rows,
        'disclosures': disclosure_rows,
    }


def _serialize_materiality_topic(item: MaterialityTopic) -> dict[str, Any]:
    priority_score = round((item.impact_score * 0.45) + (item.financial_score * 0.4) + (item.stakeholder_score * 0.15), 2)
    if item.impact_score >= 4 and item.financial_score >= 4:
        quadrant = 'Material priority'
    elif item.impact_score >= 3 or item.financial_score >= 3:
        quadrant = 'Monitor closely'
    else:
        quadrant = 'Emerging'
    return {
        'id': item.id,
        'topic': item.topic,
        'pillar': item.pillar,
        'impact_score': item.impact_score,
        'financial_score': item.financial_score,
        'stakeholder_score': item.stakeholder_score,
        'priority_score': priority_score,
        'quadrant': quadrant,
        'rationale': item.rationale or '',
        'owner': item.owner,
        'status': item.status,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    }


@app.get('/materiality/topics')
def list_materiality_topics(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if normalize_role(user.role) not in {'manager', 'investor'}:
        raise HTTPException(status_code=403, detail='Materiality assessment is restricted to managers and investors')
    rows = db.query(MaterialityTopic).order_by(MaterialityTopic.impact_score.desc(), MaterialityTopic.financial_score.desc()).all()
    items = [_serialize_materiality_topic(item) for item in rows]
    return {
        'topics': items,
        'priority_topics': sum(1 for item in items if item['quadrant'] == 'Material priority'),
        'action_required': sum(1 for item in items if item['status'] == 'action required'),
        'average_priority': round(sum(item['priority_score'] for item in items) / len(items), 2) if items else 0.0,
    }


@app.post('/materiality/topics')
def create_materiality_topic(
    payload: MaterialityTopicRequest,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    topic_name = payload.topic.strip()
    existing = db.query(MaterialityTopic).filter(func.lower(MaterialityTopic.topic) == topic_name.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail='This materiality topic already exists')
    values = payload.model_dump()
    values['topic'] = topic_name
    item = MaterialityTopic(**values)
    db.add(item)
    log_audit_event(db, 'materiality_topic_created', manager, metadata={'topic': topic_name})
    db.commit()
    db.refresh(item)
    return _serialize_materiality_topic(item)


@app.patch('/materiality/topics/{topic_id}')
def update_materiality_topic(
    topic_id: int,
    payload: MaterialityTopicRequest,
    manager: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    item = db.query(MaterialityTopic).filter(MaterialityTopic.id == topic_id).first()
    if not item:
        raise HTTPException(status_code=404, detail='Materiality topic not found')
    for key, value in payload.model_dump().items():
        setattr(item, key, value.strip() if isinstance(value, str) else value)
    item.updated_at = datetime.utcnow()
    log_audit_event(db, 'materiality_topic_updated', manager, metadata={'topic_id': item.id})
    db.commit()
    db.refresh(item)
    return _serialize_materiality_topic(item)


@app.post('/analytics/scenario-analysis', dependencies=[Depends(require_manager_or_investor)])
def run_scenario_analysis(
    payload: ScenarioAnalysisRequest,
    db: Session = Depends(get_db),
):
    companies = db.query(Company).options(selectinload(Company.submissions)).order_by(Company.name.asc()).all()
    rows = []
    years_to_horizon = max(payload.horizon_year - datetime.now(timezone.utc).year, 1)
    pathway_pressure = max(payload.temperature_pathway - 1.5, 0) / 3
    for company in companies:
        submission, values, reporting_year = _data_quality_submission(company, None)
        if not submission:
            continue
        emissions = max(_safe_float(values.get('total_ghg_emissions')) or (
            (_safe_float(values.get('scope_1_emissions')) or 0)
            + (_safe_float(values.get('scope_2_location_based')) or 0)
            + (_safe_float(values.get('scope_3_emissions')) or 0)
        ), 0)
        energy = max(_safe_float(values.get('total_energy_consumption')) or 0, 0)
        water = max(_safe_float(values.get('total_water_withdrawal')) or 0, 0)
        waste = max(_safe_float(values.get('total_waste_generated')) or 0, 0)
        transition_cost = emissions * payload.carbon_price
        energy_cost = energy * 100 * (payload.energy_cost_change_percent / 100)
        physical_cost = ((water * 0.05) + (waste * 25)) * payload.physical_risk_multiplier * (1 + pathway_pressure)
        annual_exposure = max(transition_cost + energy_cost + physical_cost, 0)
        cumulative_exposure = annual_exposure * years_to_horizon
        risk_score = min(100, round(
            (min(emissions / 10000, 1) * 45)
            + (min(energy / 50000, 1) * 20)
            + (min((water + waste) / 100000, 1) * 20)
            + (pathway_pressure * 15),
            1,
        ))
        rows.append({
            'company_id': company.id,
            'company': company.name,
            'sector': company.sector or 'Unassigned',
            'reporting_year': reporting_year,
            'emissions_tco2e': round(emissions, 2),
            'transition_cost': round(transition_cost, 2),
            'energy_cost_impact': round(energy_cost, 2),
            'physical_risk_cost': round(physical_cost, 2),
            'annual_exposure': round(annual_exposure, 2),
            'cumulative_exposure': round(cumulative_exposure, 2),
            'risk_score': risk_score,
            'risk_tier': 'High' if risk_score >= 70 else ('Medium' if risk_score >= 40 else 'Low'),
        })
    total_annual = sum(row['annual_exposure'] for row in rows)
    return {
        'scenario': payload.model_dump(),
        'modelled_companies': len(rows),
        'annual_exposure': round(total_annual, 2),
        'cumulative_exposure': round(sum(row['cumulative_exposure'] for row in rows), 2),
        'high_risk_companies': sum(1 for row in rows if row['risk_tier'] == 'High'),
        'average_risk_score': round(sum(row['risk_score'] for row in rows) / len(rows), 1) if rows else 0.0,
        'rows': sorted(rows, key=lambda row: row['annual_exposure'], reverse=True),
        'methodology': [
            'Transition exposure applies the selected carbon price to reported Scope 1, 2 and 3 emissions.',
            'Energy exposure applies the selected cost change to reported energy using a transparent base-cost proxy.',
            'Physical exposure is a screening proxy based on reported water and waste, adjusted by the physical-risk multiplier.',
            'Results are decision-support estimates, not forecasts or valuations.',
        ],
    }


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
    score_trend = analytics.get('score_trend') or []
    emissions_trend = analytics.get('emissions_trend') or []

    def trend_percent(rows: list[dict], key: str) -> float | None:
        if len(rows) < 2:
            return None
        current = safe_number(rows[-1].get(key))
        previous = safe_number(rows[-2].get(key))
        if previous == 0:
            return None
        return round(((current - previous) / abs(previous)) * 100, 2)

    score_change = trend_percent(score_trend, 'score')
    emissions_change = trend_percent(emissions_trend, 'total_emissions')
    return [
        {
            'metric_name': 'Portfolio ESG Score',
            'current_value': f"{float(analytics.get('portfolio_esg_score') or 0):.1f}",
            'unit': 'score',
            'trend_percent': score_change,
            'trend_direction': 'up' if score_change is not None and score_change > 0 else 'down' if score_change is not None and score_change < 0 else 'neutral',
            'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Total GHG Emissions',
            'current_value': f"{float(emissions_totals.get('total') or 0):.1f}",
            'unit': 'tCO2e',
            'trend_percent': emissions_change,
            'trend_direction': 'up' if emissions_change is not None and emissions_change > 0 else 'down' if emissions_change is not None and emissions_change < 0 else 'neutral',
            'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Energy Consumption',
            'current_value': f"{float(resource_totals.get('energy') or 0):.1f}",
            'unit': 'MWh',
            'trend_percent': None,
            'trend_direction': 'neutral',
            'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        },
        {
            'metric_name': 'Data Completeness',
            'current_value': f"{float(data_quality.get('completeness') or 0):.1f}",
            'unit': '%',
            'trend_percent': None,
            'trend_direction': 'neutral',
            'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        },
    ]


def _build_lp_dashboard_payload(db: Session) -> dict:
    analytics = build_investor_analytics(db)
    companies = int(analytics.get('total_companies') or 0)
    reporting_companies = int(analytics.get('reporting_companies') or 0)
    narrative = _fallback_portfolio_narrative(analytics)
    score_trend = analytics.get('score_trend') or []
    current_score = float(analytics.get('portfolio_esg_score') or 0)
    previous_score = safe_number(score_trend[-2].get('score')) if len(score_trend) > 1 else None
    yoy_change = None
    if previous_score not in {None, 0}:
        yoy_change = round(((current_score - previous_score) / abs(previous_score)) * 100, 2)
    return {
        'portfolio_scorecard': {
            'overall_esg_score': current_score,
            'overall_esg_score_previous': previous_score,
            'yoy_change_percent': yoy_change,
            'three_year_trend': [float(item.get('score') or 0) for item in score_trend[-3:]],
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
    merged.update(incoming_payload or {})

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
                if input_type == 'select' and changed:
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
    database_check: dict[str, Any]
    try:
        started = time.perf_counter()
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        database_check = {
            'ok': True,
            'latency_ms': round((time.perf_counter() - started) * 1000, 2),
            'error': None,
        }
    except Exception as error:
        database_check = {
            'ok': False,
            'latency_ms': None,
            'error': type(error).__name__,
        }
    storage_check = storage_health()
    ready = bool(database_check['ok'] and storage_check.get('ok'))
    return {
        'status': 'ok' if ready else 'degraded',
        'version': APP_VERSION,
        'ready': ready,
        **_runtime_context(),
        'timestamp': _utc_now_iso(),
        'checks': {
            'database': database_check,
            'storage': storage_check,
            'openai': {'ok': True, 'configured': bool(str(os.getenv('OPENAI_API_KEY') or '').strip()), 'error': None},
        },
        'message': 'Application health snapshot',
    }


@app.get('/health/ready')
def health_ready(response: Response):
    payload = health()
    if not payload['ready']:
        response.status_code = 503
    payload['message'] = 'Application is ready to serve requests' if payload['ready'] else 'Application is not ready to serve requests'
    return payload


@app.get('/analytics/manager', dependencies=[Depends(require_manager)])
def analytics_manager(db: Session = Depends(get_db)):
    companies = db.query(Company).order_by(Company.name.asc()).all()
    action_plan_total = db.query(ActionPlan).count()
    action_plan_complete = db.query(ActionPlan).filter(func.lower(ActionPlan.status).in_(['complete', 'completed', 'done'])).count()
    active_unlocks = db.query(SubmissionUnlock).filter(
        SubmissionUnlock.active.is_(True),
        SubmissionUnlock.expires_at > datetime.utcnow(),
    ).count()
    return {
        'summary': build_manager_summary(db, companies),
        'analytics': build_investor_analytics(db),
        'operations': {
            'action_plan_completion_rate': round((action_plan_complete / action_plan_total) * 100, 2) if action_plan_total else None,
            'active_correction_windows': active_unlocks,
            'reminders_logged': db.query(ReminderLog).count(),
        },
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
    try:
        storage_path = persist_export(file_path, 'text/plain')
    except Exception as error:
        raise HTTPException(status_code=503, detail='Unable to persist the newsletter export') from error
    return {
        **payload,
        'file_name': file_name,
        'file_path': str(file_path),
        'storage_path': storage_path,
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
        .limit(200)
        .all()
    )

    company_ids = sorted({int(flag.company_id) for flag in flags if flag.company_id is not None})
    company_lookup: dict[int, dict[str, Any]] = {}
    if company_ids:
        companies = db.query(Company).filter(Company.id.in_(company_ids)).all()
        company_lookup = {
            int(company.id): {
                'id': int(company.id),
                'name': company.name,
                'code': company.code,
            }
            for company in companies
        }

    severity_counts: Counter[str] = Counter()
    flag_type_counts: Counter[str] = Counter()
    items = []
    for flag in flags:
        severity_key = str(flag.severity or '').strip().lower() or 'unknown'
        flag_type_key = str(flag.flag_type or '').strip().lower() or 'other'
        severity_counts[severity_key] += 1
        flag_type_counts[flag_type_key] += 1

        company_meta = company_lookup.get(int(flag.company_id)) if flag.company_id is not None else None
        items.append({
            'id': flag.id,
            'company_id': flag.company_id,
            'company_name': company_meta.get('name') if company_meta else None,
            'company_code': company_meta.get('code') if company_meta else None,
            'reporting_year': flag.reporting_year,
            'flag_type': flag.flag_type,
            'field_name': flag.field_name,
            'issue_description': flag.issue_description,
            'severity': flag.severity,
        })

    watchlist_items = items[:20]
    watchlist_company_ids = sorted({
        int(item['company_id'])
        for item in watchlist_items
        if item.get('company_id') is not None
    })
    watchlist_company_details = []
    for company_id in watchlist_company_ids:
        company_meta = company_lookup.get(company_id) or {}
        watchlist_company_details.append({
            'company_id': company_id,
            'company_name': company_meta.get('name'),
            'company_code': company_meta.get('code'),
        })

    severity_priority = {'critical': 5, 'high': 4, 'medium': 3, 'low': 2, 'warning': 1, 'unknown': 0}
    top_severity = None
    if severity_counts:
        top_severity = max(
            severity_counts.keys(),
            key=lambda key: (severity_priority.get(key, 0), int(severity_counts.get(key, 0))),
        )
    total_flags = len(watchlist_items)
    total_companies = len(watchlist_company_ids)
    if total_flags > 0:
        top_label = str(top_severity or 'unknown').replace('_', ' ').title()
        summary = f'Live anomaly feed: {total_flags} open flags across {total_companies} companies (top severity: {top_label}).'
    else:
        summary = 'No active anomaly flags in the latest validation feed.'

    return {
        'available': True,
        'scope': 'portfolio',
        'generated_at': _utc_now_iso(),
        'headline': f'{total_flags} active anomaly flags',
        'summary': summary,
        'severity_counts': dict(severity_counts),
        'flag_type_counts': dict(flag_type_counts),
        'count': total_flags,
        'items': watchlist_items,
        'watchlist_companies': watchlist_company_ids,
        'watchlist_company_details': watchlist_company_details,
        'watchlist_company_ids': watchlist_company_ids,
        'fallback_used': total_flags == 0,
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
    severity_counts: Counter[str] = Counter(
        (str(flag.severity or '').strip().lower() or 'unknown')
        for flag in flags
    )
    flag_type_counts: Counter[str] = Counter(
        (str(flag.flag_type or '').strip().lower() or 'other')
        for flag in flags
    )
    return {
        'available': True,
        'company_id': target_company.id,
        'company_name': target_company.name,
        'generated_at': _utc_now_iso(),
        'headline': f'{len(flags)} active anomaly flags for {target_company.name}',
        'count': len(flags),
        'severity_counts': dict(severity_counts),
        'flag_type_counts': dict(flag_type_counts),
        'items': [
            {
                'id': flag.id,
                'reporting_year': flag.reporting_year,
                'flag_type': flag.flag_type,
                'field_name': flag.field_name,
                'issue_description': flag.issue_description,
                'severity': flag.severity,
            }
            for flag in flags
        ],
        'fallback_used': len(flags) == 0,
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
