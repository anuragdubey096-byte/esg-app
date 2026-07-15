# Recovery and Rollback Runbook

## Recovery objectives

Provisional targets until the database provider capability is confirmed:

- Core application recovery time objective (RTO): 60 minutes
- Database recovery point objective (RPO): 24 hours or the provider's better guaranteed point-in-time capability
- Deployment rollback decision: within 15 minutes of a confirmed release-caused SEV-1

Do not present these as contractual guarantees until operations verifies backup retention and point-in-time recovery with the production Postgres provider.

## Vercel application rollback

1. Identify the last known-good production deployment and its full Git commit SHA.
2. Confirm whether the incident includes a schema change. Application rollback alone may be unsafe after an incompatible migration.
3. Promote/redeploy the known-good commit without copying or changing production secrets.
4. Verify `/api/health/ready`, version, database and Blob checks, login, dashboards, and export retrieval.
5. Review Runtime Logs for one hour and record the incident timeline.

The existing Vercel project retains immutable deployments, so rollback can use a known-good deployment or commit. A live rollback was intentionally not performed during baseline work because production was serving traffic.

## Database restore

1. Declare an incident and prevent writes when continued writes would worsen recovery.
2. Record the desired recovery timestamp and current deployment/migration revision.
3. Create a new isolated restore target; never overwrite production for the first restore attempt.
4. Restore the provider backup or point-in-time snapshot.
5. Validate schema revision, row counts for critical tables, authentication, latest cycles/submissions, audit events, and export references.
6. Run read-only smoke tests and reconcile the RPO gap.
7. Obtain technical lead approval before directing production traffic to the restored database.
8. Preserve the failed database for investigation according to retention policy.

The production Postgres provider, retention window, and point-in-time recovery entitlement are not exposed by this repository and must be confirmed in the provider dashboard. Do not claim a production restore drill until an isolated Postgres restore has been completed and timed.

## Baseline drill record

On 2026-07-15, `scripts/sqlite_restore_drill.py` completed in 49.29 ms and verified backup creation, loss of the live test file, restoration, SQLite integrity, and a data marker. This validates the drill procedure only; it does not validate production Postgres recovery.

## Migration recovery

Follow `docs/MIGRATIONS.md`. Prefer forward repair for additive changes. Use downgrade only when reviewed as data-preserving; otherwise restore the database and roll back the application together.
