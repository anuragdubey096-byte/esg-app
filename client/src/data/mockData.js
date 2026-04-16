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
  { id: 1, name: 'PE Debt / Direct Lending Core', version: 'v3.1', updatedBy: 'Admin Alice' },
  { id: 2, name: 'Sustainability-Linked Loan (SLL) Metrics', version: 'v2.4', updatedBy: 'ESG Ops' },
  { id: 3, name: 'Mezzanine Finance Essentials', version: 'v4.0', updatedBy: 'Investor Bob' },
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

// ==========================================
// LP (LIMITED PARTNER) MOCK DATA
// ==========================================

export const lpPortfolioScorecard = {
  overall_esg_score: 76.5,
  overall_esg_score_previous: 72.1,
  yoy_change_percent: 6.1,
  three_year_trend: [68.2, 70.8, 72.1, 76.5],
  pillars: [
    {
      name: 'E',
      current_score: 78.3,
      previous_score: 73.2,
      yoy_change: 6.97,
      trend_sparkline: [65.2, 68.4, 70.1, 73.2, 78.3],
    },
    {
      name: 'S',
      current_score: 74.1,
      previous_score: 71.6,
      yoy_change: 3.49,
      trend_sparkline: [68.5, 69.2, 70.3, 71.6, 74.1],
    },
    {
      name: 'G',
      current_score: 77.0,
      previous_score: 72.4,
      yoy_change: 6.35,
      trend_sparkline: [66.1, 68.9, 70.1, 72.4, 77.0],
    },
  ],
}

export const lpPortfolioCompletion = {
  total_companies: 512,
  companies_with_approved_submission: 419,
  completion_percent: 81.83,
  last_updated: '2026-04-12 14:23 UTC',
}

export const lpKeyMetrics = [
  {
    metric_name: 'Scope 1+2+3 Emissions',
    current_value: '2,847,392',
    unit: 'tCO2e',
    trend_percent: -3.2,
    trend_direction: 'down',
    last_updated: '2026-04-12',
  },
  {
    metric_name: 'Emissions Intensity',
    current_value: '4.2',
    unit: 'tCO2e/$M Revenue',
    trend_percent: -2.1,
    trend_direction: 'down',
    last_updated: '2026-04-12',
  },
  {
    metric_name: 'Total Employees',
    current_value: '847,521',
    unit: 'FTE',
    trend_percent: 2.4,
    trend_direction: 'up',
    last_updated: '2026-04-12',
  },
  {
    metric_name: 'Female Representation',
    current_value: '43.2',
    unit: '%',
    trend_percent: 1.8,
    trend_direction: 'up',
    last_updated: '2026-04-12',
  },
  {
    metric_name: 'Total Fatalities',
    current_value: '12',
    unit: 'count',
    trend_percent: -25.0,
    trend_direction: 'down',
    last_updated: '2026-04-12',
  },
  {
    metric_name: 'Companies with ESG Policy',
    current_value: '467',
    unit: '% of portfolio',
    trend_percent: 4.1,
    trend_direction: 'up',
    last_updated: '2026-04-12',
  },
  {
    metric_name: 'TRIFR (Safety)',
    current_value: '1.32',
    unit: 'rate',
    trend_percent: -17.6,
    trend_direction: 'down',
    last_updated: '2026-04-12',
  },
  {
    metric_name: 'Board Diversity',
    current_value: '38.1',
    unit: '%',
    trend_percent: 3.2,
    trend_direction: 'up',
    last_updated: '2026-04-12',
  },
]

export const lpEmissionsTrendData = [
  { period: '2022', scope_1: 1850000, scope_2: 620000, scope_3: 4120000 },
  { period: '2023', scope_1: 1780000, scope_2: 598000, scope_3: 4080000 },
  { period: '2024', scope_1: 1650000, scope_2: 550000, scope_3: 3890000 },
  { period: 'YTD 2026', scope_1: 1420000, scope_2: 480000, scope_3: 3520000 },
]

