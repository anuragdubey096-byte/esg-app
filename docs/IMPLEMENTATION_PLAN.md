# GreenLedger Post-v1.1.0 Implementation Plan

**Baseline:** v1.1.0

**Planning horizon:** five incremental releases

**Primary objective:** move GreenLedger from a feature-complete production application to a reliable, explainable, governed, and enterprise-ready ESG platform

## 1. Executive recommendation

Deliver the roadmap in this order:

1. **v1.1.1 - Delivery safety:** CI, dependency review, migrations, observability, and release gates.
2. **v1.2.0 - Dashboard context and actionability:** global reporting scope, freshness, drill-downs, and a manager action queue.
3. **v1.3.0 - Governed reporting workflow:** attestation, dual approval, amendments, evidence history, reminders, and audit export.
4. **v1.4.0 - Enterprise access and security:** granular permissions, invitations, SSO/MFA integration, sessions, rate limits, and retention.
5. **v1.5.0 - Advanced portfolio intelligence:** hierarchy, comparison, benchmarks, target-versus-actual, saved views, and narrative traceability.

Do not begin v1.3.0 schema work until automated CI and repeatable database migrations are established. Do not enable enterprise authentication changes directly in production without a tested fallback administrator path.

## 2. Planning assumptions

- Delivery uses small, reviewable changes merged to `main` after automated checks.
- Estimates are expressed as two-week sprints, not fixed calendar dates.
- The reference team is two engineers, one product/ESG owner, and shared QA/operations support.
- A single engineer can use the same sequence, but elapsed time will increase.
- Existing manager, investor, and company workflows remain backward compatible unless a release explicitly documents a migration.
- Postgres is the durable production system of record and private Vercel Blob remains the production export store.
- External SSO, email, benchmark, and monitoring vendors require separate commercial and security decisions.

## 3. Success measures

| Outcome | Measure |
| --- | --- |
| Release safety | Every pull request runs backend tests, frontend tests, build, compilation, and configuration checks. |
| Reporting clarity | Every analytical page visibly identifies reporting year, approval scope, and data freshness. |
| Faster operations | Managers can reach the underlying company/metric from a KPI in two interactions or fewer. |
| Workflow control | Approved data cannot be silently modified; every amendment is attributable and reviewable. |
| Access governance | Permissions are explicit, testable, and reviewable without depending on hidden navigation. |
| Recovery readiness | Database restore and application rollback procedures are tested and timed. |
| Explainable outputs | Material narrative statements can be traced to source metrics and reporting periods. |

## 4. Delivery principles

- **One reporting context:** pages must not silently mix active, latest, approved, and historical data.
- **Backend authorization first:** frontend visibility is a usability layer, never the security boundary.
- **Immutable approval history:** corrections create revisions or amendments rather than rewriting approved records.
- **No untracked calculations:** material KPIs document source fields, units, formulas, and framework references.
- **Progressive rollout:** risky behavior is introduced behind configuration or feature controls and verified before broad enablement.
- **Evidence-based release:** a release is complete only when code, tests, documentation, monitoring, and rollback instructions agree.

## 5. Release roadmap

### Release v1.1.1 - Delivery safety and operational baseline

**Target:** 1-2 sprints

**Purpose:** make future changes repeatable and prevent regressions before expanding the data model.

#### GL-100: GitHub Actions CI

**Status:** Complete - hosted CI is green and `main` requires all three CI jobs with strict status checks.

Implement workflows for pull requests and pushes to `main`:

- Install Python dependencies with a pinned supported Python version.
- Run `python server/self_test.py` against isolated SQLite test state.
- Compile `server/` and `api/` Python files.
- Install frontend dependencies with `npm ci`.
- Run `npm test` and `npm run build`.
- Validate `vercel.json` and check `git diff --check` where applicable.
- Upload useful logs/artifacts on failure.
- Add branch protection after the workflow is stable.

**Acceptance criteria**

