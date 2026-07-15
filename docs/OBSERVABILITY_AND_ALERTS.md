# Observability and Alert Policy

**Owner:** Technical lead / operations  
**Review cadence:** After every deployment and monthly  
**Application:** GreenLedger on Vercel

## Implemented telemetry

Every API response records structured JSON with route, method, status, duration, request ID, application version, environment, deployment ID, commit SHA, and region. Exceptions include a normalized error category and error type. Export persistence failures emit the `export_persist_failed` event.

`/api/health` now executes a database probe, reports its latency, checks Blob configuration, and exposes the release context. `/api/health/ready` returns HTTP 503 when the database or required production storage is unavailable.

Vercel Runtime Logs are the current log store. The 2026-07-15 review found two production validation 500s caused by numeric values stored as strings; the parser and regression coverage were corrected in this workstream.

## Alert definitions

| Severity | Signal | Trigger | Owner action |
| --- | --- | --- | --- |
| SEV-1 | Readiness | Two consecutive `/api/health/ready` failures within 10 minutes | Acknowledge in 15 minutes; assess rollback immediately |
| SEV-1 | Server errors | 5xx rate above 5% for 5 minutes or repeated database connectivity errors | Acknowledge in 15 minutes; stop risky releases |
| SEV-2 | Latency | p95 API duration above 2 seconds for 15 minutes | Investigate slow routes and database latency within one hour |
| SEV-2 | Export storage | Any repeated `export_persist_failed` event or Blob health failure | Verify Blob token/integration without rotating secrets during diagnosis |
| SEV-3 | Dependency security | CI dependency-security job fails | Review before merge; do not release an unreviewed high/critical production finding |

These thresholds are defined but external notification delivery is not yet activated. Activation requires choosing a synthetic/error-monitoring destination and confirming the Vercel plan. Until then, the owner must check Runtime Logs and `/api/health/ready` after deployments and during the daily operating window.

## Deployment checks

1. Confirm the Vercel deployment is `READY` and matches the intended commit SHA.
2. Request `/api/health/ready`; require HTTP 200, expected version, database `ok`, and storage `ok`.
3. Exercise login, one role dashboard, and an export workflow.
4. Review production error logs for the first hour.
5. Roll back if readiness fails, a repeatable 500 affects a core workflow, or migration validation fails.

## Monitoring setup still requiring an owner decision

- Select Vercel dashboard-only monitoring, a synthetic monitor, or an error-monitoring integration.
- Configure notification destinations and on-call contacts.
- If the Vercel plan supports Drains, forward structured production logs to the approved destination and verify payload signatures.
- Test each alert and record delivery time before marking GL-130 complete.