export const lpDiversityMetrics = [
  {
    metric_name: 'Female Workforce',
    percentage: 43.2,
    previous_year: 41.4,
    trend: 'up',
  },
  {
    metric_name: 'Female Leadership',
    percentage: 38.7,
    previous_year: 36.9,
    trend: 'up',
  },
  {
    metric_name: 'Board Independence',
    percentage: 68.4,
    previous_year: 65.1,
    trend: 'up',
  },
  {
    metric_name: 'Workforce from Underrepresented Groups',
    percentage: 32.1,
    previous_year: 30.2,
    trend: 'up',
  },
]

export const lpPolicyAdoption = [
  {
    policy_name: 'ESG Policy in Place',
    adoption_percentage: 91.2,
    companies_with_policy: 467,
    total_companies: 512,
  },
  {
    policy_name: 'WHS / Health & Safety Policy',
    adoption_percentage: 94.5,
    companies_with_policy: 484,
    total_companies: 512,
  },
  {
    policy_name: 'Cybersecurity Policy',
    adoption_percentage: 87.3,
    companies_with_policy: 447,
    total_companies: 512,
  },
  {
    policy_name: 'Anti-Bribery / Anti-Corruption',
    adoption_percentage: 89.6,
    companies_with_policy: 459,
    total_companies: 512,
  },
]

export const lpActionPlanStatus = {
  in_progress: 234,
  completed: 187,
}

export const lpPortfolioCompanies = [
  {
    id: 1,
    name: 'Carbon Ridge Energy',
    sector: 'Energy',
    asset_class: 'Private Equity',
    geography: 'North America',
    approval_status: 'Approved',
    esg_score: 82.3,
    e_score: 85.2,
    s_score: 79.4,
    g_score: 82.1,
  },
  {
    id: 2,
    name: 'Summit Healthcare Solutions',
    sector: 'Healthcare',
    asset_class: 'Private Equity',
    geography: 'Europe',
    approval_status: 'Approved',
    esg_score: 78.1,
    e_score: 74.2,
    s_score: 81.3,
    g_score: 78.7,
  },
  {
    id: 3,
    name: 'Urban Horizons Real Estate',
    sector: 'Real Estate',
    asset_class: 'Real Estate',
    geography: 'North America',
    approval_status: 'Approved',
    esg_score: 75.4,
    e_score: 79.1,
    s_score: 71.2,
    g_score: 75.9,
  },
  {
    id: 4,
    name: 'Nexus Capital Fund',
    sector: 'Financial Services',
    asset_class: 'Debt',
    geography: 'Europe',
    approval_status: 'Approved',
    esg_score: 71.2,
    e_score: 68.3,
    s_score: 73.4,
    g_score: 72.0,
  },
  {
    id: 5,
    name: 'Forge Industrial Group',
    sector: 'Industrials',
    asset_class: 'Private Equity',
    geography: 'North America',
    approval_status: 'Pending',
    esg_score: 68.9,
    e_score: 71.2,
    s_score: 66.1,
    g_score: 68.4,
  },
]

