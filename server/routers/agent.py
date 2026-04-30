import json
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from models import CollectionCycle, Company, ReminderLog, ReviewAction, Submission, User, ValidationFlag

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

router = APIRouter(prefix="/agent", tags=["agent"])

OPENAI_MODEL = "gpt-4o"
ALLOWED_ROLES = {"company", "manager", "investor"}
SECTION_ORDER = ["environmental", "social", "governance"]
NUMERIC_VARIANCE_FIELDS = [
    "scope_1_emissions",
    "scope_2_location_based",
    "scope_3_emissions",
    "total_ghg_emissions",
    "total_energy_consumption",
    "renewable_energy_consumption",
    "total_water_withdrawal",
    "water_recycled_reused",
    "total_waste_generated",
    "waste_diverted_from_landfill",
    "hazardous_waste_generated",
    "female_representation_percent",
    "female_leadership_representation_percent",
    "independent_board_members_percent",
    "female_board_members_percent",
    "trifr",
]
REPORT_TYPES = {"edci", "sfdr"}


class AgentChatRequest(BaseModel):
    message: str
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    role: str | None = None


class ToolBaseCompanyYearRequest(BaseModel):
    company_id: str
    cycle_year: int


class ToolHistoricalRequest(BaseModel):
    company_id: str
    years: int = Field(default=3, ge=1, le=10)


class ToolSubmissionRequest(BaseModel):
    submission_id: str


class ToolPortfolioCycleRequest(BaseModel):
    cycle_year: int


class ToolFillFieldRequest(BaseModel):
    submission_id: str
    field_name: str
    value: Any


class ToolPostCommentRequest(BaseModel):
    submission_id: str
    section: str
    comment_text: str


class ToolReminderRequest(BaseModel):
    company_id: str


class ToolGenerateReportRequest(BaseModel):
    report_type: str
    cycle_year: int


class ToolTrendRequest(BaseModel):
    metric: str
    years: int = Field(default=3, ge=1, le=10)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _normalize_role(role: Any) -> str:
    if role is None:
        return ""
    value = role.value if hasattr(role, "value") else str(role)
    normalized = value.strip().lower()
    if normalized in {"admin", "manager"}:
        return "manager"
    if normalized in {"company", "investor"}:
        return normalized
    if normalized == "managerrole":
        return "manager"
    if normalized == "companyrole":
        return "company"
    return normalized


def get_user_role(x_user_role: str | None = Header(default=None)) -> str:
    return _normalize_role(x_user_role)


def get_user_email(x_user_email: str | None = Header(default=None)) -> str | None:
    return x_user_email.strip().lower() if x_user_email else None


