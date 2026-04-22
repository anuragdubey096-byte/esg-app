# ESG Platform Caveman Mode Roadmap

Purpose: give a simple, phase-by-phase build order so you can send me one phase at a time and I can implement it without re-planning the whole product.

Rule of caveman mode:
- One phase at a time.
- One clear goal at a time.
- No redesign unless the phase asks for it.
- Keep the current app structure, routes, and shared patterns.
- Use approved data only for AI features.
- Prefer existing components, endpoints, and schemas before creating new ones.

## How to use this document

When you want me to build a phase, send:
- Phase number
- Feature IDs in that phase
- What must be visible in the UI
- What must happen in the backend
- Any fixed wording, colors, or business rules
- Any data source or benchmark values to use
- What is out of scope

I will then implement only that phase, test it, and stop.

## Current Feature Status

Legend:
- Done = already present in the repo in a usable form
- Partial = some parts exist, but it still needs advancement
- Missing = not really built yet

| # | Feature | Status | Notes |
|---|---|---|---|
| 1 | AI ESG Narrative Summary | Mostly done | Narratives now have a stronger board-ready prompt, normalized AI output, and stable edit/approve/export flows. Richer report integration and broader generation workflows remain the main follow-on work. |
| 2 | ESG Impact Intelligence Engine | Mostly done | Impact story cards, metric tooltips, benchmarks, trend summaries, and portfolio chart data now land from approved data. Could still benefit from more surfaces that consume the deeper analytics. |
| 3 | Smart PDF Report Builder | Done | PDF exports now use a branded multi-section builder with KPI cards, portfolio tables, narrative appendix, chart embeds, and attachment handling. |
| 4 | ESG Newsletter Generator | Done | Newsletter generation now exists with dashboard cards on the manager and investor surfaces, plus SMTP send actions and cron-based delivery routes for automatic mailouts. |
| 5 | AI Document Data Extractor | Done | Evidence uploads now persist into active submissions, detect document families, and support confirm/override across policy and report uploads with summary metadata. |
| 6 | Sectoral ESG News & Regulatory Feed | Missing | No live feed or digest system yet. |
| 7 | Single Shared Component Library | Done | Shared buttons/cards/tables now consume the shared foundation tokens. |
| 8 | Global Status Colour Mapping | Done | Shared status tones and labels are centralized through the foundation config. |
| 9 | Typography & Spacing Standards | Done | Typography, spacing, radii, shadows, and the remaining page-local style literals are now tokenized. |
| 10 | Per-Fund White-Label Theming | Done | Brand profiles and theme tokens now live in shared config and are applied from persisted experience state. |
| 11 | Light / Dark Mode Support | Done | User theme toggle, persisted appearance state, and theme-token application are wired through the shared experience context. |
| 12 | Data Visualisation Colour Palette | Done | Chart and pillar palettes are centralized in the shared foundation config. |
| 13 | WebSocket Live Dashboard Updates | Missing | No real-time update channel yet. |
| 14 | In-Platform Toast Notification System | Missing | No general toast system yet. |
| 15 | Real-Time Submission Activity Feed | Missing | No live feed or event stream yet. |
| 16 | Fuzzy Global Search | Done | Global search now uses shared ranking weights, exact/prefix boosts, and role-aware catalog/company filtering. |
| 17 | Saved Filter Sets | Done | Saved filter presets and last-used filter state are persisted and restored across the main filter views. |
| 18 | Role-Scoped Search Boundaries | Done | Search results are scoped by role in the backend and verified in self-tests for manager, investor, and company access. |
| 19 | Zero Hardcoded Data Policy | Done | LP/company hardcoded defaults now resolve from DB-backed cycle and metrics data, including the remaining trend and score heuristics. |
| 20 | Config-Driven Architecture | Done | Core tokens, portal config, active cycle ownership, and the remaining LP/dashboard thresholds now flow from shared data or config. |
| 21 | Synthetic Test Data Standard | Done | Seed scripts, fixtures, and self-tests now validate the synthetic data contract and cross-file company coverage. |
| 22 | AI-Powered Anomaly Detection | Missing | No anomaly detection workflow yet. |
| 23 | Multi-User Collaboration on Submissions | Missing | No shared editing or section ownership system yet. |
| 24 | Carbon Footprint Calculator | Done | GHG calculator now returns a footprint summary, factor metadata, equivalence text, and activity-based breakdowns that can be applied back to the submission form. |

