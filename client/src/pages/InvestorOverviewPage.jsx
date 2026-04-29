import { useMemo } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import DataTable from '../components/DataTable'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import useDashboardData from '../hooks/useDashboardData'
import useNarrativeSummary from '../hooks/useNarrativeSummary'

const funnelColors = {
  'Not Started': '#ef4444',
  'In Progress': '#f59e0b',
  Submitted: '#0ea5e9',
  Approved: '#10b981',
  Rejected: '#f97316',
}

export default function InvestorOverviewPage() {
  const { user } = useOutletContext()
  const { summary, loading, error } = useDashboardData(user)
  const narrative = useNarrativeSummary({ user, audience: 'lp', tone: 'investor-ready', enabled: Boolean(user) })

  const analytics = summary || {}
  const scoreBreakdown = analytics.score_breakdown || { E: 0, S: 0, G: 0 }
  const emissionsTotals = analytics.emissions_totals || { scope_1: 0, scope_2: 0, scope_3: 0, total: 0 }
  const dataQuality = analytics.data_quality || { completeness: 0, accuracy: 0, confidence: 0 }

  const submissionFunnelData = useMemo(() => {
    const funnel = analytics.submission_funnel || {}
    return Object.keys(funnelColors).map((key) => ({
      name: key,
      value: Number(funnel[key] || 0),
      color: funnelColors[key],
    }))
  }, [analytics.submission_funnel])

  const topBottomRows = useMemo(() => {
    const topRows = (analytics.top_performers || []).map((item, index) => ({
      id: `top-${index}`,
      bucket: 'Top',
      company: item.company_name,
      sector: item.sector,
      score: Number(item.esg_score || 0).toFixed(1),
    }))
    const bottomRows = (analytics.bottom_performers || []).map((item, index) => ({
      id: `bottom-${index}`,
      bucket: 'Bottom',
      company: item.company_name,
      sector: item.sector,
      score: Number(item.esg_score || 0).toFixed(1),
    }))
    return [...topRows, ...bottomRows]
  }, [analytics.bottom_performers, analytics.top_performers])

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="Investor Portfolio Dashboard" subtitle="Loading portfolio analytics...">
          <p>Loading data from backend.</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="Investor Portfolio Dashboard" subtitle="Live data unavailable">
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <section className="kpi-grid">
        <KpiCard title="Portfolio ESG Score" value={`${Number(analytics.portfolio_esg_score || 0).toFixed(1)}/100`} />
        <KpiCard title="E / S / G" value={`${scoreBreakdown.E || 0} / ${scoreBreakdown.S || 0} / ${scoreBreakdown.G || 0}`} />
        <KpiCard
          title="Reporting Coverage"
          value={`${analytics.reporting_companies || 0}/${analytics.total_companies || 0}`}
          trendLabel="companies submitted"
        />
        <KpiCard title="Total Emissions" value={`${Number(emissionsTotals.total || 0).toLocaleString()} tCO2e`} />
        <KpiCard
          title="Governance Adoption"
          value={`${Number(analytics.governance_adoption_percent || 0).toFixed(1)}%`}
          trendLabel="portfolio policy coverage"
        />
      </section>

      <SectionCard title="AI Investor Summary" subtitle="OpenAI-generated narrative from current portfolio analytics">
        {narrative.loading ? <p>Generating summary...</p> : null}
        {narrative.error ? <p>{narrative.error}</p> : null}
        {!narrative.loading && !narrative.error && narrative.data ? (
          <>
            <h4>{narrative.data.headline || 'Portfolio ESG Narrative'}</h4>
            <p>{narrative.data.summary || 'No narrative summary available.'}</p>
          </>
        ) : null}
      </SectionCard>

      <section className="two-col-grid">
        <SectionCard title="Submission Funnel" subtitle="Portfolio reporting lifecycle">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={submissionFunnelData} dataKey="value" nameKey="name" innerRadius={62} outerRadius={108}>
                  {submissionFunnelData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Emissions Breakdown" subtitle="Scope 1, 2, and 3 totals">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={[
                  { name: 'Scope 1', value: Number(emissionsTotals.scope_1 || 0) },
                  { name: 'Scope 2', value: Number(emissionsTotals.scope_2 || 0) },
                  { name: 'Scope 3', value: Number(emissionsTotals.scope_3 || 0) },
                ]}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value" fill="#2563eb" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </section>

      <section className="two-col-grid">
        <SectionCard title="Data Quality Index" subtitle="Completeness, accuracy, and confidence">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={[
                  { metric: 'Completeness', score: Number(dataQuality.completeness || 0) },
                  { metric: 'Accuracy', score: Number(dataQuality.accuracy || 0) },
                  { metric: 'Confidence', score: Number(dataQuality.confidence || 0) },
                ]}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="metric" />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Bar dataKey="score" fill="#0f766e" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Top & Bottom Performers" subtitle="Portfolio companies ranked by ESG score">
          <DataTable
            columns={[
              { key: 'bucket', label: 'Bucket', sortable: true },
              { key: 'company', label: 'Company', sortable: true },
              { key: 'sector', label: 'Sector', sortable: true },
              { key: 'score', label: 'ESG Score', sortable: true },
            ]}
            rows={topBottomRows}
            pageSize={8}
            emptyMessage="No performance ranking data available."
          />
        </SectionCard>
      </section>
    </div>
  )
}
