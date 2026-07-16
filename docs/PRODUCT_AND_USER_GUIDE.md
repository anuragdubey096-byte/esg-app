# GreenLedger Product and User Guide

**Release:** v1.1.0
**Audience:** business stakeholders, ESG teams, portfolio managers, investors, company contributors, reviewers, and demo presenters

## 1. Product summary

GreenLedger is a shared ESG operating system for a portfolio. Companies submit structured metrics and evidence; managers review and validate the information; investors consume portfolio-level analytics, narratives, and reports. The system keeps each role focused on the information and actions it is allowed to use.

The platform addresses five common problems:

1. ESG information arrives in inconsistent files and formats.
2. Evidence, comments, confidence, and review decisions are separated from reported values.
3. Portfolio teams cannot easily compare reporting years or identify missing data.
4. Companies and reviewers lose track of corrections and follow-up actions.
5. Reports and stakeholder narratives take time to rebuild from source data.

## 2. Core concepts

| Concept | Meaning |
| --- | --- |
| Reporting cycle | A configured collection period, normally identified by a fiscal year and submission deadline. |
| Submission | A company's ESG metric set for a reporting cycle. |
| Evidence | A file or reference supporting a reported metric. |
| Confidence | The source-quality classification attached to a value, such as measured or estimated. |
| Validation flag | A rule-based or reviewer-created issue attached to a submission and reporting year. |
| Review decision | A manager action that moves a submission through the controlled status workflow. |
| Target | A measurable ESG outcome with owner, due date, progress, and status. |
| Action plan | An operational initiative created in response to ESG performance or risk. |
| Narrative | A generated and optionally approved explanation of portfolio or company ESG performance. |

## 3. Role and access matrix

| Workspace | Manager | Investor | Company |
| --- | :---: | :---: | :---: |
| Overview | Yes | Investor version | Company version |
| Review Hub | Yes | No | No |
| Submissions | Portfolio management | Read-only portfolio view | Company entry and submission |
| Analytics | Manager portfolio view | Investor portfolio view | Company historical view |
| ESG Strategy | Yes | Yes | No |
| Portfolio & Company Onboarding | Yes | No | No |
| Alerts & Risks | Yes | No | No |
| Action Plans | Yes | No | Yes |
| Reports | Yes | Yes | Yes |
| LP Insights | No | Yes | No |
| Newsletter Operations | Yes | Yes | No |
| Anomaly Intelligence | Yes | Yes | Yes |
| Cycle Configuration | Yes | No | No |

Role checks are enforced in both the frontend navigation and protected backend endpoints. Hiding a menu item is not treated as the security boundary.

## 4. End-to-end reporting workflow

### Step 1: Manager prepares a cycle

The manager opens **Cycle Config**, creates the fiscal-year cycle, sets dates and status, and activates the appropriate collection period. The cycle establishes the context used by submissions, deadlines, and historical comparisons.

### Step 2: Company prepares ESG data

The company opens **Submissions**, enters environmental, social, and governance data, labels confidence, attaches evidence, and saves its working draft. The form includes required-field and variance rules. Collaboration controls reduce accidental concurrent editing.

### Step 3: Company submits

The company reviews validation messages and confirms the submission. A submitted record becomes the basis for manager review; controlled correction windows are used when edits are needed later.

### Step 4: Manager validates and reviews

The manager uses **Review Hub** to inspect values, evidence, prior-year context, validation flags, and comments. The manager can move a submission through the allowed lifecycle:

`Submitted -> Under Review -> Approved`

or:

`Submitted -> Under Review -> Rejected / Resubmission Requested -> Submitted`

The audit trail records review and status activity.

### Step 5: Teams act on findings

Managers and companies can create targets and action plans. Portfolio views highlight incomplete coverage, outliers, anomalies, upcoming deadlines, and performance gaps.

### Step 6: Stakeholders consume outputs

Managers and investors use analytics, LP insights, narratives, newsletters, CSV exports, and PDF reports. In production, generated exports are stored in private Vercel Blob storage and retrieved through the authenticated application route.

## 5. How analytics reporting years work

Company Analytics lists unique reporting years from newest to oldest. **Latest** selects the newest reporting year, not merely the final array item returned by the API. If more than one submission exists for the same year, the newest submission record for that year is used. The reporting year stored in the ESG payload takes precedence; the cycle year is the fallback.

This behavior is covered by automated frontend tests to prevent historical views from silently displaying an older record.

## 6. Key outputs

### Portfolio setup and company onboarding

The manager-only Portfolio Setup page creates company data-collection accounts, portfolios, funds, and holdings. Company onboarding captures identity, sector, geography, asset class, lifecycle status, and a contributor login in one transaction. Credentials are shown after creation for controlled delivery to the contributor.

The Strategy page does not infer investments from the company directory. A manager must first create a portfolio, create its funds, and connect companies as holdings with ownership percentage, effective date, and a positive NAV or invested amount in the fund base currency. Scenario analysis remains unavailable until this scope is complete.

Operational climate impacts are attributed using ownership percentage. Portfolio risk averages use current NAV, falling back to invested amount only when NAV is unavailable. Missing company ESG submissions are shown as a coverage gap and are not silently treated as zero. Scenario results are screening estimates rather than valuations or forecasts.

- Portfolio ESG score and E/S/G breakdowns
- Reporting coverage and submission funnel
- Emissions and resource-use trends
- Diversity, safety, governance, and data-quality indicators
- Top and bottom performers and underperforming sectors
- Validation, anomaly, assurance, and evidence summaries
- EDCI and SFDR PDF reports
- CSV analytics exports
- AI-assisted portfolio/company narratives and newsletter drafts

Generated analysis is decision support, not a substitute for legal, assurance, accounting, or regulatory advice. Source submissions and evidence remain the authoritative inputs.

## 7. Suggested explanation or demo script

Use this short sequence when presenting GreenLedger:

1. **Problem:** "Portfolio ESG data is fragmented across spreadsheets, emails, evidence files, and review notes."
2. **Solution:** "GreenLedger joins collection, evidence, review, analytics, actions, and reporting in one role-aware workflow."
3. **Company view:** Show how a company enters a reporting year, adds confidence and evidence, checks validation, and submits.
4. **Manager view:** Show Review Hub, prior-year comparison, comments, flags, and the controlled approval/resubmission workflow.
5. **Investor view:** Show reporting coverage, portfolio analytics, LP insights, materiality/scenarios, and reports.
6. **Trust:** Explain backend role enforcement, audit activity, private Blob storage, and automated regression tests.
7. **Outcome:** "The same governed data moves from company input to portfolio decision and stakeholder output without rebuilding the story in separate tools."

## 8. Operational responsibilities

### Manager

- Keep only the intended collection cycle active.
- Review validation flags and evidence before approval.
- Use correction windows rather than bypassing status controls.
- Confirm the reporting year before comparing or exporting data.

### Company

- Use the correct reporting cycle and year.
- Explain material year-on-year changes.
- Attach evidence for required or material metrics.
- Confirm values and confidence labels before submission.

### Investor

- Interpret portfolio results with reporting coverage and data quality.
- Distinguish missing data from genuine zero values.
- Use narratives as summaries of the governed underlying records.

## 9. Support checklist

When a user reports an issue, capture:

- Their role and account email
- The page and action
- Company and reporting year, if relevant
- Expected and actual result
- Time of occurrence
- Screenshot without secret values

For deployment or API issues, also check `/api/health`, the Vercel deployment SHA, runtime errors, database status, and Blob configuration.