export const lpEnvironmentalMetrics = {
  scope_1_emissions: [
    { period: '2022', value: 1850, trend: 0 },
    { period: '2023', value: 1780, trend: -3.8 },
    { period: '2024', value: 1650, trend: -7.3 },
    { period: 'YTD 2026', value: 1420, trend: -13.9 },
  ],
  scope_2_emissions: [
    { period: '2022', value: 620, trend: 0 },
    { period: '2023', value: 598, trend: -3.5 },
    { period: '2024', value: 550, trend: -8.0 },
    { period: 'YTD 2026', value: 480, trend: -12.7 },
  ],
  scope_3_emissions: [
    { period: '2022', value: 4120, trend: 0 },
    { period: '2023', value: 4080, trend: -1.0 },
    { period: '2024', value: 3890, trend: -4.7 },
    { period: 'YTD 2026', value: 3520, trend: -9.5 },
  ],
  energy_total: [
    { period: '2022', value: 2.4, trend: 0 },
    { period: '2023', value: 2.3, trend: -4.2 },
    { period: '2024', value: 2.1, trend: -8.7 },
    { period: 'YTD 2026', value: 1.9, trend: -9.5 },
  ],
  energy_renewable: [
    { period: '2022', value: 28.1, trend: 0 },
    { period: '2023', value: 32.5, trend: 15.7 },
    { period: '2024', value: 38.2, trend: 17.5 },
    { period: 'YTD 2026', value: 42.8, trend: 12.0 },
  ],
  water_usage: [
    { period: '2022', value: 12400, trend: 0 },
    { period: '2023', value: 12100, trend: -2.4 },
    { period: '2024', value: 11200, trend: -7.4 },
    { period: 'YTD 2026', value: 10800, trend: -3.6 },
  ],
  water_recycled: [
    { period: '2022', value: 3100, trend: 0 },
    { period: '2023', value: 3400, trend: 9.7 },
    { period: '2024', value: 3890, trend: 14.4 },
    { period: 'YTD 2026', value: 4200, trend: 8.0 },
  ],
  waste_generated: [
    { period: '2022', value: 8900, trend: 0 },
    { period: '2023', value: 8600, trend: -3.4 },
    { period: '2024', value: 8100, trend: -5.8 },
    { period: 'YTD 2026', value: 7200, trend: -11.1 },
  ],
  waste_diverted: [
    { period: '2022', value: 5340, trend: 0 },
    { period: '2023', value: 6010, trend: 12.5 },
    { period: '2024', value: 6890, trend: 14.6 },
    { period: 'YTD 2026', value: 7440, trend: 8.0 },
  ],
}

export const lpSocialMetrics = {
  trifr: [
    { period: '2022', value: 1.6, trend: 0 },
    { period: '2023', value: 1.48, trend: -7.5 },
    { period: '2024', value: 1.32, trend: -10.8 },
    { period: 'YTD 2026', value: 1.18, trend: -10.6 },
  ],
  fatalities: [
    { period: '2022', value: 16, trend: 0 },
    { period: '2023', value: 14, trend: -12.5 },
    { period: '2024', value: 14, trend: 0 },
    { period: 'YTD 2026', value: 12, trend: -14.3 },
  ],
  total_employees: [
    { period: '2022', value: 810000, trend: 0 },
    { period: '2023', value: 825000, trend: 1.85 },
    { period: '2024', value: 838000, trend: 1.58 },
    { period: 'YTD 2026', value: 847521, trend: 1.14 },
  ],
  female_workforce_percent: [
    { period: '2022', value: 39.8, trend: 0 },
    { period: '2023', value: 41.4, trend: 4.02 },
    { period: '2024', value: 42.1, trend: 1.69 },
    { period: 'YTD 2026', value: 43.2, trend: 2.61 },
  ],
  female_leadership_percent: [
    { period: '2022', value: 34.1, trend: 0 },
    { period: '2023', value: 36.9, trend: 8.21 },
    { period: '2024', value: 37.8, trend: 2.44 },
    { period: 'YTD 2026', value: 38.7, trend: 2.38 },
  ],
  community_investment: [
    { period: '2022', value: 42800000, trend: 0 },
    { period: '2023', value: 48900000, trend: 14.25 },
    { period: '2024', value: 52400000, trend: 7.15 },
    { period: 'YTD 2026', value: 56200000, trend: 7.25 },
  ],
}

export const lpGovernanceMetrics = {
  esg_policy_compliance: 91.2,
  whs_policy_compliance: 94.5,
  cybersecurity_policy_compliance: 87.3,
  antibribery_policy_compliance: 89.6,
  board_esg_oversight: 76.4,
  cyber_incidents: [
    { period: '2022', value: 8 },
    { period: '2023', value: 6 },
    { period: '2024', value: 4 },
    { period: 'YTD 2026', value: 2 },
  ],
}

export const lpAssetClassBreakdown = [
  {
    asset_class: 'Private Equity',
    company_count: 256,
    avg_esg_score: 77.2,
    avg_emission_intensity: 4.1,
    avg_female_representation: 42.8,
  },
  {
    asset_class: 'Real Estate',
    company_count: 128,
    avg_esg_score: 74.8,
    avg_emission_intensity: 3.8,
    avg_female_representation: 44.1,
  },
  {
    asset_class: 'Debt',
    company_count: 85,
    avg_esg_score: 71.4,
    avg_emission_intensity: 4.5,
    avg_female_representation: 42.2,
  },
  {
    asset_class: 'Infrastructure',
    company_count: 43,
    avg_esg_score: 73.9,
    avg_emission_intensity: 5.2,
    avg_female_representation: 41.5,
  },
]

