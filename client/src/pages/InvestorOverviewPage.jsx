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
import AttentionInbox from '../components/AttentionInbox'
import DataTable from '../components/DataTable'
import ExecutivePageHeader from '../components/ExecutivePageHeader'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import SectionLoadState from '../components/SectionLoadState'
import useDashboardData from '../hooks/useDashboardData'
import useLiveActivity from '../hooks/useLiveActivity'
import useNarrativeHistory from '../hooks/useNarrativeHistory'
import useNarrativeSummary from '../hooks/useNarrativeSummary'

const funnelColors = {
  'Not Started': '#ef4444',
  'In Progress': '#f59e0b',
  Submitted: '#0ea5e9',
  'Under Review': '#8b5cf6',
  Approved: '#10b981',
  Rejected: '#f97316',
  'Resubmission Requested': '#dc2626',
}

function buildInvestorAttentionItems(analytics, dataQuality) {
  const items = []
  const hasQualityData = analytics.data_quality && typeof analytics.data_quality === 'object'
  const totalCompanies = Number(analytics.total_companies || 0)
  const reportingCompanies = Number(analytics.reporting_companies || 0)
  const reportingGap = Math.max(0, totalCompanies - reportingCompanies)
  const completeness = Number(dataQuality.completeness || 0)
  const confidence = Number(dataQuality.confidence || 0)
  const resubmissions = Number(
    analytics.submission_funnel?.Rejected || analytics.submission_funnel?.['Resubmission Requested'] || 0,
  )

  if (reportingGap > 0) {
    items.push({
      id: 'investor-reporting-gap',
      title: 'Portfolio reporting gap',
      detail: `${reportingGap} compan${reportingGap === 1 ? 'y has' : 'ies have'} not completed reporting.`,
      badge: `${reportingGap} outstanding`,
      tone: 'warning',
      icon: 'submissions',
      to: '/submissions',
      actionLabel: 'View coverage',
    })
  }
  if (resubmissions > 0) {
    items.push({
      id: 'investor-resubmissions',
      title: 'Corrections may affect portfolio data',
      detail: `${resubmissions} submission${resubmissions === 1 ? '' : 's'} are rejected or awaiting resubmission.`,
      badge: `${resubmissions} flagged`,
      tone: 'critical',
      icon: 'risks',
      to: '/anomaly-intel',
      actionLabel: 'Inspect risk',
    })
  }
  if (hasQualityData && (completeness < 80 || confidence < 80)) {
    const weakestMetric = completeness <= confidence ? 'completeness' : 'confidence'
    const weakestValue = Math.min(completeness, confidence)
    items.push({
      id: 'investor-data-quality',
      title: 'Data quality needs attention',
      detail: `Portfolio ${weakestMetric} is ${weakestValue.toFixed(1)}%, below the 80% monitoring threshold.`,
      badge: `${weakestValue.toFixed(0)}% ${weakestMetric}`,
      tone: weakestValue < 60 ? 'critical' : 'warning',
      icon: 'analytics',
      to: '/analytics',
      actionLabel: 'Review quality',
    })
  }
  if ((analytics.bottom_performers || []).length > 0) {
    items.push({
      id: 'investor-bottom-performers',
      title: 'ESG performance watchlist',
      detail: `${analytics.bottom_performers.length} portfolio companies are currently in the bottom-performance group.`,
      badge: `${analytics.bottom_performers.length} companies`,
      tone: 'info',
      icon: 'insights',
      to: '/analytics',
      actionLabel: 'Compare performance',
    })
  }
  return items
}

