# Incident Response

## Severity

- **SEV-1:** application unavailable, database unavailable, authentication broadly broken, data loss/corruption risk, or core workflow repeatedly returning 500.
- **SEV-2:** major workflow degraded, exports unavailable, sustained high latency, or a limited authorization/security concern.
- **SEV-3:** non-critical defect, isolated failed job, or operational warning with a workaround.

## Response flow

1. Acknowledge, assign an incident owner, and record UTC start time.
2. Capture affected routes, roles, request IDs, deployment ID, commit SHA, version, and first/last observed times.
3. Check `/api/health/ready`, Vercel deployment state, Runtime Logs, database connectivity, and Blob health.
4. Contain the incident. Pause deployment, disable the affected workflow if available, or roll back when the release is causal.
5. Recover using the recovery runbook and validate role-based smoke tests.
6. Communicate scope, current impact, workaround, and next update time without exposing secrets or personal data.
7. Close only after monitoring confirms stability and any data reconciliation is complete.
8. Complete a blameless review for SEV-1/SEV-2, with owner and due date for every follow-up.

## Evidence to preserve

- Structured runtime logs and request IDs
- Deployment and Git commit identifiers
- Migration revision and database recovery timestamp
- Audit events relevant to affected records
- Exact commands/actions used for rollback or restore
- User-visible impact and reconciliation results
