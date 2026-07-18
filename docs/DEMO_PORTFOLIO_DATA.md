# Editable demo portfolio data

The file `client/public/demo-portfolio.csv` contains synthetic portfolio, fund, ownership, investment, and NAV data for the 20 verified onboarded companies (`C001` through `C020`). It is demonstration data only and must not be represented as actual financial exposure.

Managers can download the CSV from **Portfolio Setup**, edit it in a spreadsheet application, preview it, and then commit it. The CSV remains the editable source of truth; portfolio values are not hardcoded in the application.

## Safe workflow

1. Download the editable demo CSV from Portfolio Setup.
2. Change portfolio, fund, holding, ownership, investment, NAV, currency, status, or effective-date values as required.
3. Keep all amount columns in the stated portfolio and fund base currency. The importer does not convert currencies.
4. Upload the CSV and select **Preview CSV**.
5. Correct every blocked row before selecting **Commit CSV**.

Re-importing the same portfolio code, fund code, and holding external ID updates the editable record instead of creating a duplicate. Company matching always uses an existing GreenLedger company code.
