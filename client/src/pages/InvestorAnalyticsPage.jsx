import { useMemo } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import ImpactStoryCard from '../components/ImpactStoryCard'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import { CHART_COLORS, STATUS_COLORS } from '../lib/foundation'
import useDashboardData from '../hooks/useDashboardData'

function formatTrend(value) {
  if (value == null) return 'n/a'
  return `${Number(value || 0).toFixed(1)}%`
}

export default function InvestorAnalyticsPage() {
  const { user } = useOutletContext()
  const { summary, loading, error } = useDashboardData(user)

  const analytics = summary || {}
  const scoreBreakdown = analytics.score_breakdown || { E: 0, S: 0, G: 0 }
  const emissionsTotals = analytics.emissions_totals || { scope_1: 0, scope_2: 0, scope_3: 0, total: 0 }
  const dataQuality = analytics.data_quality || { completeness: 0, accuracy: 0, confidence: 0 }
  const impactStory = analytics.impact_story || null

  const submissionFunnelData = useMemo(() => {
    const funnel = analytics.submission_funnel || {}
    return [
      { name: 'Not Started', value: Number(funnel['Not Started'] || 0), color: STATUS_COLORS['Not Started'] },
      { name: 'In Progress', value: Number(funnel['In Progress'] || 0), color: STATUS_COLORS['In Progress'] },
      { name: 'Submitted', value: Number(funnel.Submitted || 0), color: STATUS_COLORS.Submitted },
      { name: 'Approved', value: Number(funnel.Approved || 0), color: STATUS_COLORS.Approved },
      { name: 'Rejected', value: Number(funnel.Rejected || 0), color: STATUS_COLORS.Rejected },
    ]
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

  const heroMetrics = [
    { label: 'Portfolio ESG Score', value: `${Number(analytics.portfolio_esg_score || 0).toFixed(1)}/100`, hint: 'Backend portfolio average' },
    { label: 'Reporting Coverage', value: `${analytics.reporting_companies || 0}/${analytics.total_companies || 0}`, hint: 'Companies submitted' },
    { label: 'Governance Adoption', value: `${Number(analytics.governance_adoption_percent || 0).toFixed(1)}%`, hint: 'Policy coverage' },
  ]

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
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <section className="analytics-hero investor-hero">
        <div className="analytics-hero-copy">
          <p className="eyebrow">Investor Analytics</p>
          <h1>Portfolio signals, surfaced live for investor review.</h1>
          <p>
            Every chart on this page is rendered from the live backend summary, so the investor view stays aligned with
            the imported data and current portfolio state.
          </p>
          <div className="analytics-hero-chips">
            <span className="analytics-chip analytics-chip-investor-live">Backend-fed</span>
            <span className="analytics-chip analytics-chip-investor-secondary">Live portfolio summary</span>
            <span className="analytics-chip analytics-chip-investor-info">
              Data completeness {formatTrend(dataQuality.completeness)}
            </span>
          </div>
        </div>
        <div className="analytics-hero-panel">
          <div className="summary-grid three">
            {heroMetrics.map((metric) => (
              <article key={metric.label} className="summary-box">
                <p>{metric.label}</p>
                <strong>{metric.value}</strong>
              </article>
            ))}
          </div>
          <div className="mt-3 text-sm text-slate-100/80">
            {heroMetrics.map((metric) => metric.hint).join(' · ')}
          </div>
        </div>
      </section>

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

      <ImpactStoryCard
        title="Investor Impact Intelligence"
        subtitle="Plain-English portfolio context for LPs"
        story={impactStory}
        maxInsights={4}
      />

      <section className="two-col-grid">
        <SectionCard title="Submission Funnel" subtitle="Portfolio reporting lifecycle">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={submissionFunnelData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="value" stroke={CHART_COLORS.brandDark} strokeWidth={3} dot={{ r: 4 }} />
              </LineChart>
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
                <Bar dataKey="value" fill={CHART_COLORS.brand} radius={[8, 8, 0, 0]} />
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
                <Bar dataKey="score" fill={CHART_COLORS.brandDark} radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Top & Bottom Performers" subtitle="Portfolio companies ranked by ESG score">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={topBottomRows}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="company" tick={{ fontSize: 12 }} angle={-15} textAnchor="end" height={50} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="score" fill={CHART_COLORS.purple} radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </section>
    </div>
  )
}
