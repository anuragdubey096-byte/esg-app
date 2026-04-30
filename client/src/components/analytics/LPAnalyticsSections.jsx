import AnalyticsSectionBlock from './AnalyticsSectionBlock'

function toNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function emissionsTrendDelta(payload) {
  const series = payload?.emissions_trend
  if (!Array.isArray(series) || series.length < 2) return null
  const previous = toNumber(series[series.length - 2]?.total_emissions)
  const current = toNumber(series[series.length - 1]?.total_emissions)
  if (previous === null || current === null || previous === 0) return null
  const diffPercent = ((current - previous) / previous) * 100
  return {
    direction: diffPercent > 0 ? 'up' : diffPercent < 0 ? 'down' : 'neutral',
    percent: diffPercent,
    label: 'vs prior period',
  }
}

function yoyTrend(payload) {
  const yoy = toNumber(payload?.portfolio_scorecard?.yoy_change_percent)
  if (yoy === null) return null
  return {
    direction: yoy > 0 ? 'up' : yoy < 0 ? 'down' : 'neutral',
    percent: yoy,
    label: 'vs prior year',
  }
}

const overviewMetrics = [
  {
    title: 'Portfolio ESG Score',
    endpoint: '/lp/dashboard',
    valuePath: 'portfolio_scorecard.overall_esg_score',
    unit: '/100',
    valueType: 'number',
    decimals: 1,
    selectTrend: yoyTrend,
  },
  {
    title: 'ESG Performance Trend',
    endpoint: '/lp/dashboard',
    valuePath: 'portfolio_scorecard.yoy_change_percent',
    unit: 'YoY %',
    valueType: 'percent',
    decimals: 1,
    selectTrend: yoyTrend,
  },
  {
    title: 'Data Coverage',
    endpoint: '/lp/dashboard',
    valuePath: 'completion_status.completion_percent',
    unit: 'coverage',
    valueType: 'percent',
    decimals: 1,
  },
]

const environmentalMetrics = [
  {
    title: 'GHG Emissions (tCO₂e)',
    endpoint: '/dashboard/investor',
    valuePath: 'emissions_totals.total',
    unit: 'tCO2e',
    valueType: 'number',
    decimals: 1,
    selectTrend: emissionsTrendDelta,
  },
  {
    title: 'Emissions Intensity',
    endpoint: '/dashboard/investor',
    valuePath: 'average_ghg_emissions',
    unit: 'tCO2e/company',
    valueType: 'number',
    decimals: 1,
  },
  {
    title: 'Energy Consumption',
    endpoint: '/dashboard/investor',
    valuePath: 'resource_totals.energy',
    unit: 'MWh',
    valueType: 'number',
    decimals: 1,
  },
  {
    title: 'Renewable Energy Mix',
    endpoint: '/dashboard/investor',
    valuePath: 'resource_totals.renewable_ratio',
    unit: '%',
    valueType: 'percent',
    decimals: 1,
    emptyLabel: 'No renewable mix field in current API',
  },
  {
    title: 'Water Withdrawal',
    endpoint: '/dashboard/investor',
    valuePath: 'resource_totals.water',
    unit: 'm3',
    valueType: 'number',
    decimals: 1,
  },
  {
    title: 'Waste Generated',
    endpoint: '/dashboard/investor',
    valuePath: 'resource_totals.waste',
    unit: 'tonnes',
    valueType: 'number',
    decimals: 1,
  },
]

