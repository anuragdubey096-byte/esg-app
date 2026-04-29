# Role Closure Checklist (Strict)

Scope: Role 1 (Manager/Admin), Role 2 (Investor/LP), Role 3 (Portfolio Company)

Priority rules:
- P0: security, data integrity, runtime blockers
- P1: role parity and core functional completeness
- P2: polish, optimization, and extended scope

## P0 (Must close first)

- [x] Enforce tenant isolation for company-id write routes (`/company/{company_id}/...`) so company users can only access their own company.
- [x] Enforce tenant isolation for `GET /dashboard/company/{user_id}` for company users.
- [x] Enforce company write-lock behavior in company portal write path:
  - [x] block edits when cycle is closed unless unlock exists
  - [x] block edits after submitted/under review/approved/rejected unless unlock exists
  - [x] block submit when cycle is closed unless unlock exists
- [x] Fix LP dashboard runtime blockers (undefined variables in `LPDashboardPage.jsx`).
- [x] Replace LP report placeholder actions (alerts) with real export-trigger + downloadable file flow.
- [x] Add startup compatibility migrations for existing DBs:
  - [x] `users.lp_type`, `users.company_permissions`, `users.portfolio_id`
  - [x] `action_plans.description`, `action_plans.linked_metric`, `action_plans.created_at`, `action_plans.updated_at`
  - [x] backfill enum/name compatibility for LP type values.
- [x] Add/adjust regression checks in `self_test.py` for LP route smoke and company scope behavior.

## P1 (Core parity)

- [ ] Role 1:
  - [ ] Expand report frameworks beyond EDCI/SFDR where required by role spec (TCFD/GRI/PRI/SFDR variants).
  - [ ] Complete admin role split model if needed (Analyst/Manager/System Admin).
- [ ] Role 2:
  - [ ] Move LP dashboard/metrics payloads to fully DB-driven computation (remove static/mock blocks).
  - [ ] Enforce Standard vs Authorised LP company visibility in LP response payloads.
  - [ ] Fix `/lp/metrics` schema contract mismatch (`Dict[str, float]` vs mixed `period/value` objects).
- [ ] Role 3:
  - [x] Remove hardcoded cycle defaults from company UI (`cycleId=1`) and always bind active/selected cycle from API.
  - [ ] Ensure submit/edit UX clearly reflects lock state and unlock expiry.

## P2 (Polish and scale)

- [ ] Add audit-trail endpoints for LP report views/downloads and admin audit views.
- [ ] Add richer LP historical report metadata (size/status/source filters).
- [ ] Add bundle/chunk optimization for frontend (>500kB warning).
- [ ] Add dedicated automated test module for LP portal contract (dashboard, metrics, reports, permissions).
- [ ] Add E2E browser smoke suite per role routes.
