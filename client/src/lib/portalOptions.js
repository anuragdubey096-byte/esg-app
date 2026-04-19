export const REPORT_FRAMEWORK_OPTIONS = [
  { id: 'edci', label: 'EDCI' },
  { id: 'sfdr', label: 'SFDR' },
]

export const NARRATIVE_TONE_OPTIONS = [
  { value: 'board-ready', label: 'Board-ready' },
  { value: 'lp-letter', label: 'Investor letter' },
  { value: 'exec-summary', label: 'Exec summary' },
]

export const DEFAULT_REPORT_VIEW = {
  framework: REPORT_FRAMEWORK_OPTIONS[0].id,
  portfolio: 'All Portfolio Companies',
  period: 'Current Cycle',
  format: 'csv',
  narrativeTone: 'board-ready',
}

export const NARRATIVE_UI_COPY = {
  summaryCard: {
    title: 'AI ESG Narrative Summary',
    subtitle: 'Board-ready plain-English summary generated from approved data only',
    loading: 'Generating narrative from approved submission data...',
    error: 'Narrative summary could not load.',
    notReadyTitle: 'Narrative not ready yet',
    notReadyDescription: 'This summary appears after an approved submission is available.',
    highlightsTitle: 'Highlights',
    watchoutsTitle: 'Watchouts',
    nextStepsTitle: 'Next steps',
    whatDoesThisMean: 'What does this mean?',
  },
  impactStory: {
    title: 'Impact Intelligence',
    subtitle: 'Plain-English interpretation of the live portfolio',
    highlightsTitle: 'Highlights',
    watchoutsTitle: 'Watchouts',
    nextStepsTitle: 'Next steps',
    whatDoesThisMean: 'What does this mean?',
  },
  pages: {
    lpDashboardNarrativeSubtitle: 'Board-ready portfolio narrative for investors',
    lpDashboardImpactSubtitle: 'Emissions translated into investor language',
    reviewHubNarrativeSubtitle: 'Company-level narrative from approved submission data',
    reviewHubNarrativeControlsSubtitle: 'Admin can edit, approve, and export the company confirmation letter',
    reportsNarrativeSubtitle: 'Board-ready narrative from approved portfolio data',
    reportsNarrativeInsertSubtitle: 'Portfolio-level narrative insert for reports',
  },
}

const REPORT_FRAMEWORK_KEYWORDS = {
  edci: 'edci',
  sfdr: 'sfdr',
}

export function resolveReportFrameworkId(report) {
  if (report?.report_type) {
    const reportType = String(report.report_type).toLowerCase()
    const matched = REPORT_FRAMEWORK_OPTIONS.find((item) => item.id === reportType)
    if (matched) return matched.id
  }

  const name = String(report?.report_name || '').toLowerCase()
  return Object.entries(REPORT_FRAMEWORK_KEYWORDS).find(([keyword]) => name.includes(keyword))?.[1] || null
}
