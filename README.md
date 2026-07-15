# GreenLedger ESG Platform

**Current release: v1.1.0**

GreenLedger is a role-aware ESG data collection, review, analytics, and reporting platform. It gives portfolio managers, investors, and portfolio companies one workflow for collecting evidence-backed ESG data and turning it into decisions and reports.

Production: [esg-app-two.vercel.app](https://esg-app-two.vercel.app/)

## What the platform does

- Runs configurable annual ESG reporting cycles.
- Collects company metrics, confidence labels, comments, and evidence.
- Validates submissions and records manager review decisions.
- Tracks corrections, action plans, ESG targets, and assurance.
- Presents role-specific portfolio and company analytics.
- Supports materiality, scenario analysis, anomalies, and external context.
- Generates narratives, newsletters, CSV exports, and formal PDF reports.
- Persists generated exports in private Vercel Blob storage in production.

## User roles

| Role | Primary purpose |
| --- | --- |
| Manager | Configure cycles, review submissions, validate data, manage portfolio actions, and generate reports. |
| Investor | Monitor portfolio performance, analytics, LP insights, strategy, narratives, and reports. |
| Company | Enter and submit ESG data, attach evidence, track company analytics, targets, and action plans. |

See [Product and User Guide](docs/PRODUCT_AND_USER_GUIDE.md) for the complete role matrix and an explanation script suitable for a demonstration.

## Technology

- React 18 and Vite frontend
- FastAPI and SQLAlchemy backend
- Postgres for durable production data; SQLite fallback for local development
- Vercel for frontend and Python function hosting
- Private Vercel Blob for generated exports
- OpenAI for configured AI narratives and agent features, with deterministic fallbacks where supported

See [Technical and Operations Guide](docs/TECHNICAL_AND_OPERATIONS_GUIDE.md) for architecture, setup, testing, deployment, and troubleshooting.

## Local setup

### Backend

```bash
cd server
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

The backend runs at `http://127.0.0.1:8000`.

### Frontend

In a second terminal:

```bash
cd client
npm ci
npm run dev
```

The frontend runs at `http://127.0.0.1:5173` and proxies `/api` requests to the local backend.

## Environment variables

| Variable | Purpose | Required in production |
| --- | --- | --- |
| `DATABASE_URL` | Durable Postgres connection string | Yes |
| `BLOB_READ_WRITE_TOKEN` | Private Vercel Blob access for generated exports | Yes for durable exports |
| `OPENAI_API_KEY` | AI narratives and agent features | Yes for AI output |
| `OPENAI_MODEL` | Narrative model override; defaults to `gpt-4o-mini` | No |
| `FRONTEND_ORIGIN` | Allowed production frontend origin | Recommended |
| `APP_ENV=production` | Marks the runtime as production | Recommended |
| `SEED_SAMPLE_DATA=false` | Prevents demo data seeding into a durable production database | Recommended |

Never commit environment files or secret values.

## Verification

```bash
# Backend regression suite, from repository root
python server/self_test.py

# Frontend tests and build
cd client
npm test
npm run build
```

The v1.1.0 frontend suite covers role routing and company analytics reporting-year selection.

## Deployment

The repository is deployed as one Vercel project from its root. `vercel.json` installs and builds the client, serves `client/dist`, mounts the FastAPI wrapper from `api/index.py`, and preserves SPA routing.

Use [Vercel Production Checklist](VERCEL_PRODUCTION_CHECKLIST.md) before and after a production release.

## Release documentation

- [Changelog](CHANGELOG.md)
- [Product and User Guide](docs/PRODUCT_AND_USER_GUIDE.md)
- [Technical and Operations Guide](docs/TECHNICAL_AND_OPERATIONS_GUIDE.md)
- [Restoration Checklist](RESTORATION_CHECKLIST.md)
- [Vercel Production Checklist](VERCEL_PRODUCTION_CHECKLIST.md)

The canonical release number is stored in [`VERSION`](VERSION).