- A deliberately failing backend test blocks CI.
- A deliberately failing frontend test blocks CI.
- A build failure blocks CI.
- The normal pipeline passes from a clean clone without local-only files or secrets.
- CI runtime and failure ownership are documented.

#### GL-110: Dependency and security baseline

**Status:** Implemented locally - dependency audits are clean; automated checks await hosted CI verification.

- Classify current npm findings by production versus development exposure.
- Run `npm audit --omit=dev` as the production dependency gate.
- Review Python packages for known vulnerabilities using an agreed scanner.
- Patch safe updates separately from breaking upgrades.
- Enable automated dependency pull requests with grouping and rate limits.
- Record accepted risks with owner and review date rather than suppressing them silently.

**Acceptance criteria**

- No unreviewed critical production dependency finding remains.
- Development-only findings are documented and scheduled.
- Lockfiles remain reproducible and CI uses them.

#### GL-120: Database migration discipline

**Status:** Implemented locally - clean upgrade, additive migration, drift check, and downgrade pass; production schema comparison/stamp remains a controlled release task.

- Introduce Alembic or an equivalent reviewed migration mechanism.
- Baseline the current production schema without destructive recreation.
- Add upgrade and downgrade/recovery guidance.
- Stop relying on implicit `create_all` behavior for future production schema evolution.
- Test migrations against a copy of representative data.

**Acceptance criteria**

- A clean database can migrate to the current schema.
- A current database reports no unexpected migration drift.
- A sample additive migration is applied in CI.
- Production migration ownership and rollback decision points are documented.

#### GL-130: Observability and recovery baseline

**Status:** In progress - release-aware logs, truthful readiness checks, alert policy, incident response, and a local restore drill are implemented. Production alert delivery and an isolated Postgres restore drill require provider/owner configuration.

- Add structured release/version fields to runtime logs.
- Monitor health, error rate, latency, database connectivity, and export failures.
- Configure alerts with severity and an owner.
- Document Postgres backup retention and point-in-time recovery capabilities.
- Perform and time one database restore drill.
- Verify Vercel deployment rollback without changing production secrets.

**Exit gate for v1.1.1**

- CI is required and green.
- Dependency risk review is signed off.
- Migration baseline is proven.
- Health/error alerts and recovery runbook are available.

---

### Release v1.2.0 - Dashboard context and actionability

**Target:** 2 sprints

**Purpose:** make every number understandable and every exception actionable.

#### GL-200: Global reporting scope

Create a single reporting-scope contract used by the frontend and API.

Frontend:

- Add a `ReportingScopeProvider` at the authenticated dashboard layout.
- Store `cycleYear`, `scopeMode`, and optional company/portfolio filters.
- Represent scope in URL query parameters so views are shareable and browser navigation works.
- Persist the most recent valid selection per role, while defaulting safely to the latest approved or active context defined for that page.
- Show the selected year in the top navigation and all page headers.

Backend:

- Standardize optional `cycle_year`/cycle identifiers on analytical endpoints.
- Return resolved scope metadata with every scoped response.
- Reject unavailable years clearly instead of silently falling back to another year.

Suggested response metadata:

```json
{
  "scope": {
    "requested_cycle_year": 2025,
    "resolved_cycle_year": 2025,
    "mode": "approved",
    "latest_data_at": "2026-07-15T12:00:00Z",
    "submission_count": 18
  }
}

```


**Acceptance criteria**

- Overview, analytics, submissions, reports, and anomalies agree on the selected year.
- Changing the year updates all scoped widgets without a full-page reload.
- Refreshing or sharing a scoped URL preserves the selection.
- A missing year displays an explicit empty state and never substitutes another year silently.
- Manager, investor, and company scope behavior is covered by tests.

#### GL-210: Data freshness and provenance

- Display last data refresh, resolved reporting year, approval state, coverage, and confidence.
- Distinguish current active-cycle data from latest approved data.
- Link company analytics to the selected submission ID.
- Add metric definitions and calculation notes for material KPIs.

**Acceptance criteria**

