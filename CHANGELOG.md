# Changelog

All notable GreenLedger changes are recorded here. Versions follow Semantic Versioning.

## [Unreleased]

### Added

- Post-v1.1.0 implementation roadmap with sequenced releases, acceptance criteria, ownership, and rollout gates.
- GitHub Actions CI for repository validation, backend regression, frontend tests, and production frontend builds.
- Automated release metadata and Vercel configuration validation.
- Short-retention failure logs for backend and frontend CI jobs.

### Changed

- Backend self-tests now exit unsuccessfully when any regression check fails, allowing CI to block broken changes.

## [1.1.0] - 2026-07-15

### Added

- Role-specific manager, investor, and company dashboard experiences.
- Expanded ESG analytics, data-quality views, framework mapping, double materiality, and scenario analysis.
- Company targets, action plans, assurance decisions, evidence workflows, and correction windows.
- Formal EDCI and SFDR PDF reporting plus CSV export workflows.
- Portfolio narratives, narrative history and approval, newsletter operations, anomaly intelligence, and external ESG context.
- Private Vercel Blob persistence for generated report and newsletter exports.
- Frontend regression testing with Vitest for role routing and analytics reporting-year selection.
- Product, user, technical, operations, and release documentation.

### Changed

- Company analytics now resolves the latest submission by reporting year and submission order, including duplicate-year submissions.
- Analytics content and navigation are aligned to each user role.
- Frontend dependencies are no longer tracked in Git; reproducible installation uses `package-lock.json` and `npm ci`.
- Production health reports database, Blob storage, OpenAI configuration, and application version.
- Documentation now reflects OpenAI configuration and the current single-project Vercel architecture.

### Fixed

- Historical analytics selection when API submissions arrive out of order.
- Production API dependency, SPA routing, database bootstrap, and pooled Postgres startup issues accumulated after v1.0.0.
- Durable export retrieval across stateless Vercel function invocations.

### Verified

- Backend self-test contract: 67 checks.
- Frontend regression suite: 9 tests.
- Vite production build.
- Production homepage and health endpoint.
- Vercel Blob upload and authenticated retrieval.

## [1.0.0] - 2026-04-29

- Initial tagged GreenLedger baseline.
- Core authentication, dashboards, company records, collection cycles, submissions, review, analytics, and reporting foundation.
