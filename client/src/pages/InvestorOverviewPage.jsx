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
import ActivityFeedCard from '../components/ActivityFeedCard'
import DataTable from '../components/DataTable'
import DashboardNarrativeMaterialCard from '../components/DashboardNarrativeMaterialCard'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import { CHART_COLORS, STATUS_COLORS } from '../lib/foundation'
import { UI_LABELS } from '../lib/uiLabels'
import useDashboardData from '../hooks/useDashboardData'
import useDashboardNarrativeMaterial from '../hooks/useDashboardNarrativeMaterial'

function hasValue(value) {
  return value !== null && value !== undefined && value !== ''
}

function formatScore(value) {
  return hasValue(value) ? `${Number(value).toFixed(1)}/100` : 'N/A'
}

function formatPercent(value) {
  return hasValue(value) ? `${Number(value).toFixed(1)}%` : 'N/A'
}

function formatCoverage(reporting, total) {
  if (!hasValue(reporting) && !hasValue(total)) return 'N/A'
  return `${Number(reporting ?? 0)}/${Number(total ?? 0)}`
}

function formatEsgBreakdown(scoreBreakdown) {
  const e = hasValue(scoreBreakdown?.E) ? Number(scoreBreakdown.E).toFixed(1) : 'N/A'
  const s = hasValue(scoreBreakdown?.S) ? Number(scoreBreakdown.S).toFixed(1) : 'N/A'
  const g = hasValue(scoreBreakdown?.G) ? Number(scoreBreakdown.G).toFixed(1) : 'N/A'
  return `${e} / ${s} / ${g}`
}

function formatEmissionsTotal(value) {
  return hasValue(value) ? `${Number(value).toLocaleString()} tCO2e` : 'N/A'
}

export default function InvestorOverviewPage() {
  const { user } = useOutletContext()
  const { summary, loading, error } = useDashboardData(user)
  const investorNarrative = useDashboardNarrativeMaterial({ user, materialType: 'investor_narrative', enabled: Boolean(user) })
  const trendSummary = useDashboardNarrativeMaterial({ user, materialType: 'trend_summary', enabled: Boolean(user) })
  const attentionSummary = useDashboardNarrativeMaterial({ user, materialType: 'attention_summary', enabled: Boolean(user) })

  const analytics = summary || {}
  const scoreBreakdown = analytics.score_breakdown || { E: 0, S: 0, G: 0 }
  const emissionsTotals = analytics.emissions_totals || { scope_1: 0, scope_2: 0, scope_3: 0, total: 0 }
  const dataQuality = analytics.data_quality || { completeness: 0, accuracy: 0, confidence: 0 }

  const submissionFunnelData = useMemo(() => {
    const funnel = analytics.submission_funnel || {}
    return Object.keys(STATUS_COLORS).filter((key) => key !== 'Under Review' && key !== 'Resubmission Requested').map((key) => ({
      name: key,
      value: Number(funnel[key] || 0),
      color: STATUS_COLORS[key],
    }))
  }, [analytics.submission_funnel])

  const topBottomRows = useMemo(() => {
    const topRows = (analytics.top_performers || []).map((item, index) => ({
      id: `top-${index}`,
      bucket: 'Top',
      company: item.company_name,
      sector: item.sector,
      score: hasValue(item.esg_score) ? Number(item.esg_score).toFixed(1) : 'N/A',
    }))
    const bottomRows = (analytics.bottom_performers || []).map((item, index) => ({
      id: `bottom-${index}`,
      bucket: 'Bottom',
      company: item.company_name,
      sector: item.sector,
      score: hasValue(item.esg_score) ? Number(item.esg_score).toFixed(1) : 'N/A',
    }))
    return [...topRows, ...bottomRows]
  }, [analytics.bottom_performers, analytics.top_performers])

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.investorOverview.title} subtitle={UI_LABELS.pages.investorOverview.loadingSubtitle}>
          <p>{UI_LABELS.common.loadingDataFromBackend}</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.investorOverview.title} subtitle={UI_LABELS.pages.investorOverview.errorSubtitle}>
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <section className="kpi-grid">
        <KpiCard title="Portfolio ESG Score" value={formatScore(analytics.portfolio_esg_score)} />
        <KpiCard title="E / S / G" value={formatEsgBreakdown(scoreBreakdown)} />
        <KpiCard
          title="Reporting Coverage"
          value={formatCoverage(analytics.reporting_companies, analytics.total_companies)}
          trendLabel="companies submitted"
        />
        <KpiCard title="Total Emissions" value={formatEmissionsTotal(emissionsTotals.total)} />
        <KpiCard
          title="Governance Adoption"
          value={formatPercent(analytics.governance_adoption_percent)}
          trendLabel="portfolio policy coverage"
        />
      </section>

      <DashboardNarrativeMaterialCard
        title="Investor Portfolio Narrative"
        subtitle="AI-assisted portfolio narrative generated from live approved analytics and impact context"
        data={investorNarrative.data}
        loading={investorNarrative.loading}
        error={investorNarrative.error}
        onRefresh={investorNarrative.refresh}
      />

      <section className="two-col-grid">
        <DashboardNarrativeMaterialCard
          title="What Changed Since Last Cycle"
          subtitle="Shared trend summary from live portfolio comparison context"
          data={trendSummary.data}
          loading={trendSummary.loading}
          error={trendSummary.error}
          onRefresh={trendSummary.refresh}
        />
        <DashboardNarrativeMaterialCard
          title="Risk & Attention Summary"
          subtitle="Shared portfolio attention summary generated from live anomaly context"
          data={attentionSummary.data}
          loading={attentionSummary.loading}
          error={attentionSummary.error}
          onRefresh={attentionSummary.refresh}
        />
      </section>

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

      <ActivityFeedCard
        user={user}
        title="Investor Activity Feed"
        subtitle="Live portfolio workflow events surfaced for investor users"
      />
    </div>
  )
}