- Every executive KPI identifies its period and freshness context.
- Users can identify the source submission for company-level KPIs.
- Zero, unavailable, and not-yet-reported states are visually distinct.

#### GL-220: KPI drill-down

- Define stable drill-down routes and query contracts.
- Make reporting coverage, ESG score, emissions, validation flags, data quality, and target status interactive.
- Preserve the global reporting scope when navigating.
- Provide table-level filtering, sorting, pagination, and CSV export where appropriate.

**Acceptance criteria**

- Each priority KPI opens the records that reconcile to its displayed total.
- Drill-down totals equal summary totals for the same scope.
- Keyboard users can activate and exit drill-down experiences.

#### GL-230: Manager action queue

Add an API and dashboard component that combines:

- Submissions awaiting review
- Resubmission requests
- Unresolved validation flags
- Approaching and overdue deadlines
- Expiring correction windows
- Overdue targets and action plans

Define a transparent priority model using severity, due date, workflow state, and age. Do not use an opaque AI score for operational ordering.

**Acceptance criteria**

- Every queue item has owner, reason, due date/age, priority explanation, and destination.
- Completing the underlying action removes or updates the item.
- Duplicate events are collapsed by a stable deduplication key.

**Exit gate for v1.2.0**

- Cross-page reporting scope tests pass.
- KPI-to-detail reconciliation tests pass.
- Role-specific UAT confirms that displayed periods and data states are understandable.
- Performance remains within agreed dashboard latency targets.

---

### Release v1.3.0 - Governed reporting workflow

**Target:** 2-3 sprints

**Purpose:** strengthen approval integrity, evidence history, accountability, and exception management.

#### GL-300: Company attestation

- Add authorized signatory name, title, timestamp, statement version, and submission revision.
- Require explicit confirmation before final submission.
- Preserve attestations with the submitted revision.
- Display attestation in manager review and eligible reports.

#### GL-310: Dual review and approval

- Separate reviewer and approver permissions.
- Prevent the same account from completing both steps when segregation is required.
- Add configurable thresholds for when dual approval is mandatory.
- Preserve review comments and decisions as immutable events.

#### GL-320: Approved-data amendments

- Lock approved submission revisions.
- Add an amendment request with reason, requested fields, requester, and evidence.
- Create a new revision rather than overwriting the approved record.
- Compare original and amended values side by side.
- Require approval before the amended revision becomes current.

#### GL-330: Evidence version history

- Version replacements rather than deleting history.
- Store uploader, timestamp, file metadata, checksum, metric links, and status.
- Add malware/content validation appropriate to the selected upload architecture.
- Define retention and legal-hold behavior.

#### GL-340: Reminders, escalation, and audit export

- Introduce scheduled reminder rules with deduplication.
- Add escalation levels and accountable owners.
- Make delivery status visible.
- Add filtered audit-log export for administrators.
- Include actor, timestamp, event, target, reporting scope, and before/after summary.

**Acceptance criteria for v1.3.0**

- Approved data cannot be modified through any UI or API path without an amendment.
- Required dual approval cannot be completed by one person.
- Evidence replacement preserves prior versions and attribution.
- Reminder retries do not create duplicate notifications.
- Audit exports reconcile to tested workflow events.
- Migration, permission, and rollback tests pass before production rollout.

---

### Release v1.4.0 - Enterprise access and security

**Target:** 2-3 sprints plus vendor lead time

**Purpose:** support controlled organizational access and stronger production security.

#### GL-400: Permission model

Move from only broad roles to permissions such as:

- `cycle.manage`
- `submission.edit`
- `submission.review`
- `submission.approve`
- `report.generate`
- `audit.export`
- `user.manage`

Map existing roles to default permission sets for backward compatibility. Add API tests for every protected action.

#### GL-410: User lifecycle

- Invitation, acceptance, expiration, resend, and cancellation
- Organization/company assignment
- Deactivation and reactivation
- Access review report
- Last login and active-session visibility
- Emergency administrator recovery procedure

