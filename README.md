# ESG Data Collection App

A simple starter project for an ESG data collection web app.

- `client/` contains the React frontend.
- `server/` contains the FastAPI backend.
- The backend uses Postgres through `DATABASE_URL` in both local development and production.

## Getting started

### Frontend
1. Navigate to the client directory: `cd client`
2. Run `npm install`.
3. Run `npm run dev`.

### Backend
1. Navigate to the server directory: `cd server`
2. Create and activate a virtual environment (optional but recommended).
   - On Windows: `python -m venv venv` followed by `venv\Scripts\activate`
   - On Mac/Linux: `python3 -m venv venv` followed by `source venv/bin/activate`
3. Run `pip install -r requirements.txt`.
4. Run `uvicorn main:app --reload`.

Local development reads `DATABASE_URL` from [server/.env.local](C:/Users/hp/esg-app/server/.env.local), so the app connects to Neon by default.

### Database Reset
Run `python server/reset_db.py` from the project root to rebuild the local database with clean sample data.

### Self-Test
Run `python server/self_test.py` from the project root to verify:
- sample logins
- admin, investor, client, and portfolio dashboards
- company creation
- cycle creation
- ESG submission storage
- submission status updates

### CSV Import
Run `python server/import_csv.py <folder-with-csv-files>` from the project root.
If your fixture CSVs are in `server/fixtures`, you can simply run `python server/import_csv.py` and it will use that folder automatically.

Expected files:
- `cycles.csv`
- `review_actions.csv`
- `validation_flags.csv`
- `companies.csv`
- `esg_submissions_previous_year.csv`
- `esg_submissions_current_year.csv`

Default fixture location:
- `server/fixtures`

If you are loading synthetic data into an existing database, run `python server/reset_db.py` so the new schema is created.

The app starts with a simple login page that will later grow into the full ESG workflow.

### Vercel Deployment
This repo is Vercel-ready as a single project from the repository root.

Root project env vars:
- `DATABASE_URL`: Postgres connection string.
- `BLOB_READ_WRITE_TOKEN`: Blob storage token for report and narrative exports.
- `FRONTEND_ORIGIN`: your Vercel URL for CORS.
- `ANTHROPIC_API_KEY`: required for Claude narrative generation.

Build settings:
- Root `vercel.json` builds the React client from `client/` and serves it from `client/dist`.
- The Python backend is exposed through the root `api/` directory.

1. Set the Vercel project root directory to the repository root.
2. Add the env vars above in the Vercel project settings.
3. Deploy. The React app will be built from `client/`, and the FastAPI app will run from `api/index.py`.

Alternative:
- If you prefer separate deployments, you can still deploy `client/` as its own Vercel project and point it at a separately hosted backend using `BACKEND_URL`.

### Legacy Data Migration
If you already have older local data and want to move it into Postgres, run:

```bash
python server/migrate_to_postgres.py --target "postgresql+psycopg2://..."
```

The script recreates the target schema and copies every ORM table in dependency order, preserving primary keys so relationships stay intact.
