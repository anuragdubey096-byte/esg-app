import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class UserRole(str, enum.Enum):
    COMPANY = 'company'
    MANAGER = 'manager'
    INVESTOR = 'investor'

# users — stores email, password, and role for every account.
# Role is one of: company, manager, investor.
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(Enum(UserRole, native_enum=False), nullable=False)

    companies = relationship('Company', back_populates='owner')
    cycles = relationship('CollectionCycle', back_populates='created_by_user')
    submission_unlocks = relationship('SubmissionUnlock', back_populates='unlocked_by_user')
    reminder_logs = relationship('ReminderLog', back_populates='sent_by_user')


# companies — stores each company and connects it to a user account.
# The user_id column tells us which user owns or submits for this company.
class Company(Base):
    __tablename__ = 'companies'

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, nullable=False)
    sector = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    asset_class = Column(String, nullable=True)
    geography = Column(String, nullable=True)
    client_visible = Column(String, nullable=True)
    current_status = Column(String, nullable=True)

    owner = relationship('User', back_populates='companies')
    submissions = relationship('Submission', back_populates='company')
    submission_drafts = relationship('SubmissionDraft', back_populates='company')
    evidence_files = relationship('SubmissionEvidence', back_populates='company')
    action_plans = relationship('ActionPlan', back_populates='company')
    esg_targets = relationship('ESGTarget', back_populates='company')
    review_actions = relationship('ReviewAction', back_populates='company')
    validation_flags = relationship('ValidationFlag', back_populates='company')
    submission_unlocks = relationship('SubmissionUnlock', back_populates='company')
    reminder_logs = relationship('ReminderLog', back_populates='company')
    holdings = relationship('Holding', back_populates='company')


class Portfolio(Base):
    __tablename__ = 'portfolios'

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    base_currency = Column(String, nullable=False, default='USD')
    description = Column(Text, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    funds = relationship('Fund', back_populates='portfolio', cascade='all, delete-orphan')


class Fund(Base):
    __tablename__ = 'funds'
    __table_args__ = (UniqueConstraint('portfolio_id', 'code', name='uq_fund_portfolio_code'),)

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey('portfolios.id'), nullable=False, index=True)
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    vintage_year = Column(Integer, nullable=True)
    base_currency = Column(String, nullable=False, default='USD')
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    portfolio = relationship('Portfolio', back_populates='funds')
    holdings = relationship('Holding', back_populates='fund', cascade='all, delete-orphan')


