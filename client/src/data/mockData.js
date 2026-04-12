const STATUS_FLOW = ['Not Started', 'In Progress', 'Submitted', 'Approved', 'Rejected']
const RISK_LEVELS = ['Low', 'Medium', 'High']
const SECTORS = ['Industrials', 'Energy', 'Healthcare', 'Consumer', 'Technology', 'Real Estate']
const GEOGRAPHIES = ['North America', 'Europe', 'APAC', 'LATAM']

const companyPrefixes = [
  'Aster',
  'Blue Peak',
  'Cedar',
  'Delta Ridge',
  'Evergreen',
  'Forge',
  'Granite',
  'Harbor',
  'Ion',
  'Juniper',
  'Kite',
  'Lumen',
  'Mosaic',
  'Northstar',
  'Orion',
  'Pioneer',
  'Quartz',
  'Ridgeway',
  'Summit',
  'Terra',
]

function addDays(base, days) {
  const copy = new Date(base)
  copy.setDate(copy.getDate() + days)
  return copy
}

function formatDate(value) {
  return value.toISOString().slice(0, 10)
}

const today = new Date()

export const submissionRows = Array.from({ length: 84 }, (_, index) => {
  const status = STATUS_FLOW[index % STATUS_FLOW.length]
  const risk = RISK_LEVELS[index % RISK_LEVELS.length]
  const progress = status === 'Approved'
    ? 100
    : status === 'Submitted'
      ? 92
      : status === 'In Progress'
        ? 40 + ((index * 7) % 40)
        : status === 'Rejected'
          ? 85
          : 8 + (index % 16)

  const deadlineOffset = status === 'Approved'
    ? 20 + (index % 40)
    : status === 'Rejected'
      ? -8 + (index % 16)
      : -6 + (index % 28)

  const prefix = companyPrefixes[index % companyPrefixes.length]
  return {
    id: index + 1,
    companyName: `${prefix} Holdings ${String(index + 1).padStart(3, '0')}`,
    status,
    progress,
    deadline: formatDate(addDays(today, deadlineOffset)),
    esgScore: 48 + ((index * 3) % 47),
    risk,
    sector: SECTORS[index % SECTORS.length],
    geography: GEOGRAPHIES[index % GEOGRAPHIES.length],
  }
})

export const reviewMetricRows = [
  { metric: 'Scope 1 Emissions (tCO2e)', value: 1360, previousYear: 1480, validation: 'Pass', confidence: 'Measured', comment: 'Fuel optimization in operations.' },
  { metric: 'Scope 2 Emissions (tCO2e)', value: 920, previousYear: 990, validation: 'Warning', confidence: 'Estimated', comment: 'Waiting utility invoice reconciliation.' },
  { metric: 'Scope 3 Emissions (tCO2e)', value: 4120, previousYear: 4060, validation: 'Warning', confidence: 'Estimated', comment: 'Supplier data still incomplete.' },
  { metric: 'TRIFR', value: 1.2, previousYear: 1.6, validation: 'Pass', confidence: 'Measured', comment: 'Improved contractor safety onboarding.' },
  { metric: 'Female Leadership Representation (%)', value: 37, previousYear: 33, validation: 'Pass', confidence: 'Measured', comment: 'Leadership hiring targets achieved.' },
  { metric: 'Cybersecurity Policy In Place', value: 'Yes', previousYear: 'Yes', validation: 'Pass', confidence: 'NA', comment: 'Policy refreshed in Q1.' },
  { metric: 'Anti-Bribery Training Completion (%)', value: 84, previousYear: 72, validation: 'Fail', confidence: 'Estimated', comment: 'Regional rollout still pending.' },
]

export const overviewKpis = {
  esgScore: 76,
  esgTrend: 4.8,
  totalCompanies: 512,
  submittedPercent: 82,
  approvedCount: 319,
  daysToDeadline: 11,
}

export const esgTrendData = [
  { month: 'Jan', score: 66 },
  { month: 'Feb', score: 68 },
  { month: 'Mar', score: 69 },
  { month: 'Apr', score: 71 },
  { month: 'May', score: 72 },
  { month: 'Jun', score: 74 },
  { month: 'Jul', score: 73 },
  { month: 'Aug', score: 74 },
  { month: 'Sep', score: 75 },
  { month: 'Oct', score: 76 },
  { month: 'Nov', score: 77 },
  { month: 'Dec', score: 76 },
]

export const submissionBreakdownData = [
  { name: 'Not Started', value: 74, color: '#ef4444' },
  { name: 'In Progress', value: 118, color: '#f59e0b' },
  { name: 'Submitted', value: 89, color: '#0ea5e9' },
  { name: 'Approved', value: 203, color: '#10b981' },
  { name: 'Rejected', value: 28, color: '#f97316' },
]

export const emissionsTrendData = [
  { month: 'Jan', scope1: 1400, scope2: 970, scope3: 4200 },
  { month: 'Feb', scope1: 1360, scope2: 940, scope3: 4150 },
  { month: 'Mar', scope1: 1320, scope2: 920, scope3: 4100 },
  { month: 'Apr', scope1: 1290, scope2: 910, scope3: 4060 },
  { month: 'May', scope1: 1260, scope2: 890, scope3: 4010 },
  { month: 'Jun', scope1: 1240, scope2: 870, scope3: 3980 },
]