#### GL-420: SSO, MFA, and sessions

- Select an identity provider/integration after security and commercial review.
- Support SSO discovery and organization mapping.
- Require MFA according to policy.
- Add session/device listing and revocation.
- Preserve a controlled fallback administrator path during rollout.

#### GL-430: Platform protection

- Rate-limit authentication, password reset, generation, export, and upload endpoints.
- Add security headers and content security policy compatible with the SPA.
- Validate upload size/type and safe download behavior.
- Add secret-rotation instructions and verification.
- Define retention, deletion, and audit-preservation policies.

**Acceptance criteria for v1.4.0**

- Permission tests deny every unauthorized action at the API layer.
- Deactivated users and revoked sessions lose access promptly.
- SSO failure does not lock out the designated emergency administrator.
- Rate limits protect abuse-sensitive endpoints without blocking normal workflows.
- Access review and retention procedures are documented and tested.

---

### Release v1.5.0 - Advanced portfolio intelligence

**Target:** 2-3 sprints

**Purpose:** improve portfolio comparison, planning, and explainability after data governance is mature.

#### GL-500: Portfolio hierarchy

- Model funds, portfolios, investments, companies/subsidiaries, ownership percentages, and effective dates.
- Aggregate metrics with explicit consolidation rules.
- Prevent double counting and document boundary assumptions.

#### GL-510: Company comparison and benchmarks

- Compare selected companies, sectors, asset classes, and years.
- Support internal quartiles and approved external benchmark datasets.
- Record benchmark source, publication date, scope, unit, and license.
- Never present unmatched benchmark definitions as directly comparable.

#### GL-520: Target-versus-actual

- Link targets to defined metrics, baselines, units, and dates.
- Calculate on-track, at-risk, overdue, and achieved states with documented rules.
- Drill from portfolio target status to company actions and evidence.

#### GL-530: Saved views and custom dashboards

- Save named filters and dashboard configurations per user or team.
- Validate widgets against role permissions.
- Support safe defaults and reset behavior.
- Avoid arbitrary query execution from saved configuration.

#### GL-540: Narrative traceability

- Store source metric references and reporting scope with generated narratives.
- Link material claims to underlying values or calculated indicators.
- Flag stale narratives when source submissions change.
- Require regeneration or review before using stale narratives in approved outputs.

**Acceptance criteria for v1.5.0**

- Portfolio aggregation reconciles to company records under documented rules.
- Benchmark comparisons show definition and source metadata.
- Target status is reproducible from stored inputs.
- Saved views cannot reveal unauthorized data.
- Narrative source links resolve to the same reporting scope used at generation time.

## 6. Continuous quality workstream

These items run across all releases rather than waiting for a final hardening phase.

### Automated testing pyramid

- Unit tests for calculations, permissions, scope resolution, and status transitions
- API integration tests for role access and persistence
- Browser tests for login, submission, review, analytics, and report export
- Websocket/collaboration tests for claim, heartbeat, conflict, release, and reconnect
- Narrative lifecycle tests for generate, edit, approve, history, staleness, and authorization
- Migration tests using representative prior-version schemas

### Accessibility and responsive behavior

- Keyboard navigation and visible focus
- Semantic labels and screen-reader status announcements
- Color contrast and non-color status indicators
- Responsive tables, charts, dialogs, and filters
- Automated checks plus manual keyboard/screen-reader review on critical flows

### Performance

- Establish p50/p95 API and dashboard targets.
- Measure query counts and payload size for analytical endpoints.
- Add indexes only from measured query plans.
- Paginate large tables and audit logs.
- Avoid loading every historical record into initial dashboard responses.

### Documentation

For each release update:

- `VERSION`, server version, package versions, and `CHANGELOG.md`
- Product/user guide for workflow or role changes
- Technical guide for architecture, configuration, migrations, and operations
- API schema/examples when contracts change
- UAT script, rollback steps, and release notes

## 7. Suggested sprint sequence

