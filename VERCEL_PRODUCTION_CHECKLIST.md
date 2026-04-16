# Vercel Production Checklist

Use this checklist before and during production deploys of the ESG app.

## 1. Required environment variables

Set these in the Vercel project settings:

- `DATABASE_URL`
  - Production Postgres connection string
  - Do not use SQLite on Vercel
- `BLOB_READ_WRITE_TOKEN`
  - Required for report and narrative PDF exports
- `OPENAI_API_KEY`
  - Required for AI ESG Narrative Summary generation
- `OPENAI_MODEL`
  - Optional model override, defaults to `gpt-4o-mini`
- `FRONTEND_ORIGIN`
  - Exact public origin of the deployed app
  - Example: `https://your-app.vercel.app`

## 2. Optional environment variables

Only needed for split deployments or advanced setups:

- `BACKEND_URL`
  - Only if you deploy `client/` as a standalone frontend project
  - Not needed for the single root-project Vercel setup
- `VITE_API_BASE_URL`
  - Only if you want the frontend to point to a non-default API base
  - Default production value is `/api`

## 3. Repository layout checks

- Root project is deployed from the repository root
- `api/index.py` exports the FastAPI app
- `client/` builds the frontend into `client/dist`
- `server/database.py` requires Postgres on Vercel
- `server/storage.py` uses Vercel Blob when the token is present

## 4. Vercel project settings

- Root directory: repository root
- Build command: `cd client && npm ci && npm run build`
- Output directory: `client/dist`
- Keep API routes served by the FastAPI app under `/api`
- Keep SPA fallback for non-API frontend routes

## 5. Pre-deploy verification

- Frontend build passes
- Backend Python files compile
- Narrative smoke test passes
- Vercel config parses as valid JSON

## 6. Post-deploy verification

Check these live after deployment:

- Frontend home page loads
- Login works for admin, LP, and company users
- `/api` routes return JSON, not HTML
- Review Hub narrative loads for approved submissions
- Admin editing still works
- LP and company views remain read-only
- PDF export works

## 7. Common failure points

- Missing `DATABASE_URL`
- Missing `BLOB_READ_WRITE_TOKEN`
- Missing `OPENAI_API_KEY`
- Wrong `FRONTEND_ORIGIN`
- Accidentally deploying from `client/` when you meant to use the root project
- Using SQLite in production
- Caching an old browser bundle after deploy

## 8. Quick rollback rule

If a deploy breaks the app:

- Revert the last commit or redeploy the previous successful build
- Keep the database and blob tokens unchanged
- Recheck the route behavior at `/api` and the frontend fallback