export const diversityData = [
  { label: 'Women Workforce', value: 43 },
  { label: 'Women Leadership', value: 37 },
  { label: 'Independent Board', value: 54 },
  { label: 'Inclusion Training', value: 81 },
]

export const analyticsTabs = ['Environmental', 'Social', 'Governance', 'Benchmarking']

export const energyMixData = [
  { source: 'Renewable', value: 48 },
  { source: 'Grid', value: 34 },
  { source: 'Gas', value: 18 },
]

export const trifrTrendData = [
  { year: '2021', trifr: 2.4 },
  { year: '2022', trifr: 2.1 },
  { year: '2023', trifr: 1.8 },
  { year: '2024', trifr: 1.6 },
  { year: '2025', trifr: 1.3 },
]

export const diversityPieData = [
  { name: 'Women', value: 43, color: '#10b981' },
  { name: 'Men', value: 54, color: '#0ea5e9' },
  { name: 'Non-binary / Prefer not', value: 3, color: '#c084fc' },
]

export const governancePolicyData = [
  { policy: 'ESG Policy', adoption: 92 },
  { policy: 'Cybersecurity', adoption: 88 },
  { policy: 'Whistleblower', adoption: 76 },
  { policy: 'Anti-bribery', adoption: 81 },
]

export const benchmarkData = [
  { category: 'Emissions Intensity', portfolio: 64, peer: 58 },
  { category: 'Safety', portfolio: 74, peer: 66 },
  { category: 'Gender Diversity', portfolio: 69, peer: 61 },
  { category: 'Governance Maturity', portfolio: 81, peer: 73 },
]

export const alertCards = [
  { title: 'Missing ESG Policies', value: 38, severity: 'critical' },
  { title: 'High Emissions Variance', value: 54, severity: 'warning' },
  { title: 'Overdue Submissions', value: 27, severity: 'critical' },
]

export const riskIssueRows = submissionRows.slice(0, 28).map((item, index) => ({
  id: index + 1,
  company: item.companyName,
  issue: index % 3 === 0 ? 'Missing policy reference' : index % 3 === 1 ? 'Emissions variance > 15%' : 'Submission overdue',
  severity: index % 3 === 0 ? 'Medium' : index % 3 === 1 ? 'High' : 'Critical',
}))

export const actionPlanRows = submissionRows.slice(8, 52).map((item, index) => ({
  id: index + 1,
  company: item.companyName,
  pillar: index % 3 === 0 ? 'Environmental' : index % 3 === 1 ? 'Social' : 'Governance',
  action: index % 2 === 0 ? 'Deploy supplier data collection workflow' : 'Update board ESG oversight policy',
  owner: index % 2 === 0 ? 'Portfolio ESG Lead' : 'Company CFO',
  deadline: formatDate(addDays(today, -3 + (index % 40))),
  status: index % 4 === 0 ? 'Not Started' : index % 4 === 1 ? 'In Progress' : index % 4 === 2 ? 'Blocked' : 'Complete',
}))

export const reportFrameworks = ['EDCI', 'GRI', 'TCFD', 'SFDR', 'PRI']

export const adminSettingsTabs = ['Users', 'Templates', 'Validation Rules', 'Data Collection Cycles', 'Audit Logs']

export const usersData = [
  { id: 1, name: 'Admin Alice', role: 'Admin', email: 'admin@example.com', status: 'Active' },
  { id: 2, name: 'Investor Bob', role: 'Investor', email: 'investor@example.com', status: 'Active' },
  { id: 3, name: 'Client Clara', role: 'Client', email: 'client@example.com', status: 'Active' },
  { id: 4, name: 'Portfolio Contact', role: 'Portfolio', email: 'company@example.com', status: 'Invited' },
]

export const templatesData = [
  { id: 1, name: 'Private Equity Core', version: 'v3.1', updatedBy: 'Admin Alice' },
  { id: 2, name: 'Infrastructure Deep Dive', version: 'v2.4', updatedBy: 'ESG Ops' },
  { id: 3, name: 'Real Estate Essentials', version: 'v4.0', updatedBy: 'Investor Bob' },
]

export const validationRulesData = [
  { id: 1, rule: 'Scope 1 cannot be negative', severity: 'Critical', enabled: 'Yes' },
  { id: 2, rule: 'TRIFR should be < 5', severity: 'Warning', enabled: 'Yes' },
  { id: 3, rule: 'Female leadership target >= 30%', severity: 'Warning', enabled: 'Yes' },
]

export const cyclesData = [
  { id: 1, cycle: 'FY2026', openDate: '2026-03-01', deadline: '2026-06-30', status: 'Active' },
  { id: 2, cycle: 'FY2025', openDate: '2025-03-01', deadline: '2025-06-30', status: 'Closed' },
]

export const auditLogsData = [
  { id: 1, event: 'Submission Approved', actor: 'Admin Alice', timestamp: '2026-04-11 09:22' },
  { id: 2, event: 'Validation Rule Updated', actor: 'ESG Ops', timestamp: '2026-04-10 17:45' },
  { id: 3, event: 'New User Added', actor: 'Admin Alice', timestamp: '2026-04-09 11:08' },
]
