# ESG Caveman Mode Restoration Checklist

Last updated: 2026-04-30

## Phase 1 - Core Platform and Access

Status: Complete (compatibility parity achieved)

- [x] `POST /login`
- [x] `POST /auth/forgot-password`
- [x] `POST /auth/sso/{provider}`
- [x] `GET /dashboard/manager`
- [x] `GET /dashboard/investor`
- [x] `GET /dashboard/company/{user_id}`
- [x] `GET /health` (compatibility alias restored)
- [x] `GET /health/ready` (compatibility alias restored)
- [x] `GET /search/global` parity with ranking/filter/navigation depth (`type`, `limit`, scored page/company/action results)

Frontend wiring:
- [x] Existing manager/investor/company dashboard routes active
- [x] Global search wired in top navbar (`/search/global`)
- [x] Global search ranked results + navigation depth wiring completed

## Phase 2 - Data Collection, Validation, Workflow

Status: Complete (workflow and collaboration parity restored)

- [x] `POST /companies`
- [x] `POST /cycles`
- [x] `GET /cycles`
- [x] `PATCH /cycles/{cycle_id}/status`
- [x] `POST /company/{company_id}/submissions`
- [x] `PATCH /submissions/{submission_id}/status`
- [x] `POST /submissions/{submission_id}/review`
- [x] `POST /submissions/{submission_id}/validate`
- [x] `POST /submissions/{submission_id}/unlock`
- [x] `POST /companies/{company_id}/reminders`
- [x] `POST /calculator/ghg`
- [x] `POST /company/{company_id}/upload-evidence`

Frontend wiring:
- [x] Existing Submissions/Review Hub pages still wired
- [x] Collaboration workspace parity reintroduced for company users (claim/release/heartbeat + field updates)

## Phase 3 - Narrative and Reporting Foundation

Status: Complete (DB-backed narrative lifecycle parity restored)

- [x] `GET /narrative/summary`
- [x] `POST /narrative/generate` (compatibility endpoint restored)
- [x] `GET /narrative/{id}` (compatibility endpoint restored)
- [x] `GET /reports/{report_type}`
- [x] `GET /reports/{report_type}/export`
- [x] `GET /analytics/portfolio`
- [x] `GET /analytics/manager` (compatibility endpoint restored)
- [x] `GET /narrative/history` (compatibility endpoint restored)
- [x] `PATCH /narrative/{id}` (compatibility endpoint restored)
- [x] `POST /narrative/{id}/approve` (compatibility endpoint restored)
- [x] Historical narrative persistence parity (DB-backed narrative records and lifecycle state)

Frontend wiring:
- [x] Investor overview/analytics narrative panels active
- [x] Narrative history panel added to investor overview
- [x] Manager overview includes compatibility Narrative Ops (generate/approve)
- [x] Full narrative lifecycle UI parity (generate/edit/approve/history + company scope workflows)

## Phase 4 - LP Layer

Status: Complete

- [x] `GET /lp/dashboard` (compatibility endpoint restored)
- [x] `GET /lp/metrics` (compatibility endpoint restored)
- [x] `GET /lp/reports` (compatibility endpoint restored)

Frontend wiring:
- [x] Investor pages keep baseline analytics wiring
- [x] Reports page adds LP reports feed for investor role
- [x] Dedicated LP insights page wired (`/lp-insights`)
- [x] Dedicated LP dashboard composition parity (KPIs + impact story + metrics + report feed)

## Phase 5 - Live Ops, Activity, and Narrative Ops

Status: Complete

- [x] `GET /live/activity` (compatibility endpoint restored)
- [x] `GET /narrative/history` (compatibility endpoint restored)
- [x] `GET /ws/live` websocket endpoint restored
- [x] Collaboration endpoints restored:
- [x] `GET /company/submission/{cycle_id}`
- [x] `POST /company/submission/{cycle_id}`
- [x] `POST /company/submission/{cycle_id}/collaboration/claim`
- [x] `POST /company/submission/{cycle_id}/collaboration/release`
- [x] `POST /company/submission/{cycle_id}/collaboration/heartbeat`
- [x] `GET /submissions/{submission_id}/collaboration`

Frontend wiring:
- [x] Live activity panel added to investor overview
- [x] Real-time websocket client wiring parity in dashboards (manager/investor live cards)

## Phase 6 - Newsletters, External Context, Anomaly Intelligence

Status: Complete

- [x] `POST /newsletter/generate` (compatibility endpoint restored)
- [x] `POST /newsletter/export` (compatibility endpoint restored)
- [x] `POST /newsletter/send` (compatibility endpoint restored)
- [x] `GET /external-context/feed` (compatibility endpoint restored)
- [x] `GET /anomalies/summary` (compatibility endpoint restored)
- [x] `GET /company/anomalies` (compatibility endpoint restored)
- [x] `GET /cron/newsletter/{audience}` with secret handling parity

Frontend wiring:
- [x] Newsletter preview generation added to investor analytics
- [x] Dedicated newsletter operations page wired (`/newsletter-ops`)
- [x] Dedicated anomaly intelligence page wired (`/anomaly-intel`)
- [x] Cron trigger UX parity (secret + dry-run controls in newsletter ops console)

## Next Restoration Steps

1. Run full regression against `self_test_full_latest` contract to confirm edge-case behavior parity.
2. Optional hardening: add automated tests for websocket/collaboration and narrative DB lifecycle.
