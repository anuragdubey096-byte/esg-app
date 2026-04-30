import AnalyticsSectionBlock from './AnalyticsSectionBlock'

function toNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function totalFromSeverityCounts(counts) {
  if (!counts || typeof counts !== 'object') return null
  return Object.values(counts).reduce((total, value) => total + (Number(value) || 0), 0)
}

function getActionRequiredCount(statusBreakdown) {
  if (!statusBreakdown || typeof statusBreakdown !== 'object') return null
  const notStarted = Number(statusBreakdown['Not Started'] || 0)
  const inProgress = Number(statusBreakdown['In Progress'] || 0)
  const resubmission = Number(statusBreakdown['Resubmission Requested'] || 0)
  return notStarted + inProgress + resubmission
}

function getPendingApprovals(statusBreakdown) {
  if (!statusBreakdown || typeof statusBreakdown !== 'object') return null
  return Number(statusBreakdown.Submitted || 0) + Number(statusBreakdown['Under Review'] || 0)
}

function scoreBreakdownLabel(payload) {
  const breakdown = payload?.analytics?.score_breakdown
  if (!breakdown) return null
  const e = toNumber(breakdown.E)
  const s = toNumber(breakdown.S)
  const g = toNumber(breakdown.G)
  if (e === null || s === null || g === null) return null
  return `E ${e.toFixed(1)} | S ${s.toFixed(1)} | G ${g.toFixed(1)}`
}

const cycleOverviewMetrics = [
  {
    title: 'Submission Completion Rate',
    endpoint: '/analytics/manager',
    unit: '%',
    valueType: 'percent',
    decimals: 1,
    selectValue: (payload) => {
      const total = Number(payload?.analytics?.total_companies || 0)
      const reporting = Number(payload?.analytics?.reporting_companies || 0)
      if (!total) return null
      return (reporting / total) * 100
    },
  },
  {
    title: 'Days to Deadline',
    endpoint: '/analytics/manager',
    valuePath: 'summary.cycle_banner.days_remaining',
    unit: 'days',
    valueType: 'integer',
  },
  {
    title: 'Submissions Requiring Action',
    endpoint: '/analytics/manager',
    unit: 'submissions',
    valueType: 'integer',
    selectValue: (payload) => getActionRequiredCount(payload?.summary?.status_breakdown),
  },
  {
    title: 'Pending Approvals',
    endpoint: '/analytics/manager',
    unit: 'submissions',
    valueType: 'integer',
    selectValue: (payload) => getPendingApprovals(payload?.summary?.status_breakdown),
  },
]

const dataQualityMetrics = [
  {
    title: 'Validation Flags',
    endpoint: '/anomalies/summary',
    unit: 'flags',
    valueType: 'integer',
    selectValue: (payload) => totalFromSeverityCounts(payload?.severity_counts),
  },
  {
    title: 'Cross-Company Anomalies',
    endpoint: '/anomalies/summary',
    unit: 'companies',
    valueType: 'integer',
    selectValue: (payload) => {
      const rows = payload?.watchlist_companies
      return Array.isArray(rows) ? rows.length : null
    },
  },
  {
    title: 'YoY Variance Flags',
    endpoint: '/analytics/manager',
    valuePath: 'analytics.diversity_safety.high_variance_flags',
    unit: 'flags',
    valueType: 'integer',
  },
  {
    title: 'Data Confidence Score',
    endpoint: '/analytics/manager',
    valuePath: 'analytics.data_quality.confidence',
    unit: '%',
    valueType: 'percent',
    decimals: 1,
  },
  {
    title: 'Measured vs Estimated',
    endpoint: '/analytics/manager',
    valueType: 'text',
    unit: 'measured/estimated %',
    selectValue: (payload) => {
      const measured = toNumber(payload?.analytics?.data_quality?.confidence)
      if (measured === null) return null
      const estimated = Math.max(0, 100 - measured)
      return `${measured.toFixed(1)} / ${estimated.toFixed(1)}`
    },
  },
]

const portfolioPerformanceMetrics = [
  {
    title: 'ESG Scoring Leaderboard',
    endpoint: '/analytics/manager',
    unit: 'top score',
    valueType: 'number',
    decimals: 1,
    selectValue: (payload) => {
      const top = payload?.analytics?.top_performers
      if (!Array.isArray(top) || !top.length) return null
      return top[0]?.esg_score
    },
  },
  {
    title: 'Pillar Breakdown (E / S / G)',
    endpoint: '/analytics/manager',
    valueType: 'text',
    unit: 'score',
    selectValue: scoreBreakdownLabel,
  },
  {
    title: 'Sector Benchmarks',
    endpoint: '/analytics/manager',
    valueType: 'text',
    unit: 'sectors',
    selectValue: (payload) => {
      const sectors = payload?.analytics?.underperforming_sectors
      if (!Array.isArray(sectors) || !sectors.length) return null
      return sectors.join(', ')
    },
  },
  {
    title: 'Action Plan Completion Rate',
    endpoint: null,
    valueType: 'number',
    unit: '%',
    emptyLabel: 'Endpoint unavailable for action plan completion rate',
  },
]

const operationsMetrics = [
  {
    title: 'Reminder Log',
    endpoint: '/live/activity?limit=150',
    unit: 'events',
    valueType: 'integer',
    selectValue: (payload) => {
      if (!Array.isArray(payload)) return null
      return payload.filter((item) => String(item?.event_type || '').toLowerCase() === 'reminder_sent').length
    },
  },
  {
    title: 'Auditor Access',
    endpoint: null,
    valueType: 'text',
    unit: 'status',
    emptyLabel: 'Endpoint unavailable for auditor access tracking',
  },
  {
    title: 'Template Version',
    endpoint: '/cycles',
    valueType: 'text',
    unit: 'active cycle',
    selectValue: (payload) => {
      if (!Array.isArray(payload) || !payload.length) return null
      const active = payload.find((cycle) => String(cycle?.status || '').toLowerCase() === 'active') || payload[0]
      if (!active) return null
      return active.cycle_year ? `CY ${active.cycle_year}` : null
    },
  },
  {
    title: 'Cycle Completion Trend',
    endpoint: '/analytics/manager',
    valueType: 'percent',
    unit: '%',
    decimals: 1,
    selectValue: (payload) => {
      const rows = payload?.summary?.progress_rows
      if (!Array.isArray(rows) || !rows.length) return null
      const total = rows.length
      const completed = rows.filter((row) => String(row?.status || '').toLowerCase() === 'approved').length
      return (completed / total) * 100
    },
  },
]

export default function AdminAnalyticsSections({ user }) {
  return (
    <>
      <AnalyticsSectionBlock title="Cycle Overview Section" user={user} metrics={cycleOverviewMetrics} />
      <AnalyticsSectionBlock title="Data Quality Section" user={user} metrics={dataQualityMetrics} />
      <AnalyticsSectionBlock title="Portfolio Performance Section" user={user} metrics={portfolioPerformanceMetrics} />
      <AnalyticsSectionBlock title="Operations Section" user={user} metrics={operationsMetrics} />
    </>
  )
}
