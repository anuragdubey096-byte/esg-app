# Database Migration Operations

GreenLedger uses Alembic for reviewed schema changes. Production startup no longer creates tables implicitly. Automatic `create_all` remains available only for local development and disposable tests.

## Ownership and release gate

The technical lead owns migration review and execution. Before a production schema release:

1. Confirm the database backup and recovery point.
2. Run the migration against a current, isolated database copy.
3. Review generated SQL and lock/rewrite risk.
4. Record the expected duration and rollback decision point.
5. Run `alembic upgrade head` before deploying application code that requires the new schema.
6. Confirm `alembic current` reports the expected revision and run application health checks.

Never run `alembic downgrade` in production without a tested backup and an explicit data-loss review. Prefer restoring the database and rolling back the application when a downgrade would discard or rewrite data.

## Existing production database baseline

The first migration represents the schema already deployed in v1.1.0. It must not be applied as table creation to that existing database.

On an isolated copy of the current database, first verify that tables, columns, constraints, and indexes match the baseline. Then mark only the baseline revision as present and apply the additive index migration:

```powershell
$env:DATABASE_URL = '<isolated-database-copy-url>'
alembic stamp 20260715_01
alembic upgrade head
alembic check
```

After this succeeds and the application regression suite passes, repeat the same stamp/upgrade sequence in the controlled production migration window. Do not stamp a database whose schema has not been compared to the baseline.

## Clean database and local verification

```powershell
$env:DATABASE_URL = 'sqlite:///migration-test.sqlite'
$env:APP_ENV = 'migration'
$env:SEED_SAMPLE_DATA = 'false'
alembic upgrade head
alembic current
alembic check
```

The first revision creates the v1.1.0 schema. The second revision is a tested additive migration that indexes `audit_events.actor_user_id`.

## Creating later migrations

Change the SQLAlchemy models, then generate and review a revision:

```powershell
alembic revision --autogenerate -m 'describe the schema change'
alembic upgrade head
alembic check
```

Every migration must include a safe upgrade, a reviewed downgrade or documented restore requirement, tests from the previous revision, and an operations note when it can lock or rewrite a large table.
