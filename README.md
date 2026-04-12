# ESG Data Collection App

A simple starter project for an ESG data collection web app.

- `client/` contains the React frontend.
- `server/` contains the FastAPI backend.
- `server/db.sqlite` will be the SQLite database file created automatically.

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

### Database Reset
Run `python server/reset_db.py` from the project root to rebuild `server/db.sqlite` with clean sample data.

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

Expected files:
- `cycles.csv`
- `review_actions.csv`
- `validation_flags.csv`
- `companies.csv`
- `esg_submissions_previous_year.csv`
- `esg_submissions_current_year.csv`

If you are loading synthetic data into an existing database, delete `server/db.sqlite` first or run `python server/reset_db.py` so the new schema is created.

The app starts with a simple login page that will later grow into the full ESG workflow.
