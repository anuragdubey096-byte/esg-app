import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
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
    action_plans = relationship('ActionPlan', back_populates='company')
    review_actions = relationship('ReviewAction', back_populates='company')
    validation_flags = relationship('ValidationFlag', back_populates='company')
    submission_unlocks = relationship('SubmissionUnlock', back_populates='company')
    reminder_logs = relationship('ReminderLog', back_populates='company')


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
    reporting_year = Column(Integer, nullable=False)
    review_status = Column(String, nullable=False)
    reviewer_role = Column(String, nullable=False)
    review_comment = Column(String, nullable=True)

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


class UserPermission(Base):
    __tablename__ = 'user_permissions'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True, index=True)
    can_manage_security = Column(Boolean, nullable=False, default=False)
    can_view_portfolio_audit = Column(Boolean, nullable=False, default=False)
    can_clone_cycles = Column(Boolean, nullable=False, default=False)
    read_only_audit_scope = Column(Text, nullable=False, default='[]')
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class FeatureFlag(Base):
    __tablename__ = 'feature_flags'

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AuditEvent(Base):
    __tablename__ = 'audit_events'

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
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


class SubmissionDeclaration(Base):
    __tablename__ = 'submission_declarations'

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey('submissions.id'), nullable=False, unique=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, index=True)
    signatory_name = Column(String, nullable=False)
    signatory_role = Column(String, nullable=False, default='company_signatory')
    statement_version = Column(String, nullable=False, default='v1')
    declared_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    metadata_json = Column(Text, nullable=False, default='{}')


class ContextHelpContent(Base):
    __tablename__ = 'context_help_content'

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey('collection_cycles.id'), nullable=False, index=True)
    field_key = Column(String, nullable=False, index=True)
    title = Column(String, nullable=True)
    body = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    updated_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CycleCloneLog(Base):
    __tablename__ = 'cycle_clone_logs'

    id = Column(Integer, primary_key=True, index=True)
    source_cycle_id = Column(Integer, ForeignKey('collection_cycles.id'), nullable=False, index=True)
    target_cycle_id = Column(Integer, ForeignKey('collection_cycles.id'), nullable=False, index=True)
    cloned_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    clone_options_json = Column(Text, nullable=False, default='{}')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class OnboardingState(Base):
    __tablename__ = 'onboarding_states'

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False, unique=True, index=True)
    steps_json = Column(Text, nullable=False, default='{}')
    progress_percent = Column(Integer, nullable=False, default=0)
    completed = Column(Boolean, nullable=False, default=False, index=True)
    updated_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class UserSecuritySetting(Base):
    __tablename__ = 'user_security_settings'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True, index=True)
    mfa_enabled = Column(Boolean, nullable=False, default=False)
    mfa_secret = Column(String, nullable=True)
    mfa_backup_codes_json = Column(Text, nullable=False, default='[]')
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class SessionPolicy(Base):
    __tablename__ = 'session_policies'

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, nullable=False, unique=True, index=True)
    timeout_minutes = Column(Integer, nullable=False, default=480)
    warn_before_minutes = Column(Integer, nullable=False, default=5)
    max_failed_logins = Column(Integer, nullable=False, default=5)
    lockout_minutes = Column(Integer, nullable=False, default=30)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class IPAllowlist(Base):
    __tablename__ = 'ip_allowlists'

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, nullable=False, unique=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    note = Column(String, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class UserSession(Base):
    __tablename__ = 'user_sessions'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    session_token = Column(String, nullable=False, unique=True, index=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AccountLockout(Base):
    __tablename__ = 'account_lockouts'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True, index=True)
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AuthEvent(Base):
    __tablename__ = 'auth_events'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    email = Column(String, nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    ip_address = Column(String, nullable=True)
    details_json = Column(Text, nullable=False, default='{}')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