const socialMetrics = [
  {
    title: 'Total Recordable Injury Rate',
    endpoint: '/dashboard/investor',
    valuePath: 'diversity_safety.trifr',
    unit: 'TRIR',
    valueType: 'number',
    decimals: 2,
  },
  {
    title: 'Lost Time Injuries',
    endpoint: '/dashboard/investor',
    valuePath: 'diversity_safety.lost_time_injuries',
    unit: 'incidents',
    valueType: 'integer',
    emptyLabel: 'No lost-time-injury field in current API',
  },
  {
    title: 'Fatalities',
    endpoint: '/dashboard/investor',
    valuePath: 'diversity_safety.fatalities',
    unit: 'incidents',
    valueType: 'integer',
    emptyLabel: 'No fatalities field in current API',
  },
  {
    title: 'Female Representation',
    endpoint: '/dashboard/investor',
    valuePath: 'average_female_representation',
    unit: '%',
    valueType: 'percent',
    decimals: 1,
  },
  {
    title: 'Female Leadership Representation',
    endpoint: '/dashboard/investor',
    valuePath: 'diversity_safety.female_leadership_representation_percent',
    unit: '%',
    valueType: 'percent',
    decimals: 1,
    emptyLabel: 'No female leadership field in current API',
  },
  {
    title: 'Employee Headcount',
    endpoint: '/dashboard/investor',
    valuePath: 'workforce.total_employees',
    unit: 'employees',
    valueType: 'integer',
    emptyLabel: 'No headcount field in current API',
  },
]

const governanceMetrics = [
  {
    title: 'ESG Policy Adoption',
    endpoint: '/dashboard/investor',
    valuePath: 'governance_adoption_percent',
    unit: '%',
    valueType: 'percent',
    decimals: 1,
  },
  {
    title: 'Anti-Bribery Policy Coverage',
    endpoint: '/dashboard/investor',
    valuePath: 'governance_policy_coverage.anti_bribery_percent',
    unit: '%',
    valueType: 'percent',
    decimals: 1,
    emptyLabel: 'No anti-bribery coverage field in current API',
  },
  {
    title: 'Cybersecurity Policy Coverage',
    endpoint: '/dashboard/investor',
    valuePath: 'governance_policy_coverage.cybersecurity_percent',
    unit: '%',
    valueType: 'percent',
    decimals: 1,
    emptyLabel: 'No cybersecurity coverage field in current API',
  },
  {
    title: 'Board Oversight',
    endpoint: '/dashboard/investor',
    valuePath: 'governance_policy_coverage.board_oversight_percent',
    unit: '%',
    valueType: 'percent',
    decimals: 1,
    emptyLabel: 'No board oversight coverage field in current API',
  },
]

const reportingMetrics = [
  {
    title: 'EDCI Report',
    endpoint: '/lp/reports',
    valueType: 'status',
    unit: 'report status',
    selectValue: (payload) =>
      Array.isArray(payload?.available_reports) && payload.available_reports.includes('EDCI')
        ? 'Available'
        : 'Unavailable',
  },
  {
    title: 'SFDR PAI Report',
    endpoint: '/lp/reports',
    valueType: 'status',
    unit: 'report status',
    selectValue: (payload) =>
      Array.isArray(payload?.available_reports) && payload.available_reports.includes('SFDR')
        ? 'Available'
        : 'Unavailable',
  },
  {
    title: 'Year-on-Year Comparison',
    endpoint: '/lp/dashboard',
    valuePath: 'portfolio_scorecard.yoy_change_percent',
    unit: 'YoY %',
    valueType: 'percent',
    decimals: 1,
    selectTrend: yoyTrend,
  },
  {
    title: 'Asset Class Breakdown',
    endpoint: '/lp/dashboard',
    valueType: 'text',
    unit: 'asset classes',
    selectValue: (payload) => {
      const rows = payload?.impact_story?.comparison_rows
      if (!Array.isArray(rows) || !rows.length) return null
      return `${rows.length} classes`
    },
    emptyLabel: 'No asset-class breakdown in current API',
  },
]

export default function LPAnalyticsSections({ user }) {
  return (
    <>
      <AnalyticsSectionBlock title="Overview Section" user={user} metrics={overviewMetrics} />
      <AnalyticsSectionBlock title="Environmental Section" user={user} metrics={environmentalMetrics} />
      <AnalyticsSectionBlock title="Social Section" user={user} metrics={socialMetrics} />
      <AnalyticsSectionBlock title="Governance Section" user={user} metrics={governanceMetrics} />
      <AnalyticsSectionBlock title="Reporting Section" user={user} metrics={reportingMetrics} />
    </>
  )
}
