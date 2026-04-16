# CSV Import Checklist

Use this before adding rows to `server/fixtures` so imports stay clean and predictable.

## General
- Keep files as UTF-8 CSV.
- Keep the exact filenames the importer expects.
- Do not leave required columns blank.
- Keep header names exact, including underscores.
- Avoid extra empty columns or stray commas.
- Save dates as `YYYY-MM-DD`.
- Keep `company_id` values aligned across related files.

## Required Files
- `companies.csv`
- `cycles.csv`
- `review_actions.csv`
- `validation_flags.csv`
- `esg_submissions_previous_year.csv`
- `esg_submissions_current_year.csv`

## File Checks

### `companies.csv`
- `company_id`
- `company_name`
- `sector`
- `asset_class`
- `geography`
- `portfolio_contact_email`
- `portfolio_contact_name`
- `client_visible`
- `current_status`

### `cycles.csv`
- `cycle_year`
- `submission_open_date`
- `submission_deadline`
- `extension_date`
- `reminder_days_before_deadline`
- `private_equity_template`
- `real_estate_template`
- `debt_template`
- `status`
- `carry_forward_prefill`

### `review_actions.csv`
- `company_id`
- `reporting_year`
- `review_status`
- `reviewer_role`
- `review_comment`

### `validation_flags.csv`
- `company_id`
- `reporting_year`
- `flag_type`
- `field_name`
- `issue_description`
- `severity`

### `esg_submissions_previous_year.csv`
- `company_id`
- ESG metric columns for prior-year rows
- Keep values numeric or text as appropriate

### `esg_submissions_current_year.csv`
- `company_id`
- ESG metric columns for current-year rows
- Include the fields you want the app to load

## Value Rules
- `client_visible`: use `true`, `false`, `yes`, `no`, `1`, or `0`
- Dates: use `YYYY-MM-DD`
- Numbers: keep them numeric, not text like `10 tonnes`
- Text fields: avoid line breaks inside cells if possible

## Quick Safety Check
- Every `company_id` in child files should exist in `companies.csv`.
- Every `review_actions.csv` and `validation_flags.csv` row should reference a valid `company_id`.
- Keep `cycle_year` unique in `cycles.csv`.
