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
