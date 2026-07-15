import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import DataTable from '../components/DataTable'
import ExecutivePageHeader from '../components/ExecutivePageHeader'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import SectionLoadState from '../components/SectionLoadState'
import useDashboardData from '../hooks/useDashboardData'
import useNarrativeSummary from '../hooks/useNarrativeSummary'
import { API_BASE_URL } from '../lib/api'

const investorTabs = ['Climate', 'People & Governance', 'Data Quality', 'Frameworks', 'Benchmarking']

const funnelColors = {
  'Not Started': '#ef4444',
  'In Progress': '#f59e0b',
  Submitted: '#0ea5e9',
  'Under Review': '#8b5cf6',
  Approved: '#10b981',
  Rejected: '#f97316',
  'Resubmission Requested': '#dc2626',
}

function toNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export default function InvestorAnalyticsPage() {
  const { user } = useOutletContext()
  const { summary, loading, error, retrySection, sections, isRefreshing } = useDashboardData(user)
  const narrative = useNarrativeSummary({ user, audience: 'lp', tone: 'board-ready', enabled: Boolean(user) })
  const [activeTab, setActiveTab] = useState(investorTabs[0])
  const [qualityDetail, setQualityDetail] = useState(null)
  const [frameworkDetail, setFrameworkDetail] = useState(null)
  const [detailError, setDetailError] = useState('')
  const analytics = summary || {}

  useEffect(() => {
    const controller = new AbortController()
    const headers = { 'x-user-role': user?.role || '', 'x-user-email': user?.email || '' }
    setDetailError('')
    Promise.all([
      fetch(`${API_BASE_URL}/analytics/data-quality`, { headers, signal: controller.signal }),
      fetch(`${API_BASE_URL}/analytics/framework-mapping`, { headers, signal: controller.signal }),
    ]).then(async ([qualityResponse, frameworkResponse]) => {
      if (!qualityResponse.ok || !frameworkResponse.ok) throw new Error('Unable to load detailed investor analytics.')
      const [qualityPayload, frameworkPayload] = await Promise.all([qualityResponse.json(), frameworkResponse.json()])
      setQualityDetail(qualityPayload)
      setFrameworkDetail(frameworkPayload)
    }).catch((requestError) => {
      if (requestError.name !== 'AbortError') setDetailError(requestError.message)
    })
    return () => controller.abort()
  }, [user?.email, user?.role])

  const {
    coveragePercent,
    emissionsTrend,
    emissionsMix,
    scoreBreakdownData,
    submissionFunnelData,
    resourceData,
    socialData,
    qualityData,
    performerRows,
    underperformingSectors,
  } = useMemo(() => {
    const totalCompanies = toNumber(analytics.total_companies)
    const reportingCompanies = toNumber(analytics.reporting_companies)
    const coverage = totalCompanies > 0 ? (reportingCompanies / totalCompanies) * 100 : 0

    const totals = analytics.emissions_totals || {}
    const scoreBreakdown = analytics.score_breakdown || {}
    const resourceTotals = analytics.resource_totals || {}
    const diversitySafety = analytics.diversity_safety || {}
    const quality = analytics.data_quality || {}
    const funnel = analytics.submission_funnel || {}

    const topRows = (analytics.top_performers || []).map((item) => ({
      id: `top-${item.company_name}`,
      bucket: 'Top',
      company: item.company_name,
      sector: item.sector,
      score: Number(item.esg_score || 0),
    }))
    const bottomRows = (analytics.bottom_performers || []).map((item) => ({
      id: `bottom-${item.company_name}`,
      bucket: 'Watch',
      company: item.company_name,
      sector: item.sector,
      score: Number(item.esg_score || 0),
    }))

    return {
      coveragePercent: Number(coverage.toFixed(1)),
      emissionsTrend: (analytics.emissions_trend || []).map((point) => ({
        period: point.period,
        total_emissions: toNumber(point.total_emissions),
      })),
      emissionsMix: [
        { name: 'Scope 1', value: toNumber(totals.scope_1), color: '#0f766e' },
        { name: 'Scope 2', value: toNumber(totals.scope_2), color: '#0284c7' },
        { name: 'Scope 3', value: toNumber(totals.scope_3), color: '#f97316' },
      ],
      scoreBreakdownData: [
        { name: 'Environmental', value: toNumber(scoreBreakdown.E), color: '#16a34a' },
        { name: 'Social', value: toNumber(scoreBreakdown.S), color: '#0ea5e9' },
        { name: 'Governance', value: toNumber(scoreBreakdown.G), color: '#1d4ed8' },
      ],
      submissionFunnelData: Object.keys(funnelColors).map((key) => ({
        name: key,
        value: toNumber(funnel[key]),
        color: funnelColors[key],
      })),
      resourceData: [
        { metric: 'Energy', value: toNumber(resourceTotals.energy) },
        { metric: 'Water', value: toNumber(resourceTotals.water) },
        { metric: 'Waste', value: toNumber(resourceTotals.waste) },
      ],
      socialData: [
        { metric: 'Female Representation %', value: toNumber(diversitySafety.female_representation_percent) },
        { metric: 'Avg TRIFR', value: toNumber(diversitySafety.trifr) },
        { metric: 'High Variance Flags', value: toNumber(diversitySafety.high_variance_flags) },
      ],
      qualityData: [
        { metric: 'Completeness', score: toNumber(quality.completeness) },
        { metric: 'Accuracy', score: toNumber(quality.accuracy) },
        { metric: 'Confidence', score: toNumber(quality.confidence) },
      ],
      performerRows: [...topRows, ...bottomRows].sort((left, right) => right.score - left.score),
      underperformingSectors: (analytics.underperforming_sectors || []).filter(Boolean),
    }
  }, [analytics])

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="Investor Analytics" subtitle="Loading portfolio analytics...">
          <p>Loading data from backend.</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="Investor Analytics" subtitle="Live data unavailable">
          <SectionLoadState error={error} onRetry={() => retrySection('dashboard')} />
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <ExecutivePageHeader
        eyebrow="Investor analytics"
        title="Portfolio performance analytics"
        description="Compare verified portfolio indicators, historical emissions, ESG pillars, reporting quality, and performance outliers."
        meta={[
          { label: 'Coverage', value: `${coveragePercent}%` },
          { label: 'Companies', value: toNumber(analytics.total_companies) },
          { label: 'Historical periods', value: emissionsTrend.length },
        ]}
      />

      <SectionLoadState
        loading={isRefreshing}
        error={sections.dashboard.error}
        cached={Boolean(summary)}
        loadingMessage="Refreshing investor analytics..."
        onRetry={() => retrySection('dashboard')}
      />

      <section className="executive-kpi-grid" aria-label="Investor analytics metrics">
        <KpiCard title="Portfolio ESG Score" value={`${toNumber(analytics.portfolio_esg_score).toFixed(1)}/100`} />
        <KpiCard title="Reporting Coverage" value={`${coveragePercent}%`} trendLabel={`${toNumber(analytics.reporting_companies)}/${toNumber(analytics.total_companies)} companies`} />
        <KpiCard title="Total Emissions" value={`${toNumber(analytics.emissions_totals?.total).toLocaleString()} tCO2e`} />
        <KpiCard title="Avg Emissions / Company" value={`${toNumber(analytics.average_ghg_emissions).toLocaleString()} tCO2e`} />
        <KpiCard title="Governance Adoption" value={`${toNumber(analytics.governance_adoption_percent).toFixed(1)}%`} />
        <KpiCard title="Female Representation" value={`${toNumber(analytics.average_female_representation).toFixed(1)}%`} />
      </section>

      <SectionCard title="AI Analytics Narrative" subtitle="Detailed portfolio interpretation generated from live analytics">
        <SectionLoadState
          loading={narrative.loading}
          error={narrative.error}
          cached={Boolean(narrative.data)}
          loadingMessage="Generating analytics narrative..."
          onRetry={narrative.refresh}
        />
        {narrative.data ? (
          <>
            {narrative.data.fallback_used ? (
              <span className="fallback-badge">Live AI unavailable — showing calculated summary</span>
            ) : null}
            <h4>{narrative.data.headline || 'Portfolio Analytics Summary'}</h4>
            <p>{narrative.data.summary || 'No narrative summary available.'}</p>
          </>
        ) : null}
      </SectionCard>

      <nav className="analytics-view-tabs" aria-label="Investor analytics topics">
        {investorTabs.map((tab) => (
          <button
            key={tab}
            type="button"
            className={tab === activeTab ? 'active' : ''}
            aria-pressed={tab === activeTab}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </nav>

      {detailError && ['Data Quality', 'Frameworks'].includes(activeTab) ? <p className="action-message" role="alert">{detailError}</p> : null}

      <section className="two-col-grid">
        <SectionCard title="Emissions Trend" subtitle="Portfolio total emissions over recent periods" hidden={activeTab !== 'Climate'}>
          {emissionsTrend.length ? <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={emissionsTrend}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="total_emissions" stroke="#0f766e" strokeWidth={3} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div> : (
            <div className="analytics-empty-scope" role="status">
              <strong>No historical reporting periods yet</strong>
              <p>The trend will appear after submissions include reporting years.</p>
            </div>
          )}
        </SectionCard>

        <SectionCard title="Emissions Mix" subtitle="Scope distribution across portfolio" hidden={activeTab !== 'Climate'}>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie data={emissionsMix} dataKey="value" nameKey="name" innerRadius={68} outerRadius={112}>
                  {emissionsMix.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </section>

      <section className="two-col-grid">
        <SectionCard title="E / S / G Score Split" subtitle="Portfolio score composition" hidden={activeTab !== 'People & Governance'}>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie data={scoreBreakdownData} dataKey="value" nameKey="name" innerRadius={68} outerRadius={112}>
                  {scoreBreakdownData.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Submission Funnel" subtitle="Current reporting lifecycle distribution" hidden={activeTab !== 'Data Quality'}>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie data={submissionFunnelData} dataKey="value" nameKey="name" innerRadius={68} outerRadius={112}>
                  {submissionFunnelData.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </section>

      <section className="two-col-grid">
        <SectionCard title="Resource Analytics" subtitle="Energy, water, and waste totals" hidden={activeTab !== 'Climate'}>
          <div className="metric-unit-grid">
            {resourceData.map((item) => {
              const unit = item.metric === 'Energy' ? 'MWh' : item.metric === 'Water' ? 'm³' : 'tonnes'
              return <KpiCard key={item.metric} title={item.metric} value={`${item.value.toLocaleString()} ${unit}`} />
            })}
          </div>
        </SectionCard>

        <SectionCard title="Data Quality Index" subtitle="Completeness, accuracy, and confidence" hidden={activeTab !== 'Data Quality'}>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={qualityData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="metric" />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Bar dataKey="score" fill="#0f766e" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </section>

      <section className="two-col-grid">
        <SectionCard title="Social & Safety Indicators" subtitle="Portfolio averages and anomaly pressure" hidden={activeTab !== 'People & Governance'}>
          <div className="metric-unit-grid">
            {socialData.map((item) => {
              const unit = item.metric.includes('%') ? '%' : item.metric.includes('TRIFR') ? 'TRIFR' : 'flags'
              return <KpiCard key={item.metric} title={item.metric.replace(' %', '')} value={`${item.value.toLocaleString()} ${unit}`} />
            })}
          </div>
        </SectionCard>

        <SectionCard title="Underperforming Sectors" subtitle="Lowest-scoring sectors from portfolio benchmark" hidden={activeTab !== 'Benchmarking'}>
          {underperformingSectors.length ? (
            <ul className="mini-legend">
              {underperformingSectors.map((sector) => (
                <li key={sector}>
                  <span style={{ background: '#f97316' }} /> {sector}
                </li>
              ))}
            </ul>
          ) : (
            <p>No sector underperformance markers were returned.</p>
          )}
        </SectionCard>
      </section>

      <SectionCard title="Top & Watchlist Companies" subtitle="Highest and lowest ESG scores in the portfolio" hidden={activeTab !== 'Benchmarking'}>
        <DataTable
          columns={[
            { key: 'bucket', label: 'Bucket', sortable: true },
            { key: 'company', label: 'Company', sortable: true },
            { key: 'sector', label: 'Sector', sortable: true },
            { key: 'score', label: 'ESG Score', sortable: true },
          ]}
          rows={performerRows}
          pageSize={8}
          emptyMessage="No performer data available."
        />
      </SectionCard>

      <section className="space-y-4" hidden={activeTab !== 'Data Quality'}>
        <section className="executive-kpi-grid">
          <KpiCard title="Quality Index" value={`${toNumber(qualityDetail?.quality_index).toFixed(1)}/100`} trendLabel="weighted portfolio quality" />
          <KpiCard title="Completeness" value={`${toNumber(qualityDetail?.completeness).toFixed(1)}%`} trendLabel="required metrics" />
          <KpiCard title="Measured Confidence" value={`${toNumber(qualityDetail?.measured_confidence).toFixed(1)}%`} trendLabel="measured values" />
          <KpiCard title="Evidence Coverage" value={`${toNumber(qualityDetail?.evidence_coverage).toFixed(1)}%`} trendLabel="required attachments" />
          <KpiCard title="Open Flags" value={toNumber(qualityDetail?.open_flags)} trendLabel="validation findings" tone="amber" />
          <KpiCard title="At-risk Companies" value={toNumber(qualityDetail?.at_risk_companies)} trendLabel="quality intervention" tone="rose" />
        </section>
        <DataTable
          columns={[
            { key: 'company', label: 'Company', sortable: true }, { key: 'sector', label: 'Sector', sortable: true },
            { key: 'quality_score', label: 'Quality', sortable: true, render: (row) => `${row.quality_score.toFixed(1)}/100` },
            { key: 'completeness', label: 'Complete', sortable: true, render: (row) => `${row.completeness.toFixed(1)}%` },
            { key: 'measured_confidence', label: 'Measured', sortable: true, render: (row) => `${row.measured_confidence.toFixed(1)}%` },
            { key: 'evidence_coverage', label: 'Evidence', sortable: true, render: (row) => `${row.evidence_coverage.toFixed(1)}%` },
            { key: 'validation_flags', label: 'Flags', sortable: true }, { key: 'priority', label: 'Priority', sortable: true },
          ]}
          rows={qualityDetail?.rows || []}
          pageSize={10}
          emptyMessage="No detailed data-quality records are available."
        />
      </section>

      <section className="space-y-4" hidden={activeTab !== 'Frameworks'}>
        <section className="executive-kpi-grid">
          {(frameworkDetail?.frameworks || []).map((framework) => (
            <KpiCard key={framework.framework} title={framework.framework} value={`${framework.coverage_percent.toFixed(1)}%`} trendLabel={`${framework.complete_disclosures}/${framework.mapped_disclosures} disclosures complete`} />
          ))}
        </section>
        <DataTable
          columns={[
            { key: 'framework', label: 'Framework', sortable: true }, { key: 'reference', label: 'Reference', sortable: true },
            { key: 'disclosure', label: 'Disclosure', sortable: true },
            { key: 'companies_reported', label: 'Reported', sortable: true, render: (row) => `${row.companies_reported}/${row.companies_expected}` },
            { key: 'coverage_percent', label: 'Coverage', sortable: true, render: (row) => `${row.coverage_percent.toFixed(1)}%` },
            { key: 'status', label: 'Status', sortable: true },
          ]}
          rows={frameworkDetail?.disclosures || []}
          pageSize={10}
          emptyMessage="No framework coverage records are available."
        />
      </section>

    </div>
  )
}