## Recommended Build Sequence

This is the order I recommend, based on dependencies and reuse.

### Phase 1: Foundation
Build first:
- 20 Config-Driven Architecture
- 19 Zero Hardcoded Data Policy
- 21 Synthetic Test Data Standard
- 7 Single Shared Component Library
- 8 Global Status Colour Mapping
- 9 Typography & Spacing Standards
- 12 Data Visualisation Colour Palette
- 18 Role-Scoped Search Boundaries

Why first:
- These features remove future rework.
- They make every later feature easier to build.
- They stop hardcoded values, layout drift, and inconsistent status handling.

Current state:
- Items 7, 8, 9, 12, 18, 19, 20, and 21 are done.

### Phase 2: Platform Experience
Build second:
- 11 Light / Dark Mode Support
- 10 Per-Fund White-Label Theming
- 16 Fuzzy Global Search (Caveman Mode)
- 17 Saved Filter Sets

Why second:
- These are high-visibility product features.
- They depend on the foundation being clean.
- They improve the daily experience for all roles.

### Phase 3: Intelligence and Reports
Build third:
- 1 AI ESG Narrative Summary
- 2 ESG Impact Intelligence Engine
- 24 Carbon Footprint Calculator
- 3 Smart PDF Report Builder
- 5 AI Document Data Extractor

Why third:
- Narrative and impact features feed reports.
- The calculator and extractor both strengthen approved-data workflows.
- PDF output should happen after the narrative and intelligence layer are stable.

### Phase 4: Real-Time Collaboration
Build fourth:
- 13 WebSocket Live Dashboard Updates
- 14 In-Platform Toast Notification System
- 15 Real-Time Submission Activity Feed
- 23 Multi-User Collaboration on Submissions

Why fourth:
- These features share the same live event and collaboration pattern.
- They are easier to build together than one by one.

### Phase 5: External Context and Advanced AI
Build fifth:
- 4 ESG Newsletter Generator
- 6 Sectoral ESG News & Regulatory Feed
- 22 AI-Powered Anomaly Detection

Why fifth:
- These depend on the earlier reporting, narrative, and data layers.
- They add the next level of value after the core workflows are solid.

### Phase 6: Hardening and Release
Finish with:
- regression tests
- accessibility pass
- performance pass
- data integrity pass
- deployment checks
- documentation updates

Why last:
- This locks the app in after the product features are complete.

## One-Line Feature Order

If you want the exact build order as a simple list:

20 -> 19 -> 21 -> 7 -> 8 -> 9 -> 12 -> 18 -> 11 -> 10 -> 16 -> 17 -> 1 -> 2 -> 24 -> 3 -> 5 -> 13 -> 14 -> 15 -> 23 -> 4 -> 6 -> 22

## Phase Input Checklist

Send these inputs when you want a phase built.

### Phase 1 inputs
- Which values must become config-driven
- Which tables or JSON fields are the source of truth
- Which hardcoded values must be removed first
- Which status colors must stay unchanged
- Which seed data rules must remain stable

### Phase 2 inputs
- Brand color or fund theme rules
- Light mode and dark mode preferences
- Search behavior examples
- Saved filter names and default filters
- Any wording changes for navigation or labels

### Phase 3 inputs
- Narrative tone rules
- Benchmark values and comparison rules
- Impact equivalents you want shown
- PDF layout expectations
- Calculator input fields and emission factors
- Document types to support for extraction

### Phase 4 inputs
- Which events should trigger live updates
- Which events should trigger toasts
- Activity feed event types
- Collaboration roles and section ownership rules
- Any lock/unlock behavior

### Phase 5 inputs
- Newsletter cadence
- Newsletter sections
- News and regulatory sources
- Anomaly threshold rules
- What the AI should flag or ignore

### Phase 6 inputs
- Acceptance criteria for each finished feature
- Browser/device checks
- Performance limits
- Deployment target and env vars
- Any final copy or branding fixes

## Caveman Mode Prompt Template

Use this when you want me to work on one phase:

```text
Build Phase X from CAVEMAN_MODE_ROADMAP.md.
Feature IDs: ...
Must-have UI: ...
Must-have backend: ...
Data rules: ...
Copy/labels: ...
Out of scope: ...
Acceptance criteria: ...
```

## Suggested Delivery Strategy

- Build one phase.
- Run tests.
- Fix breakage.
- Stop.
- Move to the next phase only after you approve it.

This keeps the work small, safe, and easy to review.
