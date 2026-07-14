import json
import hashlib
from enum import Enum
from datetime import datetime
from typing import Optional, Dict

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

# Re-using your existing database setup and models
from database import SessionLocal
from models import AuthSession, CollectionCycle, Company, Submission, User

router = APIRouter()

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_authenticated_user(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias='esg_session'),
    db: Session = Depends(get_db),
) -> User:
    bearer = authorization.split(' ', 1)[1].strip() if authorization and authorization.lower().startswith('bearer ') else ''
    raw_token = bearer or str(session_cookie or '').strip()
    if not raw_token:
        raise HTTPException(status_code=401, detail='Authentication required')
    session = db.query(AuthSession).filter(
        AuthSession.token_hash == hashlib.sha256(raw_token.encode('utf-8')).hexdigest(),
        AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > datetime.utcnow(),
    ).first()
    user = db.query(User).filter(User.id == session.user_id).first() if session else None
    if not user:
        raise HTTPException(status_code=401, detail='Session expired or invalid')
    return user


# ==========================================
# Task 1: Pydantic Data Structures
# ==========================================

class ConfidenceLevel(str, Enum):
    MEASURED = 'Measured'
    ESTIMATED = 'Estimated'
    NOT_AVAILABLE = 'Not Available'


class EnvironmentalMetrics(BaseModel):
    scope_1_emissions: float = Field(ge=0)
    scope_1_confidence: ConfidenceLevel
    scope_2_location_based: float = Field(ge=0)
    scope_2_confidence: ConfidenceLevel
    scope_3_emissions: float = Field(ge=0)
    scope_3_confidence: ConfidenceLevel

    @property
    def total_ghg_emissions(self) -> float:
        """Dynamically calculates the sum of all scope emissions."""
        return self.scope_1_emissions + self.scope_2_location_based + self.scope_3_emissions


class SocialMetrics(BaseModel):
    whs_policy_in_place: bool
    whs_document_reference: Optional[str] = None
    trifr: float = Field(ge=0)
    female_representation_percent: float = Field(ge=0, le=100)


class GovernanceMetrics(BaseModel):
    esg_policy_in_place: bool
    esg_document_reference: Optional[str] = None
    female_board_members_percent: float = Field(ge=0, le=100)


class ESGSubmissionCreate(BaseModel):
    company_id: int
    reporting_year: int
    submission_notes: Optional[str] = None
    
    environmental: EnvironmentalMetrics
    social: SocialMetrics
    governance: GovernanceMetrics
    
    # Used to pass previous year's data for validation without saving it to the new record
    prefilled_data: Optional[Dict[str, float]] = Field(default=None, exclude=True)

    # ==========================================
    # Task 2: Business Logic & Validation
    # ==========================================
    @model_validator(mode='after')
    def validate_business_logic(self):
        if not 2000 <= self.reporting_year <= datetime.utcnow().year + 5:
            raise ValueError(f'reporting_year must be between 2000 and {datetime.utcnow().year + 5}')
        # 1. Conditional Validation: Document References
        if self.social.whs_policy_in_place and not self.social.whs_document_reference:
            raise ValueError("WHS document reference is required when a WHS policy is in place.")
        if self.governance.esg_policy_in_place and not self.governance.esg_document_reference:
            raise ValueError("ESG document reference is required when an ESG policy is in place.")

        # 2. YoY Variance Logic
        if self.prefilled_data and not self.submission_notes:
            current_numerics = {
                'scope_1_emissions': self.environmental.scope_1_emissions,
                'scope_2_location_based': self.environmental.scope_2_location_based,
                'scope_3_emissions': self.environmental.scope_3_emissions,
                'trifr': self.social.trifr,
                'female_representation_percent': self.social.female_representation_percent,
                'female_board_members_percent': self.governance.female_board_members_percent,
            }
            
            for field, current_val in current_numerics.items():
                prev_val = self.prefilled_data.get(field)
                if prev_val is not None and prev_val > 0:
                    variance = abs(current_val - prev_val) / prev_val
                    if variance > 0.30:
                        raise ValueError(
                            f"Year-on-year variance for '{field}' exceeds 30%. "
                            f"You must provide 'submission_notes' to explain this deviation."
                        )
        return self

# ==========================================
# Task 3: FastAPI Endpoint
# ==========================================
@router.post("/submissions")
def submit_esg_data(
    payload: ESGSubmissionCreate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == payload.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail='Company not found')
    role = str(user.role.value if hasattr(user.role, 'value') else user.role).lower()
    if role != 'manager' and company.user_id != user.id:
        raise HTTPException(status_code=403, detail='Company access denied')
    cycle = db.query(CollectionCycle).filter(CollectionCycle.cycle_year == payload.reporting_year).first()
    if not cycle:
        raise HTTPException(status_code=422, detail='No reporting cycle exists for reporting_year')
    if db.query(Submission).filter(Submission.company_id == company.id, Submission.cycle_id == cycle.id).first():
        raise HTTPException(status_code=409, detail='A submission already exists for this company and reporting cycle')
    # Convert Pydantic payload to JSON string. (prefilled_data is ignored via exclude=True)
    submission_record = Submission(
        company_id=payload.company_id,
        cycle_id=cycle.id,
        esg_data=payload.model_dump_json(),
        status='submitted'
    )
    
    db.add(submission_record)
    db.commit()
    db.refresh(submission_record)
    
    return {
        "message": "ESG Submission successfully processed and saved.",
        "submission_id": submission_record.id,
        "total_ghg_emissions": payload.environmental.total_ghg_emissions
    }
