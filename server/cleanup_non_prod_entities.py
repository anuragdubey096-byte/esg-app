from __future__ import annotations

import argparse
from typing import Dict, List

from sqlalchemy import func, or_

from database import SessionLocal
from models import (
    ActionPlan,
    ActivityEvent,
    Company,
    NarrativeSummary,
    ReminderLog,
    ReviewAction,
    Submission,
    SubmissionCollaborationSession,
    SubmissionDataField,
    SubmissionUnlock,
    SupportingDocument,
    User,
    ValidationError,
    ValidationFlag,
)
from non_prod_guard import build_non_prod_company_clause


def _count_by_company_owner(db, company_ids: List[int]) -> tuple[Dict[int, int], Dict[int, int]]:
    if not company_ids:
        return {}, {}
    candidate_counts = {
        user_id: count
        for user_id, count in (
            db.query(Company.user_id, func.count(Company.id))
            .filter(Company.id.in_(company_ids))
            .group_by(Company.user_id)
            .all()
        )
    }
    owner_ids = list(candidate_counts.keys())
    total_counts = {
        user_id: count
        for user_id, count in (
            db.query(Company.user_id, func.count(Company.id))
            .filter(Company.user_id.in_(owner_ids))
            .group_by(Company.user_id)
            .all()
        )
    }
    return candidate_counts, total_counts


def run_cleanup(*, apply_changes: bool) -> int:
    db = SessionLocal()
    try:
        qa_companies = (
            db.query(Company.id, Company.name, Company.code, User.id, User.email)
            .join(User, Company.user_id == User.id)
            .filter(build_non_prod_company_clause())
            .order_by(Company.id.asc())
            .all()
        )
        if not qa_companies:
            print('No non-production QA/test entities found.')
            return 0

        company_ids = [int(row[0]) for row in qa_companies]
        owner_ids = [int(row[3]) for row in qa_companies]
        owner_emails = [str(row[4] or '').strip().lower() for row in qa_companies if str(row[4] or '').strip()]
        submission_ids = [row[0] for row in db.query(Submission.id).filter(Submission.company_id.in_(company_ids)).all()]
        candidate_counts, total_counts = _count_by_company_owner(db, company_ids)
        removable_owner_ids = [
            owner_id
            for owner_id in set(owner_ids)
            if candidate_counts.get(owner_id, 0) and candidate_counts.get(owner_id, 0) == total_counts.get(owner_id, 0)
        ]

        print('Matched non-production companies:')
        for company_id, company_name, company_code, owner_id, owner_email in qa_companies:
            print(f'- company_id={company_id} name="{company_name}" code="{company_code}" owner={owner_email} (user_id={owner_id})')
        print(f'Found {len(company_ids)} companies, {len(submission_ids)} submissions, {len(removable_owner_ids)} removable owner users.')

        deletions = []

        def collect(name: str, query):
            count = query.count()
            deletions.append((name, count, query))

        if submission_ids:
            collect(
                'validation_errors',
                db.query(ValidationError).filter(
                    or_(ValidationError.company_id.in_(company_ids), ValidationError.submission_id.in_(submission_ids))
                ),
            )
            collect(
                'supporting_documents',
                db.query(SupportingDocument).filter(
                    or_(SupportingDocument.company_id.in_(company_ids), SupportingDocument.submission_id.in_(submission_ids))
                ),
            )
            collect(
                'submission_data_fields',
                db.query(SubmissionDataField).filter(
                    or_(SubmissionDataField.company_id.in_(company_ids), SubmissionDataField.submission_id.in_(submission_ids))
                ),
            )
            collect(
                'submission_collaboration_sessions',
                db.query(SubmissionCollaborationSession).filter(
                    or_(
                        SubmissionCollaborationSession.company_id.in_(company_ids),
                        SubmissionCollaborationSession.submission_id.in_(submission_ids),
                    )
                ),
            )
            collect(
                'submission_unlocks',
                db.query(SubmissionUnlock).filter(
                    or_(SubmissionUnlock.company_id.in_(company_ids), SubmissionUnlock.submission_id.in_(submission_ids))
                ),
            )
            collect(
                'activity_events_by_submission',
                db.query(ActivityEvent).filter(ActivityEvent.submission_id.in_(submission_ids)),
            )
        else:
            collect('validation_errors', db.query(ValidationError).filter(ValidationError.company_id.in_(company_ids)))
            collect('supporting_documents', db.query(SupportingDocument).filter(SupportingDocument.company_id.in_(company_ids)))
            collect('submission_data_fields', db.query(SubmissionDataField).filter(SubmissionDataField.company_id.in_(company_ids)))
            collect(
                'submission_collaboration_sessions',
                db.query(SubmissionCollaborationSession).filter(SubmissionCollaborationSession.company_id.in_(company_ids)),
            )
            collect('submission_unlocks', db.query(SubmissionUnlock).filter(SubmissionUnlock.company_id.in_(company_ids)))

        collect('reminder_logs', db.query(ReminderLog).filter(ReminderLog.company_id.in_(company_ids)))
        collect('review_actions', db.query(ReviewAction).filter(ReviewAction.company_id.in_(company_ids)))
        collect('validation_flags', db.query(ValidationFlag).filter(ValidationFlag.company_id.in_(company_ids)))
        collect('action_plans', db.query(ActionPlan).filter(ActionPlan.company_id.in_(company_ids)))
        collect('narrative_summaries', db.query(NarrativeSummary).filter(NarrativeSummary.company_id.in_(company_ids)))
        collect('activity_events_by_company', db.query(ActivityEvent).filter(ActivityEvent.company_id.in_(company_ids)))
        if owner_emails:
            collect('activity_events_by_actor', db.query(ActivityEvent).filter(ActivityEvent.actor_email.in_(owner_emails)))
        collect('submissions', db.query(Submission).filter(Submission.company_id.in_(company_ids)))
        collect('companies', db.query(Company).filter(Company.id.in_(company_ids)))
        if removable_owner_ids:
            collect('users', db.query(User).filter(User.id.in_(removable_owner_ids)))

        print('Deletion plan:')
        for name, count, _ in deletions:
            print(f'- {name}: {count}')

        if not apply_changes:
            db.rollback()
            print('Dry run only. Re-run with --apply to commit deletions.')
            return 0

        for _, count, query in deletions:
            if count:
                query.delete(synchronize_session=False)
        db.commit()
        print('Cleanup committed successfully.')
        return 0
    except Exception as exc:  # pragma: no cover - defensive CLI guard
        db.rollback()
        print(f'Cleanup failed: {exc}')
        return 1
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description='Remove non-production QA/test entities from the ESG database.')
    parser.add_argument('--apply', action='store_true', help='Apply deletions. Without this flag the script runs in dry-run mode.')
    args = parser.parse_args()
    return run_cleanup(apply_changes=bool(args.apply))


if __name__ == '__main__':
    raise SystemExit(main())
