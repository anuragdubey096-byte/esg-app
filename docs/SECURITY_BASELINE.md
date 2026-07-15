# Dependency Security Baseline

**Baseline date:** 2026-07-15  
**Owner:** Technical lead  
**Review cadence:** Weekly automation and monthly manual review  
**Next manual review:** 2026-08-15

## Policy

- Production releases must have no unreviewed critical or high dependency finding.
- Frontend production exposure is gated with `npm audit --omit=dev --audit-level=high`.
- Python dependencies are gated with `pip-audit==2.10.1` against `server/requirements.txt`.
- Dependabot checks npm, Python, and GitHub Actions dependencies weekly. Minor and patch updates are grouped and pull-request volume is limited.
- A finding may only be accepted temporarily when its exposure, accountable owner, mitigation, and review date are recorded here.
- Major upgrades are tested separately because they can change runtime behavior even when they fix a vulnerability.

## Baseline findings and remediation

The initial frontend production audit reported high-severity React Router findings. `react-router-dom` was upgraded from 7.14.0 to 7.18.1. The production audit then reported zero findings.

The initial complete frontend audit also reported seven development-tool findings: one critical, one high, four moderate, and one low. They affected Vitest, Vite, PostCSS, esbuild, Babel, and related transitive tooling. The project upgraded to Vitest 4.1.10, Vite 8.1.4, `@vitejs/plugin-react` 6.0.3, and PostCSS 8.5.10. The complete audit now reports zero findings.

The initial Python audit reported eight Starlette findings through FastAPI 0.111.1 and Starlette 0.37.2. FastAPI was upgraded to 0.139.0, which resolves Starlette 1.3.1. The Python audit now reports no known vulnerabilities.

No risk acceptance is open at this baseline.

## Verification record

- `npm audit --omit=dev`: zero findings
- `npm audit`: zero findings
- `python -m pip_audit -r server/requirements.txt`: no known vulnerabilities
- Backend isolated SQLite regression: 67/67 passed
- Frontend regression: 9/9 passed
- Frontend production build: passed

## Local verification

From `client/`:

```powershell
npm ci
npm audit --omit=dev --audit-level=high
npm audit
npm test
npm run build
```

From the repository root with the project virtual environment active:

```powershell
python -m pip install -r server/requirements.txt
python -m pip install pip-audit==2.10.1
python -m pip_audit -r server/requirements.txt
python server/self_test.py
```
