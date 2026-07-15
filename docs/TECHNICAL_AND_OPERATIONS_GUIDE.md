# GreenLedger Technical and Operations Guide

**Release:** v1.1.0
**Audience:** developers, maintainers, technical reviewers, and deployment operators

## 1. Architecture

```text
Browser
  -> React/Vite single-page application
  -> /api requests on the same Vercel origin
  -> api/index.py serverless wrapper
  -> FastAPI application and role dependencies
  -> SQLAlchemy
      -> Postgres for durable production records
      -> SQLite fallback for local/ephemeral operation
  -> Private Vercel Blob for generated exports
  -> OpenAI when configured for narrative and agent features
```

The root Vercel project builds `client/` and serves `client/dist`. Requests under `/api/*` are rewritten to `api/index.py`; non-API routes fall back to `index.html` for client-side routing.

## 2. Repository map

| Path | Responsibility |
| --- | --- |
| `client/src/` | React pages, layouts, components, hooks, routing, and frontend tests |
| `server/main.py` | Core FastAPI endpoints and domain behavior |
| `server/models.py` | SQLAlchemy persistence models |
| `server/schemas.py` | API request and response schemas |
| `server/storage.py` | Vercel Blob and local export persistence |
| `server/routers/agent.py` | Role-aware ESG agent API |
| `server/self_test.py` | Backend regression contract |
| `api/index.py` | Vercel Python entry point, API mounting, and degraded fallback |
| `vercel.json` | Build output and routing configuration |
| `VERSION` | Canonical human-readable release version |

## 3. Application versioning

GreenLedger uses Semantic Versioning:

- Major: incompatible workflow, API, or data-model change
- Minor: backward-compatible product capability
- Patch: backward-compatible correction

For a release, update:

1. `VERSION`
2. `server/version.py`
3. `client/package.json`
4. `client/package-lock.json`
5. `CHANGELOG.md`

The API publishes the version in FastAPI metadata and `/health` output. Git tags use the `vMAJOR.MINOR.PATCH` format.

## 4. Local development

### Prerequisites

- Python 3.11 or compatible runtime
- Node.js 20 or compatible runtime
- npm
- Postgres connection for durable/shared development data, or local SQLite fallback

### Backend

```bash
cd server
python -m venv .venv
# activate the environment
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd client
npm ci
npm run dev
```

Vite proxies local `/api` calls to `http://127.0.0.1:8000`.

### Database behavior

`server/database.py` normalizes `DATABASE_URL`. Without a valid configured URL, local development uses `server/db.sqlite`. On Vercel, an invalid or absent database URL can fall back to `/tmp/db.sqlite`, which is ephemeral and must not be treated as durable production storage.

## 5. Configuration

| Variable | Behavior |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy database URL; use Postgres in production. |
| `BLOB_READ_WRITE_TOKEN` | Enables private Vercel Blob export persistence. |
| `OPENAI_API_KEY` | Enables OpenAI-backed narrative and agent operations. |
| `OPENAI_MODEL` | Overrides the default narrative model. |
| `FRONTEND_ORIGIN` | Adds the intended frontend origin to CORS handling. |
| `APP_ENV` | Identifies the runtime environment. |
| `SEED_SAMPLE_DATA` | Controls sample-data bootstrap behavior. |
| `SESSION_TTL_HOURS` | Controls authenticated session lifetime within the supported limit. |

Keep secrets in local ignored environment files or Vercel project settings. Never include them in commits, logs, screenshots, or documentation examples.

## 6. Authentication and authorization

Login creates a server-side authentication session and an HTTP-only cookie. Production cookies are secure and use `SameSite=Lax`. Backend dependencies enforce manager, investor, and company permissions on protected endpoints. Company-scoped operations also verify that the authenticated company user owns the requested company record.

Frontend route filtering improves usability but does not replace backend authorization.

## 7. Storage and exports

`server/storage.py` selects storage by environment:

- With `BLOB_READ_WRITE_TOKEN`: exports are written to private Vercel Blob.
- Local development without Blob: exports are written under the local export directory.
- Vercel without Blob: health reports storage as unconfigured; durable cross-invocation export behavior is unavailable.

Clients retrieve exports through `/exports/{file_name}`. The route validates safe filenames, reads the private object server-side, and returns a non-cacheable attachment response.

## 8. Tests and release gates

### Backend

```bash
python server/self_test.py
```

The self-test creates isolated test state and exercises authentication, role access, collection, review, analytics, reporting, Blob-aware exports, narratives, and related workflows.

### Frontend

```bash
cd client
npm test
npm run build
```

Current frontend regression coverage includes:

- Manager, investor, and company route allowlists
- Unknown-role fallback behavior
- Unique analytics reporting-year ordering
- Latest-year selection independent of API array order
- Duplicate-year submission selection
- Cycle-year fallback and invalid selections

### Pre-release minimum

- Backend self-test passes
- Frontend tests pass
- Vite production build passes
- `git diff --check` passes
- No secrets or generated dependencies are staged
- Production deployment metadata matches the intended commit SHA

The workflow in `.github/workflows/ci.yml` enforces repository validation, backend regression, frontend tests, and frontend build checks. `scripts/validate_release.py` verifies version consistency and the Vercel build/routing contract without external services.

## 9. Vercel deployment

The configured Git workflow deploys pushes to `main` to production.

1. Verify tests and build locally.
2. Commit the reviewed scope.
3. Push the exact commit to `origin/main`.
4. Match the Vercel deployment metadata to the full commit SHA.
5. Wait for `READY` and confirm the production alias.
6. Check `/`, `/api/health`, and recent runtime errors.
7. Confirm health reports `storage.mode = vercel-blob` when Blob is expected.

Do not roll back environment variables when rolling back application code.

## 10. Health and troubleshooting

`GET /api/health` reports:

- Release version
- Readiness and environment
- Database check
- Storage mode/configuration
- OpenAI configuration status

Common diagnoses:

| Symptom | First checks |
| --- | --- |
| Frontend route returns 404 | SPA rewrite and root Vercel project settings |
| `/api` returns HTML | API rewrite and `api/index.py` deployment |
| Login or dashboard hangs | Runtime errors, database connectivity, pooled Postgres URL |
| Export disappears | Blob token, health storage mode, and export route response |
| AI response falls back or errors | `OPENAI_API_KEY`, model setting, provider/runtime logs |
| Wrong analytics year | Submission payload year, cycle year, duplicate submission IDs |
| Changes appear reverted | Production deployment SHA and alias ownership |

If the full backend cannot start, `api/index.py` exposes a degraded fallback health response. Treat fallback mode as an incident signal, not a healthy production state.

## 11. Known follow-up work

- The sequenced roadmap, acceptance criteria, ownership model, and rollout gates are maintained in [Post-v1.1.0 Implementation Plan](IMPLEMENTATION_PLAN.md).
- Add CI enforcement for backend tests, frontend tests, and frontend build.
- Add focused automated websocket/collaboration tests.
- Expand narrative persistence and lifecycle test coverage.
- Add browser-level end-to-end tests for login, submission, review, and analytics flows.