export default function InvestorOverviewPage() {
  const { user } = useOutletContext()
  const { summary, loading, error, retrySection, sections, isRefreshing } = useDashboardData(user)
  const narrative = useNarrativeSummary({ user, audience: 'lp', tone: 'investor-ready', enabled: Boolean(user) })
  const narrativeHistory = useNarrativeHistory({ user, audience: 'lp', limit: 5, enabled: Boolean(user) })
  const liveActivity = useLiveActivity({ user, limit: 6, enabled: Boolean(user) })
  const liveSocketBadge = useMemo(() => {
    if (liveActivity.connectionStatus === 'connected') {
      return { label: 'Connected', className: 'status-good' }
    }
    if (liveActivity.connectionStatus === 'error') {
      return { label: 'Connection Error', className: 'status-critical' }
    }
    return { label: 'Reconnecting', className: 'status-warning' }
  }, [liveActivity.connectionStatus])

  const analytics = summary || {}
  const scoreBreakdown = analytics.score_breakdown || { E: 0, S: 0, G: 0 }
  const emissionsTotals = analytics.emissions_totals || { scope_1: 0, scope_2: 0, scope_3: 0, total: 0 }
  const dataQuality = analytics.data_quality || { completeness: 0, accuracy: 0, confidence: 0 }
  const attentionItems = buildInvestorAttentionItems(analytics, dataQuality)

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
          <SectionLoadState error={error} onRetry={() => retrySection('dashboard')} />
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <ExecutivePageHeader
        eyebrow="Investor portfolio intelligence"
        title="Portfolio ESG overview"
        description="Review portfolio performance, reporting coverage, data quality, and material ESG exposures from one decision-ready view."
        meta={[
          { label: 'Companies', value: analytics.total_companies || 0 },
          { label: 'Reporting', value: analytics.reporting_companies || 0 },
          { label: 'Data confidence', value: `${Number(dataQuality.confidence || 0).toFixed(1)}%` },
        ]}
      />

      <SectionLoadState
        loading={isRefreshing}
        error={sections.dashboard.error}
        cached={Boolean(summary)}
        loadingMessage="Refreshing investor dashboard..."
        onRetry={() => retrySection('dashboard')}
      />

      <section className="executive-kpi-grid" aria-label="Investor portfolio metrics">
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

      <AttentionInbox items={attentionItems} role="investor" />

      <SectionCard title="AI Investor Summary" subtitle="OpenAI-generated narrative from current portfolio analytics">
        <SectionLoadState
          loading={narrative.loading}
          error={narrative.error}
          cached={Boolean(narrative.data)}
          loadingMessage="Generating investor summary..."
          onRetry={narrative.refresh}
        />
        {narrative.data ? (
          <>
            {narrative.data.fallback_used ? (
              <span className="fallback-badge">Live AI unavailable — showing calculated summary</span>
            ) : null}
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

      <section className="two-col-grid">
        <SectionCard title="Narrative History" subtitle="Recent generated portfolio narratives">
          {narrativeHistory.loading ? <p>Loading narrative history...</p> : null}
          {narrativeHistory.error ? <p>{narrativeHistory.error}</p> : null}
          {!narrativeHistory.loading && !narrativeHistory.error ? (
            <ul className="space-y-2 text-sm text-slate-700">
              {(narrativeHistory.items || []).slice(0, 5).map((item) => (
                <li key={item.narrative_id}>
                  <strong>{item.headline || 'Portfolio narrative'}</strong>
                  <p>{item.summary || 'No summary available.'}</p>
                </li>
              ))}
            </ul>
          ) : null}
        </SectionCard>

        <SectionCard
          title="Live Activity"
          subtitle="Latest portfolio events and submission updates"
          actions={<span className={`status-badge ${liveSocketBadge.className}`}>{liveSocketBadge.label}</span>}
        >
          {liveActivity.loading ? <p>Loading live activity...</p> : null}
          {liveActivity.error ? <p>{liveActivity.error}</p> : null}
          {!liveActivity.loading && !liveActivity.error ? (
            <ul className="space-y-2 text-sm text-slate-700">
              {(liveActivity.events || []).slice(0, 6).map((event) => (
                <li key={event.id}>
                  <strong>{event.title || 'Activity update'}</strong>
                  <p>{event.message || 'No message provided.'}</p>
                </li>
              ))}
            </ul>
          ) : null}
        </SectionCard>
      </section>
    </div>
  )
}