def _parse_submission_payload(submission: Submission | None) -> dict[str, Any]:
    if not submission:
        return {}
    try:
        parsed = json.loads(submission.esg_data or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_submission_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or "not started"


def _status_label(value: Any) -> str:
    mapping = {
        "not started": "Not Started",
        "in progress": "In Progress",
        "submitted": "Submitted",
        "under review": "Under Review",
        "reviewed": "Reviewed",
        "approved": "Approved",
        "rejected": "Rejected",
        "resubmission requested": "Resubmission Requested",
        "draft": "Draft",
    }
    return mapping.get(_normalize_submission_status(value), "Not Started")


def _find_request_user(db: Session, email: str | None) -> User | None:
    if not email:
        return None
    return db.query(User).filter(User.email == email).first()


def _get_company_for_user(db: Session, email: str | None) -> Company | None:
    user = _find_request_user(db, email)
    if not user:
        return None
    return db.query(Company).filter(Company.user_id == user.id).first()


def _role_guard(role: str) -> str:
    normalized = _normalize_role(role)
    if normalized not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Unsupported or missing role")
    return normalized


def _require_company_role(role: str):
    if role != "company":
        raise HTTPException(status_code=403, detail="Only company users can perform this action")


def _require_manager_role(role: str):
    if role != "manager":
        raise HTTPException(status_code=403, detail="Only admin users can perform this action")


def _require_manager_or_investor(role: str):
    if role not in {"manager", "investor"}:
        raise HTTPException(status_code=403, detail="Only admin or investor users can perform this action")


def _submission_cycle_year(submission: Submission | None) -> int | None:
    if not submission:
        return None
    payload = _parse_submission_payload(submission)
    reporting_year = payload.get("reporting_year")
    parsed_year = _safe_int(reporting_year, default=0)
    if parsed_year > 0:
        return parsed_year
    if submission.cycle and submission.cycle.cycle_year:
        return _safe_int(submission.cycle.cycle_year, default=0) or None
    return None


def _find_cycle_by_year(db: Session, cycle_year: int) -> CollectionCycle | None:
    return db.query(CollectionCycle).filter(CollectionCycle.cycle_year == cycle_year).first()


def _resolve_company_identifier(db: Session, company_id: str) -> Company | None:
    raw = str(company_id or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        found = db.query(Company).filter(Company.id == int(raw)).first()
        if found:
            return found
    return (
        db.query(Company)
        .filter((Company.code == raw) | (Company.name == raw))
        .first()
    )


def _resolve_submission_for_role(
    db: Session,
    submission_id: str,
    role: str,
    email: str | None,
) -> Submission:
    if not str(submission_id or "").strip().isdigit():
        raise HTTPException(status_code=422, detail="submission_id must be a numeric string")
    submission = db.query(Submission).filter(Submission.id == int(submission_id)).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if role == "company":
        owned_company = _get_company_for_user(db, email)
        if not owned_company or owned_company.id != submission.company_id:
            raise HTTPException(status_code=403, detail="Submission is outside your company scope")
    elif role == "investor":
        raise HTTPException(status_code=403, detail="Investors cannot access submission-level data")
    return submission


def _check_company_scope(
    db: Session,
    role: str,
    email: str | None,
    requested_company_id: str,
) -> Company:
    company = _resolve_company_identifier(db, requested_company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    if role == "company":
        owned_company = _get_company_for_user(db, email)
        if not owned_company:
            raise HTTPException(status_code=403, detail="No company is linked to this user")
        if owned_company.id != company.id:
            raise HTTPException(status_code=403, detail="Requested company is outside your scope")
    elif role == "investor":
        raise HTTPException(status_code=403, detail="Investors cannot access company-level data")
    return company


def _serialize_submission_summary(submission: Submission, company: Company) -> dict[str, Any]:
    payload = _parse_submission_payload(submission)
    key_metrics = {
        "total_ghg_emissions": _safe_float(payload.get("total_ghg_emissions")),
        "scope_1_emissions": _safe_float(payload.get("scope_1_emissions")),
        "scope_2_location_based": _safe_float(payload.get("scope_2_location_based")),
        "scope_3_emissions": _safe_float(payload.get("scope_3_emissions")),
        "total_energy_consumption": _safe_float(payload.get("total_energy_consumption")),
        "renewable_energy_consumption": _safe_float(payload.get("renewable_energy_consumption")),
        "total_water_withdrawal": _safe_float(payload.get("total_water_withdrawal")),
        "total_waste_generated": _safe_float(payload.get("total_waste_generated")),
        "female_representation_percent": _safe_float(payload.get("female_representation_percent")),
        "independent_board_members_percent": _safe_float(payload.get("independent_board_members_percent")),
    }
    comments_by_section = _extract_submission_comments(payload)
    return {
        "submission_id": str(submission.id),
        "company": {
            "id": str(company.id),
            "name": company.name,
            "code": company.code,
            "sector": company.sector,
        },
        "cycle_year": _submission_cycle_year(submission),
        "status": _status_label(submission.status),
        "key_metrics": key_metrics,
        "comments_by_section": comments_by_section,
        "fields": payload,
    }


def _extract_submission_comments(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped = {section: [] for section in SECTION_ORDER}
    nested = payload.get("__section_comments")
    if isinstance(nested, dict):
        for section in SECTION_ORDER:
            raw = nested.get(section) or []
            if not isinstance(raw, list):
                continue
            clean_items = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                clean_items.append(
                    {
                        "text": text,
                        "author_role": str(item.get("author_role") or "company"),
                        "timestamp": str(item.get("timestamp") or datetime.now(timezone.utc).isoformat()),
                    }
                )
            grouped[section] = clean_items[-25:]
    for section in SECTION_ORDER:
        if grouped[section]:
            continue
        legacy = str(payload.get(f"section_comment_{section}") or "").strip()
        if legacy:
            grouped[section] = [
                {
                    "text": legacy,
                    "author_role": "company",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
    return grouped


def _append_section_comment(payload: dict[str, Any], section: str, text: str, author_role: str) -> dict[str, Any]:
    normalized_section = section.strip().lower()
    if normalized_section not in SECTION_ORDER:
        raise HTTPException(status_code=422, detail="section must be one of environmental, social, governance")
    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="comment_text cannot be empty")

    merged = dict(payload or {})
    comments = _extract_submission_comments(merged)
    section_items = list(comments.get(normalized_section) or [])
    section_items.append(
        {
            "text": cleaned,
            "author_role": author_role,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )
    comments[normalized_section] = section_items[-25:]
    merged["__section_comments"] = comments
    merged[f"section_comment_{normalized_section}"] = cleaned
    return merged


def _latest_submission_by_company_for_cycle(db: Session, cycle: CollectionCycle) -> list[Submission]:
    submissions = (
        db.query(Submission)
        .filter(Submission.cycle_id == cycle.id)
        .order_by(Submission.company_id.asc(), Submission.id.desc())
        .all()
    )
    latest_by_company: dict[int, Submission] = {}
    for submission in submissions:
        if submission.company_id not in latest_by_company:
            latest_by_company[submission.company_id] = submission
    return list(latest_by_company.values())


def _portfolio_metric_from_payload(payload: dict[str, Any]) -> dict[str, float]:
    return {
        "total_ghg_emissions": _safe_float(payload.get("total_ghg_emissions")),
        "scope_1_emissions": _safe_float(payload.get("scope_1_emissions")),
        "scope_2_location_based": _safe_float(payload.get("scope_2_location_based")),
        "scope_3_emissions": _safe_float(payload.get("scope_3_emissions")),
        "total_energy_consumption": _safe_float(payload.get("total_energy_consumption")),
        "renewable_energy_consumption": _safe_float(payload.get("renewable_energy_consumption")),
        "total_water_withdrawal": _safe_float(payload.get("total_water_withdrawal")),
        "total_waste_generated": _safe_float(payload.get("total_waste_generated")),
        "female_representation_percent": _safe_float(payload.get("female_representation_percent")),
        "trifr": _safe_float(payload.get("trifr")),
        "independent_board_members_percent": _safe_float(payload.get("independent_board_members_percent")),
    }


def _compute_esg_score(metric: dict[str, float], payload: dict[str, Any]) -> float:
    scope_total = metric["scope_1_emissions"] + metric["scope_2_location_based"] + metric["scope_3_emissions"]
    renewable_ratio = (
        metric["renewable_energy_consumption"] / metric["total_energy_consumption"]
        if metric["total_energy_consumption"] > 0
        else 0.0
    )
    reduction_target = _safe_float(payload.get("reduction_target_percent"))
    female_rep = metric["female_representation_percent"]
    trifr = metric["trifr"]
    independent_board = metric["independent_board_members_percent"]
    corruption_cases = _safe_float(payload.get("confirmed_cases_of_corruption"))

    def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
        return max(minimum, min(maximum, value))

    e_score = _clamp(30 + max(0, 35 - (scope_total / 60)) + min(20, reduction_target * 0.25) + min(15, renewable_ratio * 100 * 0.2))
    s_score = _clamp(25 + min(25, female_rep * 0.35) + max(0, 20 - trifr * 2.5))
    g_score = _clamp(
        (20 if str(payload.get("esg_policy_in_place", "")).strip().lower() == "yes" else 0)
        + (20 if str(payload.get("board_level_esg_oversight", "")).strip().lower() == "yes" else 0)
        + (20 if str(payload.get("cybersecurity_policy_in_place", "")).strip().lower() == "yes" else 0)
        + (20 if str(payload.get("anti_bribery_corruption_policy", "")).strip().lower() == "yes" else 0)
        + min(20, independent_board * 0.4)
        - min(10, corruption_cases * 2)
    )
    return round((0.45 * e_score) + (0.30 * s_score) + (0.25 * g_score), 2)


def _aggregate_portfolio_metrics_for_cycle(db: Session, cycle_year: int) -> dict[str, Any]:
    cycle = _find_cycle_by_year(db, cycle_year)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle year not found")
    latest_submissions = _latest_submission_by_company_for_cycle(db, cycle)
    if not latest_submissions:
        return {
            "cycle_year": cycle_year,
            "company_count": 0,
            "submission_count": 0,
            "status_counts": {},
            "averages": {},
            "totals": {},
            "portfolio_esg_score": 0.0,
        }

    status_counts: dict[str, int] = {}
    totals = {
        "total_ghg_emissions": 0.0,
        "scope_1_emissions": 0.0,
        "scope_2_location_based": 0.0,
        "scope_3_emissions": 0.0,
        "total_energy_consumption": 0.0,
        "renewable_energy_consumption": 0.0,
        "total_water_withdrawal": 0.0,
        "total_waste_generated": 0.0,
        "female_representation_percent": 0.0,
        "trifr": 0.0,
        "independent_board_members_percent": 0.0,
    }
    score_total = 0.0
    counted = 0
    for submission in latest_submissions:
        payload = _parse_submission_payload(submission)
        metric = _portfolio_metric_from_payload(payload)
        for key in totals:
            totals[key] += metric[key]
        score_total += _compute_esg_score(metric, payload)
        counted += 1
        label = _status_label(submission.status)
        status_counts[label] = status_counts.get(label, 0) + 1

    divisor = max(counted, 1)
    averages = {key: round(value / divisor, 2) for key, value in totals.items()}
    rounded_totals = {key: round(value, 2) for key, value in totals.items()}
    return {
        "cycle_year": cycle_year,
        "company_count": counted,
        "submission_count": counted,
        "status_counts": status_counts,
        "averages": averages,
        "totals": rounded_totals,
        "portfolio_esg_score": round(score_total / divisor, 2),
    }


def tool_get_submission(
    db: Session,
    role: str,
    email: str | None,
    company_id: str,
    cycle_year: int,
) -> dict[str, Any]:
    company = _check_company_scope(db, role, email, company_id)
    cycle = _find_cycle_by_year(db, cycle_year)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle year not found")
    submission = (
        db.query(Submission)
        .filter(Submission.company_id == company.id, Submission.cycle_id == cycle.id)
        .order_by(Submission.id.desc())
        .first()
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found for company and cycle")
    return _serialize_submission_summary(submission, company)


def tool_get_historical_data(
    db: Session,
    role: str,
    email: str | None,
    company_id: str,
    years: int = 3,
) -> dict[str, Any]:
    company = _check_company_scope(db, role, email, company_id)
    approved_submissions = (
        db.query(Submission)
        .filter(Submission.company_id == company.id)
        .all()
    )
    rows = []
    for submission in approved_submissions:
        if _normalize_submission_status(submission.status) != "approved":
            continue
        year = _submission_cycle_year(submission)
        if year is None:
            continue
        rows.append((year, submission.id, submission))
    rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = rows[: max(1, years)]
    history = []
    for year, _, submission in selected:
        payload = _parse_submission_payload(submission)
        history.append(
            {
                "submission_id": str(submission.id),
                "cycle_year": year,
                "status": _status_label(submission.status),
                "key_metrics": {
                    "total_ghg_emissions": _safe_float(payload.get("total_ghg_emissions")),
                    "total_energy_consumption": _safe_float(payload.get("total_energy_consumption")),
                    "total_water_withdrawal": _safe_float(payload.get("total_water_withdrawal")),
                    "total_waste_generated": _safe_float(payload.get("total_waste_generated")),
                    "female_representation_percent": _safe_float(payload.get("female_representation_percent")),
                    "independent_board_members_percent": _safe_float(payload.get("independent_board_members_percent")),
                },
                "fields": payload,
            }
        )
    return {
        "company": {"id": str(company.id), "name": company.name, "code": company.code},
        "years_requested": years,
        "records_returned": len(history),
        "history": history,
    }


def tool_get_variance_flags(
    db: Session,
    role: str,
    email: str | None,
    submission_id: str,
) -> dict[str, Any]:
    submission = _resolve_submission_for_role(db, submission_id, role, email)
    current_payload = _parse_submission_payload(submission)
    company = db.query(Company).filter(Company.id == submission.company_id).first()
    reporting_year = _submission_cycle_year(submission)

    candidates = (
        db.query(Submission)
        .filter(
            Submission.company_id == submission.company_id,
            Submission.id != submission.id,
        )
        .all()
    )
    approved_prior: list[tuple[int, int, Submission]] = []
    for candidate in candidates:
        if _normalize_submission_status(candidate.status) != "approved":
            continue
        year = _submission_cycle_year(candidate)
        if year is None:
            continue
        if reporting_year is None or year < reporting_year:
            approved_prior.append((year, candidate.id, candidate))
    approved_prior.sort(key=lambda item: (item[0], item[1]))
    prior_submission = approved_prior[-1][2] if approved_prior else None
    prior_payload = _parse_submission_payload(prior_submission)

    threshold = 20.0
    variance_items = []
    for field_name in NUMERIC_VARIANCE_FIELDS:
        current = _safe_float(current_payload.get(field_name), default=float("nan"))
        prior = _safe_float(prior_payload.get(field_name), default=float("nan"))
        if current != current or prior != prior or prior == 0:
            continue
        variance_pct = round(((current - prior) / abs(prior)) * 100, 2)
        if abs(variance_pct) <= threshold:
            continue
        severity = "high" if abs(variance_pct) > 30 else "medium"
        variance_items.append(
            {
                "field_name": field_name,
                "current_value": round(current, 4),
                "prior_value": round(prior, 4),
                "variance_percent": variance_pct,
                "threshold_percent": threshold,
                "severity": severity,
            }
        )

    db_flags = []
    if reporting_year is not None:
        related_flags = (
            db.query(ValidationFlag)
            .filter(
                ValidationFlag.company_id == submission.company_id,
                ValidationFlag.reporting_year == reporting_year,
            )
            .order_by(ValidationFlag.id.desc())
            .all()
        )
        for flag in related_flags:
            if str(flag.flag_type or "").strip().lower() not in {"variance", "anomaly", "manual validation"}:
                continue
            db_flags.append(
                {
                    "field_name": flag.field_name,
                    "issue_description": flag.issue_description,
                    "severity": str(flag.severity or "").lower(),
                    "flag_type": flag.flag_type,
                }
            )

    return {
        "submission_id": str(submission.id),
        "company": {"id": str(company.id) if company else None, "name": company.name if company else None},
        "reporting_year": reporting_year,
        "prior_submission_id": str(prior_submission.id) if prior_submission else None,
        "variance_flags": variance_items,
        "existing_validation_flags": db_flags,
    }


def tool_get_portfolio_metrics(
    db: Session,
    role: str,
    cycle_year: int,
) -> dict[str, Any]:
    _require_manager_or_investor(role)
    return _aggregate_portfolio_metrics_for_cycle(db, cycle_year)


def tool_get_pending_approvals(db: Session, role: str) -> dict[str, Any]:
    _require_manager_role(role)
    pending_statuses = {"reviewed", "under review"}
    submissions = db.query(Submission).order_by(Submission.id.desc()).all()
    items = []
    for submission in submissions:
        normalized = _normalize_submission_status(submission.status)
        if normalized not in pending_statuses:
            continue
        company = db.query(Company).filter(Company.id == submission.company_id).first()
        items.append(
            {
                "submission_id": str(submission.id),
                "company_name": company.name if company else None,
                "company_code": company.code if company else None,
                "cycle_year": _submission_cycle_year(submission),
                "status": _status_label(submission.status),
            }
        )
    return {"count": len(items), "items": items}


def tool_get_anomaly_flags(db: Session, role: str, cycle_year: int) -> dict[str, Any]:
    _require_manager_role(role)
    cycle = _find_cycle_by_year(db, cycle_year)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle year not found")

    submissions = _latest_submission_by_company_for_cycle(db, cycle)
    numeric_matrix: dict[str, list[tuple[int, float]]] = {field: [] for field in NUMERIC_VARIANCE_FIELDS}
    for submission in submissions:
        payload = _parse_submission_payload(submission)
        for field_name in NUMERIC_VARIANCE_FIELDS:
            value = _safe_float(payload.get(field_name), default=float("nan"))
            if value == value:
                numeric_matrix[field_name].append((submission.company_id, value))

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
        for company_id, value in values:
            z_score = (value - mean) / std_dev
            if abs(z_score) >= 2.0:
                company = db.query(Company).filter(Company.id == company_id).first()
                anomalies.append(
                    {
                        "company_id": str(company_id),
                        "company_name": company.name if company else None,
                        "field_name": field_name,
                        "value": round(value, 4),
                        "portfolio_mean": round(mean, 4),
                        "z_score": round(z_score, 3),
                        "severity": "high" if abs(z_score) >= 3.0 else "medium",
                    }
                )

    validation_flags = (
        db.query(ValidationFlag)
        .filter(ValidationFlag.reporting_year == cycle_year)
        .order_by(ValidationFlag.id.desc())
        .all()
    )
    top_manual_flags = []
    for flag in validation_flags[:50]:
        company = db.query(Company).filter(Company.id == flag.company_id).first()
        top_manual_flags.append(
            {
                "company_id": str(flag.company_id),
                "company_name": company.name if company else None,
                "field_name": flag.field_name,
                "issue_description": flag.issue_description,
                "severity": flag.severity,
                "flag_type": flag.flag_type,
            }
        )
    return {
        "cycle_year": cycle_year,
        "statistical_outliers": anomalies,
        "validation_flag_watchlist": top_manual_flags[:20],
    }


def tool_get_company_comments(
    db: Session,
    role: str,
    email: str | None,
    submission_id: str,
) -> dict[str, Any]:
    submission = _resolve_submission_for_role(db, submission_id, role, email)
    payload = _parse_submission_payload(submission)
    comments_by_section = _extract_submission_comments(payload)

    workflow_comments = []
    reporting_year = _submission_cycle_year(submission)
    if reporting_year is not None:
        review_rows = (
            db.query(ReviewAction)
            .filter(
                ReviewAction.company_id == submission.company_id,
                ReviewAction.reporting_year == reporting_year,
            )
            .order_by(ReviewAction.id.desc())
            .all()
        )
        for row in review_rows:
            text = str(row.review_comment or "").strip()
            if not text:
                continue
            workflow_comments.append(
                {
                    "text": text,
                    "review_status": row.review_status,
                    "reviewer_role": row.reviewer_role,
                    "record_id": str(row.id),
                }
            )
    comments_by_section["workflow"] = workflow_comments
    return {
        "submission_id": str(submission.id),
        "comments_by_section": comments_by_section,
    }


def tool_fill_form_field(
    db: Session,
    role: str,
    email: str | None,
    submission_id: str,
    field_name: str,
    value: Any,
) -> dict[str, Any]:
    _require_company_role(role)
    submission = _resolve_submission_for_role(db, submission_id, role, email)
    normalized_status = _normalize_submission_status(submission.status)
    editable_statuses = {"draft", "not started", "in progress", "resubmission requested", "rejected"}
    if normalized_status not in editable_statuses:
        raise HTTPException(status_code=403, detail="This submission is not editable in its current status")

    clean_field_name = str(field_name or "").strip()
    if not clean_field_name:
        raise HTTPException(status_code=422, detail="field_name is required")

    payload = _parse_submission_payload(submission)
    payload[clean_field_name] = value
    submission.esg_data = json.dumps(payload)
    db.commit()
    db.refresh(submission)
    return {
        "submission_id": str(submission.id),
        "field_name": clean_field_name,
        "updated": True,
        "status": _status_label(submission.status),
    }


def tool_post_comment(
    db: Session,
    role: str,
    email: str | None,
    submission_id: str,
    section: str,
    comment_text: str,
) -> dict[str, Any]:
    _require_company_role(role)
    submission = _resolve_submission_for_role(db, submission_id, role, email)
    payload = _parse_submission_payload(submission)
    merged = _append_section_comment(payload, section, comment_text, author_role="company")
    submission.esg_data = json.dumps(merged)
    db.commit()
    db.refresh(submission)
    grouped = _extract_submission_comments(merged)
    normalized_section = section.strip().lower()
    latest_comment = grouped.get(normalized_section, [])[-1] if grouped.get(normalized_section) else None
    return {
        "submission_id": str(submission.id),
        "section": normalized_section,
        "saved": True,
        "latest_comment": latest_comment,
    }


def tool_send_reminder(
    db: Session,
    role: str,
    email: str | None,
    company_id: str,
) -> dict[str, Any]:
    _require_manager_role(role)
    company = _resolve_company_identifier(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    sender = _find_request_user(db, email)
    active_cycle = (
        db.query(CollectionCycle)
        .filter(func.lower(CollectionCycle.status) == "active")
        .order_by(CollectionCycle.cycle_year.desc())
        .first()
    ) or db.query(CollectionCycle).order_by(CollectionCycle.cycle_year.desc()).first()
    if not active_cycle:
        raise HTTPException(status_code=404, detail="No collection cycle found")

    message = f"Reminder: please complete your ESG submission for cycle {active_cycle.cycle_year}."
    reminder = ReminderLog(
        company_id=company.id,
        cycle_id=active_cycle.id,
        sent_by_user_id=sender.id if sender else None,
        channel="email",
        message=message,
        delivery_status="logged",
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return {
        "reminder_id": str(reminder.id),
        "company": {"id": str(company.id), "name": company.name},
        "cycle_year": active_cycle.cycle_year,
        "channel": reminder.channel,
        "delivery_status": reminder.delivery_status,
    }


def tool_generate_report(
    db: Session,
    role: str,
    report_type: str,
    cycle_year: int,
) -> dict[str, Any]:
    _require_manager_or_investor(role)
    normalized_type = str(report_type or "").strip().lower()
    if normalized_type not in REPORT_TYPES:
        raise HTTPException(status_code=422, detail="report_type must be edci or sfdr")
    metrics = _aggregate_portfolio_metrics_for_cycle(db, cycle_year)
    if normalized_type == "edci":
        return {
            "report_type": "EDCI",
            "cycle_year": cycle_year,
            "portfolio_summary": {
                "portfolio_esg_score": metrics["portfolio_esg_score"],
                "company_count": metrics["company_count"],
                "status_counts": metrics["status_counts"],
            },
            "environmental": {
                "total_ghg_emissions": metrics.get("totals", {}).get("total_ghg_emissions", 0.0),
                "total_energy_consumption": metrics.get("totals", {}).get("total_energy_consumption", 0.0),
                "total_water_withdrawal": metrics.get("totals", {}).get("total_water_withdrawal", 0.0),
                "total_waste_generated": metrics.get("totals", {}).get("total_waste_generated", 0.0),
            },
            "social_governance": {
                "average_female_representation_percent": metrics.get("averages", {}).get("female_representation_percent", 0.0),
                "average_independent_board_members_percent": metrics.get("averages", {}).get("independent_board_members_percent", 0.0),
            },
        }
    return {
        "report_type": "SFDR_PAI",
        "cycle_year": cycle_year,
        "pai_indicators": {
            "ghg_total_tco2e": metrics.get("totals", {}).get("total_ghg_emissions", 0.0),
            "average_trifr": metrics.get("averages", {}).get("trifr", 0.0),
            "average_female_representation_percent": metrics.get("averages", {}).get("female_representation_percent", 0.0),
            "average_independent_board_members_percent": metrics.get("averages", {}).get("independent_board_members_percent", 0.0),
        },
        "portfolio_context": {
            "company_count": metrics["company_count"],
            "status_counts": metrics["status_counts"],
            "portfolio_esg_score": metrics["portfolio_esg_score"],
        },
    }


def tool_get_portfolio_trends(
    db: Session,
    role: str,
    metric: str,
    years: int = 3,
) -> dict[str, Any]:
    _require_manager_or_investor(role)
    clean_metric = str(metric or "").strip()
    if not clean_metric:
        raise HTTPException(status_code=422, detail="metric is required")

    cycles = (
        db.query(CollectionCycle)
        .filter(CollectionCycle.cycle_year > 0)
        .order_by(CollectionCycle.cycle_year.desc())
        .limit(max(1, years))
        .all()
    )
    if not cycles:
        return {"metric": clean_metric, "years_requested": years, "trend": []}

    trend = []
    for cycle in sorted(cycles, key=lambda c: c.cycle_year):
        summary = _aggregate_portfolio_metrics_for_cycle(db, cycle.cycle_year)
        metric_value = None
        if clean_metric == "portfolio_esg_score":
            metric_value = summary.get("portfolio_esg_score")
        elif clean_metric in summary.get("averages", {}):
            metric_value = summary["averages"][clean_metric]
        elif clean_metric in summary.get("totals", {}):
            metric_value = summary["totals"][clean_metric]
        else:
            raise HTTPException(status_code=422, detail="Unsupported metric for trend analysis")
        trend.append({"cycle_year": cycle.cycle_year, "value": metric_value})

    yoy = []
    for index in range(1, len(trend)):
        previous = _safe_float(trend[index - 1]["value"], default=0.0)
        current = _safe_float(trend[index]["value"], default=0.0)
        change_pct = None if previous == 0 else round(((current - previous) / abs(previous)) * 100, 2)
        yoy.append(
            {
                "from_year": trend[index - 1]["cycle_year"],
                "to_year": trend[index]["cycle_year"],
                "change_percent": change_pct,
            }
        )
    return {"metric": clean_metric, "years_requested": years, "trend": trend, "yoy_changes": yoy}


def tool_get_all_comments(db: Session, role: str, cycle_year: int | None = None) -> dict[str, Any]:
    _require_manager_role(role)
    query = db.query(Submission).order_by(Submission.id.desc())
    submissions = query.all()
    items = []
    for submission in submissions:
        year = _submission_cycle_year(submission)
        if cycle_year is not None and year != cycle_year:
            continue
        payload = _parse_submission_payload(submission)
        grouped = _extract_submission_comments(payload)
        has_comments = any(grouped.get(section) for section in SECTION_ORDER)
        if not has_comments:
            continue
        company = db.query(Company).filter(Company.id == submission.company_id).first()
        items.append(
            {
                "submission_id": str(submission.id),
                "company_name": company.name if company else None,
                "cycle_year": year,
                "comments_by_section": grouped,
            }
        )
    return {"count": len(items), "items": items}


def _ensure_openai_client() -> OpenAI:
    api_key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")
    if OpenAI is None:
        raise HTTPException(status_code=503, detail="openai SDK is not available")
    return OpenAI(api_key=api_key)


def _tool_definitions_for_role(role: str) -> list[dict[str, Any]]:
    company_read_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_submission",
                "description": "Return ESG submission data for a company and cycle year.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company_id": {"type": "string"},
                        "cycle_year": {"type": "integer"},
                    },
                    "required": ["company_id", "cycle_year"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_historical_data",
                "description": "Return approved ESG submission data for previous years.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company_id": {"type": "string"},
                        "years": {"type": "integer", "default": 3},
                    },
                    "required": ["company_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_variance_flags",
                "description": "Return material variance flags for a submission.",
                "parameters": {
                    "type": "object",
                    "properties": {"submission_id": {"type": "string"}},
                    "required": ["submission_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_company_comments",
                "description": "Return submission comments grouped by section.",
                "parameters": {
                    "type": "object",
                    "properties": {"submission_id": {"type": "string"}},
                    "required": ["submission_id"],
                },
            },
        },
    ]
    company_write_tools = [
        {
            "type": "function",
            "function": {
                "name": "fill_form_field",
                "description": "Update one field in a draft company submission.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "submission_id": {"type": "string"},
                        "field_name": {"type": "string"},
                        "value": {},
                    },
                    "required": ["submission_id", "field_name", "value"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "post_comment",
                "description": "Save a comment for environmental/social/governance section.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "submission_id": {"type": "string"},
                        "section": {"type": "string"},
                        "comment_text": {"type": "string"},
                    },
                    "required": ["submission_id", "section", "comment_text"],
                },
            },
        },
    ]
    admin_plus = [
        {
            "type": "function",
            "function": {
                "name": "get_portfolio_metrics",
                "description": "Return portfolio-wide ESG aggregates for a cycle.",
                "parameters": {
                    "type": "object",
                    "properties": {"cycle_year": {"type": "integer"}},
                    "required": ["cycle_year"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_pending_approvals",
                "description": "Return submissions awaiting approval.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_anomaly_flags",
                "description": "Return cross-company outliers for a cycle.",
                "parameters": {
                    "type": "object",
                    "properties": {"cycle_year": {"type": "integer"}},
                    "required": ["cycle_year"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "send_reminder",
                "description": "Log a reminder email trigger for a company.",
                "parameters": {
                    "type": "object",
                    "properties": {"company_id": {"type": "string"}},
                    "required": ["company_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_all_comments",
                "description": "Return comments across submissions (admin only).",
                "parameters": {
                    "type": "object",
                    "properties": {"cycle_year": {"type": "integer"}},
                },
            },
        },
    ]
    investor_plus = [
        {
            "type": "function",
            "function": {
                "name": "get_portfolio_metrics",
                "description": "Return portfolio-wide ESG aggregates for a cycle.",
                "parameters": {
                    "type": "object",
                    "properties": {"cycle_year": {"type": "integer"}},
                    "required": ["cycle_year"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_portfolio_trends",
                "description": "Return year-on-year trends for a portfolio metric.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": {"type": "string"},
                        "years": {"type": "integer", "default": 3},
                    },
                    "required": ["metric"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_report",
                "description": "Generate portfolio-level EDCI or SFDR-PAI report data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "report_type": {"type": "string"},
                        "cycle_year": {"type": "integer"},
                    },
                    "required": ["report_type", "cycle_year"],
                },
            },
        },
    ]

    if role == "company":
        return company_read_tools + company_write_tools
    if role == "manager":
        return company_read_tools + admin_plus + investor_plus
    if role == "investor":
        return investor_plus
    return []


def _execute_tool_call(
    *,
    tool_name: str,
    args: dict[str, Any],
    db: Session,
    role: str,
    email: str | None,
) -> dict[str, Any]:
    if tool_name == "get_submission":
        return tool_get_submission(db, role, email, args["company_id"], _safe_int(args["cycle_year"]))
    if tool_name == "get_historical_data":
        return tool_get_historical_data(db, role, email, args["company_id"], _safe_int(args.get("years", 3), 3))
    if tool_name == "get_variance_flags":
        return tool_get_variance_flags(db, role, email, args["submission_id"])
    if tool_name == "get_company_comments":
        return tool_get_company_comments(db, role, email, args["submission_id"])
    if tool_name == "fill_form_field":
        return tool_fill_form_field(db, role, email, args["submission_id"], args["field_name"], args.get("value"))
    if tool_name == "post_comment":
        return tool_post_comment(db, role, email, args["submission_id"], args["section"], args["comment_text"])
    if tool_name == "get_portfolio_metrics":
        return tool_get_portfolio_metrics(db, role, _safe_int(args["cycle_year"]))
    if tool_name == "get_pending_approvals":
        return tool_get_pending_approvals(db, role)
    if tool_name == "get_anomaly_flags":
        return tool_get_anomaly_flags(db, role, _safe_int(args["cycle_year"]))
    if tool_name == "send_reminder":
        return tool_send_reminder(db, role, email, args["company_id"])
    if tool_name == "generate_report":
        return tool_generate_report(db, role, str(args["report_type"]), _safe_int(args["cycle_year"]))
    if tool_name == "get_portfolio_trends":
        return tool_get_portfolio_trends(db, role, str(args["metric"]), _safe_int(args.get("years", 3), 3))
    if tool_name == "get_all_comments":
        return tool_get_all_comments(db, role, _safe_int(args.get("cycle_year"), 0) or None)
    raise HTTPException(status_code=400, detail=f"Unsupported tool: {tool_name}")


def _sanitize_history(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    sanitized = []
    for entry in history or []:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or "").strip().lower()
        content = str(entry.get("content") or "").strip()
        if role not in {"system", "user", "assistant"} or not content:
            continue
        sanitized.append({"role": role, "content": content})
    return sanitized[-30:]


@router.post("/chat")
def agent_chat(
    payload: AgentChatRequest,
    db: Session = Depends(get_db),
    role_header: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    role = _role_guard(role_header)
    body_role = _normalize_role(payload.role or "")
    if body_role and body_role != role:
        raise HTTPException(status_code=403, detail="Role mismatch between request body and authenticated context")

    clean_message = str(payload.message or "").strip()
    if not clean_message:
        raise HTTPException(status_code=422, detail="message is required")

    if role == "company" and not _get_company_for_user(db, email):
        raise HTTPException(status_code=403, detail="No company is linked to this company user")

    client = _ensure_openai_client()
    tools = _tool_definitions_for_role(role)

    system_message = {
        "role": "system",
        "content": (
            "You are an ESG data assistant embedded in an ESG reporting platform. "
            "Use tools to fetch data before answering. "
            "Never invent values. "
            f"Current user role is '{role}'. "
            "Respect role access boundaries and provide concise professional ESG responses."
        ),
    }
    conversation = [system_message] + _sanitize_history(payload.conversation_history)
    conversation.append({"role": "user", "content": clean_message})

    tools_used: list[str] = []
    max_rounds = 5
    for _ in range(max_rounds):
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=conversation,
                tools=tools,
                tool_choice="auto",
                temperature=0.1,
            )
        except HTTPException:
            raise
        except Exception as exc:
            error_text = str(exc or "").strip()
            lowered = error_text.lower()
            if "insufficient_quota" in lowered or "rate limit" in lowered or "429" in lowered:
                raise HTTPException(
                    status_code=429,
                    detail="Agent model quota/rate limit reached. Please try again shortly.",
                )
            raise HTTPException(
                status_code=503,
                detail="Agent model is temporarily unavailable. Please try again shortly.",
            )
        choice = (response.choices or [None])[0]
        if not choice or not choice.message:
            raise HTTPException(status_code=502, detail="No response from language model")
        message = choice.message
        assistant_record: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
        if getattr(message, "tool_calls", None):
            assistant_record["tool_calls"] = []
            for call in message.tool_calls:
                assistant_record["tool_calls"].append(
                    {
                        "id": call.id,
                        "type": call.type,
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                )
        conversation.append(assistant_record)

        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            final_response = str(message.content or "").strip()
            final_history = _sanitize_history(payload.conversation_history)
            final_history.append({"role": "user", "content": clean_message})
            final_history.append({"role": "assistant", "content": final_response})
            return {
                "response": final_response,
                "tools_used": tools_used,
                "conversation_history": final_history[-40:],
            }

        for call in tool_calls:
            tool_name = call.function.name
            if tool_name not in [item["function"]["name"] for item in tools]:
                raise HTTPException(status_code=403, detail=f"Tool '{tool_name}' is not allowed for role '{role}'")
            try:
                args = json.loads(call.function.arguments or "{}")
                if not isinstance(args, dict):
                    args = {}
            except ValueError:
                args = {}
            tool_result = _execute_tool_call(tool_name=tool_name, args=args, db=db, role=role, email=email)
            tools_used.append(tool_name)
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": tool_name,
                    "content": json.dumps(tool_result),
                }
            )

    raise HTTPException(status_code=502, detail="Agent loop exceeded maximum tool rounds")


@router.post("/tools/get_submission")
def get_submission_endpoint(
    payload: ToolBaseCompanyYearRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    return tool_get_submission(db, _role_guard(role), email, payload.company_id, payload.cycle_year)


@router.post("/tools/get_historical_data")
def get_historical_data_endpoint(
    payload: ToolHistoricalRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    return tool_get_historical_data(db, _role_guard(role), email, payload.company_id, payload.years)


@router.post("/tools/get_variance_flags")
def get_variance_flags_endpoint(
    payload: ToolSubmissionRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    return tool_get_variance_flags(db, _role_guard(role), email, payload.submission_id)


@router.post("/tools/get_portfolio_metrics")
def get_portfolio_metrics_endpoint(
    payload: ToolPortfolioCycleRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    return tool_get_portfolio_metrics(db, _role_guard(role), payload.cycle_year)


@router.post("/tools/get_pending_approvals")
def get_pending_approvals_endpoint(
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    return tool_get_pending_approvals(db, _role_guard(role))


@router.post("/tools/get_anomaly_flags")
def get_anomaly_flags_endpoint(
    payload: ToolPortfolioCycleRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    return tool_get_anomaly_flags(db, _role_guard(role), payload.cycle_year)


@router.post("/tools/get_company_comments")
def get_company_comments_endpoint(
    payload: ToolSubmissionRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    return tool_get_company_comments(db, _role_guard(role), email, payload.submission_id)


@router.post("/tools/fill_form_field")
def fill_form_field_endpoint(
    payload: ToolFillFieldRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    return tool_fill_form_field(
        db,
        _role_guard(role),
        email,
        payload.submission_id,
        payload.field_name,
        payload.value,
    )


@router.post("/tools/post_comment")
def post_comment_endpoint(
    payload: ToolPostCommentRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    return tool_post_comment(
        db,
        _role_guard(role),
        email,
        payload.submission_id,
        payload.section,
        payload.comment_text,
    )


@router.post("/tools/send_reminder")
def send_reminder_endpoint(
    payload: ToolReminderRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
    email: str | None = Depends(get_user_email),
):
    return tool_send_reminder(db, _role_guard(role), email, payload.company_id)


@router.post("/tools/generate_report")
def generate_report_endpoint(
    payload: ToolGenerateReportRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    return tool_generate_report(db, _role_guard(role), payload.report_type, payload.cycle_year)


@router.post("/tools/get_portfolio_trends")
def get_portfolio_trends_endpoint(
    payload: ToolTrendRequest,
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    return tool_get_portfolio_trends(db, _role_guard(role), payload.metric, payload.years)


@router.post("/tools/get_all_comments")
def get_all_comments_endpoint(
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    role: str = Depends(get_user_role),
):
    cycle_year = payload.get("cycle_year")
    parsed_cycle_year = _safe_int(cycle_year, default=0) or None
    return tool_get_all_comments(db, _role_guard(role), parsed_cycle_year)
