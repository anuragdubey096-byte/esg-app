# Admin DB Update Guide

## 1. Small admin update script

Use this when you want to update one field in one row directly against the production database:

```bash
python server/admin_update_record.py --table submissions --id 24 --column status --value approved
```

Other examples:

```bash
python server/admin_update_record.py --table companies --id 4 --column name --value "Arclight Renewable Energy"
python server/admin_update_record.py --table narrative_summaries --id 7 --column status --value approved
python server/admin_update_record.py --list-tables
python server/admin_update_record.py --list-columns narrative_summaries
```

Notes:
- The script reads `DATABASE_URL`
- JSON strings are accepted for array/object columns
- It validates the table and column names before updating

## 2. Update a record through the app API

If the app already has an endpoint for the record you want to change, use that instead of raw SQL.

Examples:

```bash
curl -X PATCH "https://your-app.vercel.app/api/narrative/7" \
  -H "Content-Type: application/json" \
  -H "X-User-Role: manager" \
  -H "X-User-Email: manager@example.com" \
  -d '{"headline":"Updated headline","summary":"Updated summary","highlights":["A"],"watchouts":["B"],"recommendations":["C"]}'
```

```bash
curl -X POST "https://your-app.vercel.app/api/narrative/7/approve" \
  -H "Content-Type: application/json" \
  -H "X-User-Role: manager" \
  -d '{"approved":true}'
```

```bash
curl -X PATCH "https://your-app.vercel.app/api/submissions/24/status" \
  -H "Content-Type: application/json" \
  -H "X-User-Role: manager" \
  -d '{"status":"approved"}'
```

Use the same pattern for any other existing `PATCH` or `POST` route in `server/main.py`.

## 3. Edit `DATABASE_URL` in Vercel

1. Open your project in Vercel.
2. Click **Settings**.
3. Click **Environment Variables**.
4. Find `DATABASE_URL`.
5. Edit the value or add it if it is missing.
6. Save the change.
7. Go to **Deployments** and click **Redeploy** on the latest deployment.

Important:
- Env var changes only apply to new deployments.
- If the project was previously using SQLite locally, production should still use Postgres.