| Sprint | Primary outcome |
| --- | --- |
| 1 | CI pipeline, dependency classification, observability plan |
| 2 | Migration baseline, recovery drill, branch protection |
| 3 | Reporting-scope backend contract and frontend provider |
| 4 | Freshness UI, KPI drill-downs, manager action queue, v1.2.0 UAT |
| 5 | Attestation and immutable submission revisions |
| 6 | Dual approval and amendment workflow |
| 7 | Evidence history, reminders, audit export, v1.3.0 UAT |
| 8 | Permission model and user lifecycle |
| 9 | SSO/MFA integration and session controls |
| 10 | Rate limits, retention, access review, v1.4.0 UAT |
| 11 | Portfolio hierarchy and comparison |
| 12 | Benchmarks, target-versus-actual, saved views, narrative traceability, v1.5.0 UAT |

The schedule is a sequencing aid, not a commitment. Split releases when acceptance criteria cannot be safely completed within the target window.

## 8. Ownership model

| Responsibility | Accountable owner |
| --- | --- |
| Product scope and acceptance | Product/ESG owner |
| Architecture, API, data model, migrations | Technical lead |
| Role policy and approval design | Product/ESG owner with security reviewer |
| Test automation and UAT coordination | Engineering/QA |
| Vercel, database, Blob, monitoring, recovery | Operations/technical lead |
| SSO, MFA, retention, incident policy | Security/operations owner |
| Benchmark definitions and calculation methodology | ESG methodology owner |

Every epic needs one named accountable person before implementation begins.

## 9. Definition of done

A roadmap item is complete only when:

- Acceptance criteria are met and demonstrated.
- Backend authorization is tested for allowed and denied roles/permissions.
- Unit/integration/browser tests appropriate to the risk pass in CI.
- Database changes have forward migration and recovery instructions.
- Empty, loading, error, stale, and unauthorized states are handled.
- Accessibility and responsive behavior are reviewed.
- Logs and metrics make production failures diagnosable.
- Product and technical documentation are updated.
- Deployment and rollback steps are verified.
- No unrelated or generated files are included in the release.

## 10. Release and rollout process

1. Write the epic brief, data/API contract, and acceptance criteria.
2. Review permission, migration, privacy, and rollback impact.
3. Implement in small changes with tests.
4. Deploy a preview and run role-based UAT.
5. Back up or verify recovery capability before schema-affecting production releases.
6. Merge only with required CI checks green.
7. Match the Vercel deployment to the intended full commit SHA.
8. Verify homepage, versioned health, role smoke tests, storage, and runtime errors.
9. Monitor the defined observation window.
10. Publish release notes and tag the verified commit.

## 11. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Cross-page filters show inconsistent years | One scope contract, URL state, response metadata, and reconciliation tests |
| Workflow schema changes damage existing records | Migration baseline, representative backups, additive rollout, restore drill |
| Dual approval blocks small teams | Configurable policy with documented emergency procedure and audit event |
| SSO rollout locks out administrators | Staged organization rollout and controlled fallback administrator |
| Benchmark data is not comparable | Definition matching, provenance metadata, methodology owner approval |
| Custom views expose unauthorized data | Server-side permission checks and allowlisted widget/query definitions |
| Notifications create noise | Deduplication keys, preferences, escalation rules, and delivery observability |
| AI narrative overstates the source data | Source links, stale detection, review status, and deterministic fallback behavior |

## 12. Immediate next actions

1. Commit and push the v1.1.1 baseline, then require the new dependency-security check after hosted CI passes.
2. Compare an isolated production Postgres copy with the Alembic baseline before stamping revision `20260715_01` and applying the additive migration.
3. Select and configure alert delivery, notification owners, and synthetic readiness monitoring.
4. Confirm the production Postgres backup retention/PITR entitlement and complete a timed isolated restore drill.
5. Release v1.1.1 only after migration, alert-delivery, and recovery gates are evidenced.
6. Begin the GL-200 reporting-scope contract after the v1.1.1 release gate is complete.