class Holding(Base):
    __tablename__ = 'holdings'
    __table_args__ = (
        UniqueConstraint('fund_id', 'external_id', name='uq_holding_fund_external_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    fund_id = Column(Integer, ForeignKey('funds.id'), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    external_id = Column(String, nullable=False)
    ownership_percent = Column(Float, nullable=False)
    invested_amount_base = Column(Float, nullable=False, default=0)
    nav_value_base = Column(Float, nullable=False, default=0)
    currency = Column(String, nullable=False, default='USD')
    effective_from = Column(String, nullable=False)
    effective_to = Column(String, nullable=True)
    status = Column(String, nullable=False, default='active')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    fund = relationship('Fund', back_populates='holdings')
    company = relationship('Company', back_populates='holdings')


# submissions — stores ESG reports for each company with a status.
# Status values are simple strings, such as not started, in progress, submitted, approved.
class Submission(Base):
    __tablename__ = 'submissions'

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    cycle_id = Column(Integer, ForeignKey('collection_cycles.id'), nullable=True, index=True)
    esg_data = Column(String, nullable=False)
    status = Column(String, nullable=False, default='not started')

    company = relationship('Company', back_populates='submissions')
    cycle = relationship('CollectionCycle', back_populates='submissions')
    unlocks = relationship('SubmissionUnlock', back_populates='submission')


class ReviewAction(Base):
    __tablename__ = 'review_actions'

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    submission_id = Column(Integer, ForeignKey('submissions.id'), nullable=True, index=True)
    reporting_year = Column(Integer, nullable=False)
    review_status = Column(String, nullable=False)
    reviewer_role = Column(String, nullable=False)
    review_comment = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    company = relationship('Company', back_populates='review_actions')


class ValidationFlag(Base):
    __tablename__ = 'validation_flags'

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    reporting_year = Column(Integer, nullable=False)
    flag_type = Column(String, nullable=False)
    field_name = Column(String, nullable=False)
    issue_description = Column(String, nullable=False)
    severity = Column(String, nullable=False)

    company = relationship('Company', back_populates='validation_flags')


class CollectionCycle(Base):
    __tablename__ = 'collection_cycles'

    id = Column(Integer, primary_key=True, index=True)
    cycle_year = Column(Integer, nullable=False, unique=True)
    submission_open_date = Column(String, nullable=False)
    submission_deadline = Column(String, nullable=False)
    extension_date = Column(String, nullable=True)
    reminder_schedule = Column(String, nullable=False)
    template_config = Column(String, nullable=False)
    prefill_summary = Column(String, nullable=False)
    status = Column(String, nullable=False, default='active')
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    created_by_user = relationship('User', back_populates='cycles')
    submissions = relationship('Submission', back_populates='cycle')
    submission_drafts = relationship('SubmissionDraft', back_populates='cycle')
    evidence_files = relationship('SubmissionEvidence', back_populates='cycle')
    submission_unlocks = relationship('SubmissionUnlock', back_populates='cycle')
    reminder_logs = relationship('ReminderLog', back_populates='cycle')


class SubmissionUnlock(Base):
    __tablename__ = 'submission_unlocks'

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey('submissions.id'), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey('collection_cycles.id'), nullable=False, index=True)
    unlocked_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    reason = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    active = Column(Boolean, nullable=False, default=True)

    submission = relationship('Submission', back_populates='unlocks')
    company = relationship('Company', back_populates='submission_unlocks')
    cycle = relationship('CollectionCycle', back_populates='submission_unlocks')
    unlocked_by_user = relationship('User', back_populates='submission_unlocks')


class SubmissionDraft(Base):
    __tablename__ = 'submission_drafts'
    __table_args__ = (UniqueConstraint('company_id', 'cycle_id', name='uq_submission_draft_company_cycle'),)

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey('collection_cycles.id'), nullable=False, index=True)
    payload = Column(Text, nullable=False, default='{}')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship('Company', back_populates='submission_drafts')
    cycle = relationship('CollectionCycle', back_populates='submission_drafts')


class SubmissionEvidence(Base):
    __tablename__ = 'submission_evidence'

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey('collection_cycles.id'), nullable=False, index=True)
    submission_id = Column(Integer, ForeignKey('submissions.id'), nullable=True, index=True)
    metric_key = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=False, default=0)
    content = Column(LargeBinary, nullable=False)
    status = Column(String, nullable=False, default='uploaded')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    company = relationship('Company', back_populates='evidence_files')
    cycle = relationship('CollectionCycle', back_populates='evidence_files')
    submission = relationship('Submission')


class AssuranceRecord(Base):
    __tablename__ = 'assurance_records'
    __table_args__ = (UniqueConstraint('submission_id', 'metric_key', name='uq_assurance_submission_metric'),)

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey('submissions.id'), nullable=False, index=True)
    evidence_id = Column(Integer, ForeignKey('submission_evidence.id'), nullable=True, index=True)
    metric_key = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default='pending')
    assurance_level = Column(String, nullable=False, default='limited')
    conclusion = Column(Text, nullable=True)
    reviewer_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReminderLog(Base):
    __tablename__ = 'reminder_logs'

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey('collection_cycles.id'), nullable=False, index=True)
    sent_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    channel = Column(String, nullable=False, default='email')
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    delivery_status = Column(String, nullable=False, default='logged')

    company = relationship('Company', back_populates='reminder_logs')
    cycle = relationship('CollectionCycle', back_populates='reminder_logs')
    sent_by_user = relationship('User', back_populates='reminder_logs')


class ActionPlan(Base):
    __tablename__ = 'action_plans'

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    initiative_name = Column(String, nullable=False)
    target_completion_date = Column(String, nullable=False)
    assigned_owner = Column(String, nullable=False)
    status = Column(String, nullable=False, default='planned')

    company = relationship('Company', back_populates='action_plans')