export const lpBenchmarkComparisons = [
  {
    metric_name: 'Overall ESG Score',
    portfolio_value: 76.5,
    benchmark_value: 71.2,
    status: 'above',
    industry: 'Multi-Sector Average',
  },
  {
    metric_name: 'Emissions Intensity',
    portfolio_value: 4.2,
    benchmark_value: 5.1,
    status: 'below',
    industry: 'Energy & Industrials Peer Group',
  },
  {
    metric_name: 'Female Representation',
    portfolio_value: 43.2,
    benchmark_value: 39.8,
    status: 'above',
    industry: 'Multi-Sector Average',
  },
  {
    metric_name: 'TRIFR (Safety)',
    portfolio_value: 1.18,
    benchmark_value: 1.45,
    status: 'below',
    industry: 'Manufacturing & Energy',
  },
  {
    metric_name: 'Policy Compliance',
    portfolio_value: 90.2,
    benchmark_value: 83.1,
    status: 'above',
    industry: 'Institutional Investment Peer Group',
  },
]

export const lpAvailableReports = [
  {
    report_name: 'Annual ESG Report FY2025',
    year: 2025,
    generated_date: '2026-03-15',
    format: 'PDF',
    download_url: '/reports/annual_esg_2025.pdf',
  },
  {
    report_name: 'EDCI Submission FY2025',
    year: 2025,
    generated_date: '2026-03-20',
    format: 'Excel',
    download_url: '/reports/edci_fy2025.xlsx',
  },
  {
    report_name: 'TCFD Climate Report FY2025',
    year: 2025,
    generated_date: '2026-03-18',
    format: 'PDF',
    download_url: '/reports/tcfd_fy2025.pdf',
  },
  {
    report_name: 'GRI Standards Report FY2025',
    year: 2025,
    generated_date: '2026-03-22',
    format: 'PDF',
    download_url: '/reports/gri_fy2025.pdf',
  },
  {
    report_name: 'SFDR PAI Report FY2025',
    year: 2025,
    generated_date: '2026-03-21',
    format: 'Excel',
    download_url: '/reports/sfdr_pai_fy2025.xlsx',
  },
  {
    report_name: 'PRI Annual Report FY2025',
    year: 2025,
    generated_date: '2026-03-17',
    format: 'PDF',
    download_url: '/reports/pri_fy2025.pdf',
  },
  {
    report_name: 'Annual ESG Report FY2024',
    year: 2024,
    generated_date: '2025-03-10',
    format: 'PDF',
    download_url: '/reports/annual_esg_2024.pdf',
  },
  {
    report_name: 'EDCI Submission FY2024',
    year: 2024,
    generated_date: '2025-03-12',
    format: 'Excel',
    download_url: '/reports/edci_fy2024.xlsx',
  },
]

export const lpHistoricalArchive = {
  2025: [
    {
      report_name: 'Annual ESG Report FY2025',
      year: 2025,
      generated_date: '2026-03-15',
      format: 'PDF',
      download_url: '/reports/annual_esg_2025.pdf',
    },
    {
      report_name: 'EDCI Submission FY2025',
      year: 2025,
      generated_date: '2026-03-20',
      format: 'Excel',
      download_url: '/reports/edci_fy2025.xlsx',
    },
  ],
  2024: [
    {
      report_name: 'Annual ESG Report FY2024',
      year: 2024,
      generated_date: '2025-03-10',
      format: 'PDF',
      download_url: '/reports/annual_esg_2024.pdf',
    },
    {
      report_name: 'EDCI Submission FY2024',
      year: 2024,
      generated_date: '2025-03-12',
      format: 'Excel',
      download_url: '/reports/edci_fy2024.xlsx',
    },
  ],
}