class ESGTarget(Base):
    __tablename__ = 'esg_targets'

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    pillar = Column(String, nullable=False)
    metric_key = Column(String, nullable=False)
    target_name = Column(String, nullable=False)
    baseline_value = Column(Float, nullable=False, default=0)
    target_value = Column(Float, nullable=False)
    current_value = Column(Float, nullable=False, default=0)
    unit = Column(String, nullable=False, default='')
    target_date = Column(String, nullable=False)
    owner = Column(String, nullable=False)
    status = Column(String, nullable=False, default='on track')
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship('Company', back_populates='esg_targets')


class NarrativeRecord(Base):
    __tablename__ = 'narrative_records'

    id = Column(Integer, primary_key=True, index=True)
    audience = Column(String, nullable=False, default='lp')
    scope = Column(String, nullable=False, default='portfolio')
    tone = Column(String, nullable=False, default='board-ready')
    status = Column(String, nullable=False, default='generated')
    company_id = Column(Integer, nullable=True, index=True)
    company_name = Column(String, nullable=True)

    source_years = Column(Text, nullable=False, default='[]')
    source_company_count = Column(Integer, nullable=False, default=0)
    source_submission_count = Column(Integer, nullable=False, default=0)
    latest_source_years = Column(Text, nullable=False, default='[]')
    latest_source_company_count = Column(Integer, nullable=False, default=0)
    latest_source_submission_count = Column(Integer, nullable=False, default=0)

    provider = Column(String, nullable=False, default='fallback')
    model = Column(String, nullable=True)
    cached = Column(Boolean, nullable=False, default=False)
    fallback_used = Column(Boolean, nullable=False, default=True)

    freshness_status = Column(String, nullable=False, default='current')
    freshness_label = Column(String, nullable=False, default='Current narrative')
    freshness_reason = Column(Text, nullable=False, default='Narrative matches the latest approved data.')

    generated_at = Column(String, nullable=False)
    headline = Column(String, nullable=False, default='ESG narrative')
    summary = Column(Text, nullable=False, default='')
    highlights = Column(Text, nullable=False, default='[]')
    watchouts = Column(Text, nullable=False, default='[]')
    recommendations = Column(Text, nullable=False, default='[]')
    message = Column(Text, nullable=True)
    framework_tags = Column(Text, nullable=False, default='[]')

    generated_payload = Column(Text, nullable=False, default='{}')
    edited_payload = Column(Text, nullable=False, default='{}')
    published_payload = Column(Text, nullable=False, default='{}')

    approved_by_role = Column(String, nullable=True)
    approved_at = Column(String, nullable=True)
    edited_by_role = Column(String, nullable=True)
    edited_at = Column(String, nullable=True)
    updated_at = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AuthSession(Base):
    __tablename__ = 'auth_sessions'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PasswordResetToken(Base):
    __tablename__ = 'password_reset_tokens'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AuditEvent(Base):
    __tablename__ = 'audit_events'

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    actor_email = Column(String, nullable=True, index=True)
    actor_role = Column(String, nullable=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True, index=True)
    submission_id = Column(Integer, ForeignKey('submissions.id'), nullable=True, index=True)
    cycle_id = Column(Integer, ForeignKey('collection_cycles.id'), nullable=True, index=True)
    field_name = Column(String, nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    source = Column(String, nullable=False, default='ui')
    metadata_json = Column(Text, nullable=False, default='{}')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class Notification(Base):
    __tablename__ = 'notifications'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    role = Column(String, nullable=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True, index=True)
    notification_type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    dedupe_key = Column(String, unique=True, nullable=True, index=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class MetricReviewComment(Base):
    __tablename__ = 'metric_review_comments'
    __table_args__ = (UniqueConstraint('submission_id', 'metric_key', name='uq_metric_comment_submission_metric'),)

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey('submissions.id'), nullable=False, index=True)
    metric_key = Column(String, nullable=False, index=True)
    comment = Column(Text, nullable=False)
    reviewer_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MaterialityTopic(Base):
    __tablename__ = 'materiality_topics'

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String, nullable=False, unique=True, index=True)
    pillar = Column(String, nullable=False)
    impact_score = Column(Float, nullable=False)
    financial_score = Column(Float, nullable=False)
    stakeholder_score = Column(Float, nullable=False)
    rationale = Column(Text, nullable=True)
    owner = Column(String, nullable=False)
    status = Column(String, nullable=False, default='assessed')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
