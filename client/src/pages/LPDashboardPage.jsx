import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import ActivityFeedCard from '../components/ActivityFeedCard'
import KpiCard from '../components/KpiCard'
import ImpactStoryCard from '../components/ImpactStoryCard'
import NewsletterCard from '../components/NewsletterCard'
import NarrativeSummaryCard from '../components/NarrativeSummaryCard'
import SectionCard from '../components/SectionCard'
import { useOptionalLiveUpdates } from '../contexts/LiveUpdatesContext'
import useNarrativeSummary from '../hooks/useNarrativeSummary'
import useNewsletterSummary from '../hooks/useNewsletterSummary'
import { API_BASE_URL } from '../lib/api'
import { CHART_COLORS } from '../lib/foundation'
import { NARRATIVE_UI_COPY } from '../lib/portalOptions'
import { UI_LABELS } from '../lib/uiLabels'

function formatSignedPercent(value) {
  const numeric = Number(value || 0)
  if (!Number.isFinite(numeric)) return 'N/A'
  return `${numeric >= 0 ? '+' : ''}${numeric.toFixed(1)}%`
}

function formatComparisonValue(value, unit = '') {
  if (value === null || value === undefined || value === '') return 'N/A'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  if (unit === '%') return `${numeric.toFixed(1)}%`
  if (unit === 'rate') return numeric.toFixed(2)
  if (unit) return `${numeric.toLocaleString()} ${unit}`
  return numeric.toLocaleString()
}

export default function LPDashboardPage() {
  const { user } = useOutletContext()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const liveUpdates = useOptionalLiveUpdates()
  const narrative = useNarrativeSummary({
    user,
    audience: 'lp',
    tone: 'lp-letter',
    enabled: Boolean(user),
  })
  const newsletter = useNewsletterSummary({
    user,
    audience: 'investor',
    tone: 'lp-letter',
    enabled: Boolean(user),
  })

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true)
        const response = await fetch(`${API_BASE_URL}/lp/dashboard`, {
          headers: {
            'X-User-Role': user?.role || 'investor',
            'X-User-Email': user?.email || '',
            'Content-Type': 'application/json',
          },
        })

        if (!response.ok) {
          throw new Error(`Failed to fetch dashboard data: ${response.status}`)
        }

        const dashboardData = await response.json()
        setData(dashboardData)
        setError(null)
      } catch (err) {
        console.error('Error fetching dashboard:', err)
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchDashboardData()
  }, [liveUpdates?.lastEvent?.id, user])

  useEffect(() => {
    if (!liveUpdates?.lastEvent) return
    narrative.refresh()
    newsletter.refresh()
  }, [liveUpdates?.lastEvent?.id, narrative.refresh, newsletter.refresh])

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.lpDashboard.title} subtitle={UI_LABELS.pages.lpDashboard.loadingSubtitle}>
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.lpDashboard.title} subtitle={UI_LABELS.pages.lpDashboard.errorSubtitle}>
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
            <p className="ui-text-strong">Error: {error}</p>
            <p className="text-sm mt-2">{UI_LABELS.common.backendApiReachable}</p>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.lpDashboard.title} subtitle={UI_LABELS.pages.lpDashboard.noDataSubtitle}>
          <p className="text-gray-600">{UI_LABELS.pages.lpDashboard.noDataMessage}</p>
        </SectionCard>
      </div>
    )
  }

  const scorecard = data.portfolio_scorecard ?? {
    overall_esg_score: 'N/A',
    overall_esg_score_previous: 'N/A',
    yoy_change_percent: 0,
    pillars: [],
  }
  const completion = data.completion_status ?? {
    total_companies: 0,
    companies_with_approved_submission: 0,
    last_updated: 'n/a',
  }
  const keyMetrics = Array.isArray(data.key_metrics) ? data.key_metrics : []
  const emissionsTrendRaw = Array.isArray(data.emissions_trend) ? data.emissions_trend : []
  const diversityMetrics = Array.isArray(data.diversity_metrics) ? data.diversity_metrics : []
  const policyAdoption = Array.isArray(data.policy_adoption) ? data.policy_adoption : []
  const actionPlanStatus = data.action_plan_status ?? { in_progress: 0, completed: 0 }
  const impactStory = data.impact_story || null
  const comparisonRows = Array.isArray(impactStory?.comparison_rows)
    ? impactStory.comparison_rows.map((row) => ({
        metric: row.metric_name || 'Metric',
        current: formatComparisonValue(row.current_value, row.unit),
        previous: formatComparisonValue(row.previous_value, row.unit),
        delta:
          row.trend_percent === null || row.trend_percent === undefined
            ? 'N/A'
            : formatSignedPercent(row.trend_percent),
      }))
    : []

  const completionPercent = Number(completion.total_companies)
    ? ((Number(completion.companies_with_approved_submission) / Number(completion.total_companies)) * 100).toFixed(1)
    : '0.0'
  const keyMetricCount = keyMetrics.length

  const emissionsData = emissionsTrendRaw.map((item) => ({
    period: item.period,
    'Scope 1': Number(item.scope_1 || 0) / 1000,
    'Scope 2': Number(item.scope_2 || 0) / 1000,
    'Scope 3': Number(item.scope_3 || 0) / 1000,
  }))

  return (
    <div className="page-grid">
      <section className="investor-narrative-grid">
        <NarrativeSummaryCard
          title="Investor Narrative Summary"
          subtitle={NARRATIVE_UI_COPY.pages.lpDashboardNarrativeSubtitle}
          data={narrative.data}
          loading={narrative.loading}
          error={narrative.error}
          onRefresh={narrative.refresh}
          variant="investor"
        />

        <ImpactStoryCard
          title="Portfolio Narrative Intelligence"
          subtitle={NARRATIVE_UI_COPY.pages.lpDashboardImpactSubtitle}
          story={impactStory}
          maxInsights={4}
          variant="investor"
        />
      </section>

      <NewsletterCard
        title="Investor Newsletter Draft"
        subtitle={NARRATIVE_UI_COPY.pages.lpDashboardNewsletterSubtitle}
        data={newsletter.data}
        loading={newsletter.loading}
        error={newsletter.error}
        onRefresh={newsletter.refresh}
        onExport={newsletter.exportNewsletter}
        onSend={newsletter.sendNewsletter}
        exporting={newsletter.exporting}
        sending={newsletter.sending}
      />

      <ActivityFeedCard
        user={user}
        title="Investor Activity Feed"
        subtitle="Live reporting, approval, and action-plan activity visible to investor users"
      />

      <SectionCard title="Portfolio ESG Scorecard" subtitle="Live backend snapshot">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 p-6 rounded-lg">
            <p className="text-sm text-gray-600 mb-2">Overall ESG Score</p>
            <p className="ui-text-display text-blue-900">{scorecard.overall_esg_score}</p>
            <p className="text-sm text-green-600 ui-text-strong mt-2">{formatSignedPercent(scorecard.yoy_change_percent)} YoY</p>
          </div>

          {scorecard.pillars.map((pillar) => (
            <div key={pillar.name} className="bg-gradient-to-br from-gray-50 to-gray-100 p-6 rounded-lg">
              <p className="text-sm text-gray-600 mb-2">{pillar.name === 'E' ? 'Environmental' : pillar.name === 'S' ? 'Social' : 'Governance'}</p>
              <p className="ui-text-display text-gray-800">{pillar.current_score}</p>
              <p className="text-xs text-gray-500 mt-1">Previously: {pillar.previous_score}</p>
              <p className="text-sm text-green-600 ui-text-strong mt-2">{formatSignedPercent(pillar.yoy_change)}</p>
            </div>
          ))}
        </div>
      </SectionCard>

      <section className="summary-grid three">
        <article className="summary-box">
          <p>Total Companies</p>
          <strong>{completion.total_companies}</strong>
        </article>
        <article className="summary-box">
          <p>Approved Submissions</p>
          <strong>{completion.companies_with_approved_submission}</strong>
        </article>
        <article className="summary-box">
          <p>Last Updated</p>
          <strong>{completion.last_updated}</strong>
        </article>
      </section>

      <section className="kpi-grid">
        {keyMetrics.map((metric) => (
          <KpiCard
            key={metric.metric_name}
            title={metric.metric_name}
            value={metric.current_value}
            trendLabel={`${metric.trend_direction === 'up' ? 'Up' : metric.trend_direction === 'down' ? 'Down' : 'Flat'} ${Math.abs(Number(metric.trend_percent || 0)).toFixed(1)}% vs prior year`}
          />
        ))}
      </section>

      <SectionCard title="Portfolio Submission Status" subtitle="Data Quality & Coverage">
        <div className="bg-blue-50 p-6 rounded-lg">
          <div className="flex items-end justify-between mb-4">
            <div>
              <p className="text-sm text-gray-600 mb-1">Approved Submissions</p>
              <p className="ui-text-display text-blue-900">
                {completion.companies_with_approved_submission}/{completion.total_companies}
              </p>
            </div>
            <div className="text-right">
              <p className="ui-text-display text-green-600">{completionPercent}%</p>
              <p className="text-sm text-gray-600">Complete</p>
            </div>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div className="bg-green-500 h-2 rounded-full" style={{ width: `${completionPercent}%` }} />
          </div>
          <p className="text-xs text-gray-500 mt-3">Last updated: {completion.last_updated}</p>
        </div>
      </SectionCard>

      <SectionCard title="Emissions Trend" subtitle="Scope 1, 2, 3 Analysis (in thousands tCO2e)">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={emissionsData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" />
            <YAxis />
            <Tooltip formatter={(value) => `${value.toFixed(0)}k tCO2e`} />
            <Legend />
            <Line type="monotone" dataKey="Scope 1" stroke={CHART_COLORS.scope1} strokeWidth={2} />
            <Line type="monotone" dataKey="Scope 2" stroke={CHART_COLORS.scope2} strokeWidth={2} />
            <Line type="monotone" dataKey="Scope 3" stroke={CHART_COLORS.scope3} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </SectionCard>

      <SectionCard title="Previous Year Comparison" subtitle="Current year vs previous year reference">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-100 border-b">
              <tr>
                <th className="text-left p-3 ui-text-strong">Metric</th>
                <th className="text-right p-3 ui-text-strong">Current</th>
                <th className="text-right p-3 ui-text-strong">Previous</th>
                <th className="text-right p-3 ui-text-strong">Change</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map((row) => (
                <tr key={row.metric} className="border-b hover:bg-gray-50">
                  <td className="p-3 font-medium">{row.metric}</td>
                  <td className="p-3 text-right">{row.current}</td>
                  <td className="p-3 text-right">{row.previous}</td>
                  <td className="p-3 text-right ui-text-strong">{row.delta}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard title="Workforce Diversity" subtitle="Progress Across Key Indicators">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {diversityMetrics.map((metric) => (
            <div key={metric.metric_name} className="border-l-4 border-blue-500 pl-4">
              <p className="text-sm text-gray-600 mb-1">{metric.metric_name}</p>
              <p className="ui-text-display text-blue-900">{metric.percentage}%</p>
              <p className="text-xs text-gray-500 mt-1">
                Previous: {metric.previous_year}% ({metric.trend === 'up' ? 'Up' : metric.trend === 'down' ? 'Down' : 'Flat'})
              </p>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="ESG Policy Adoption" subtitle="Portfolio Coverage">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {policyAdoption.map((policy) => (
            <div key={policy.policy_name} className="bg-gradient-to-br from-purple-50 to-purple-100 p-4 rounded-lg text-center">
              <p className="text-xs text-gray-600 mb-2">{policy.policy_name}</p>
              <p className="ui-text-display text-purple-900">{policy.adoption_percentage.toFixed(1)}%</p>
              <p className="text-xs text-gray-500 mt-2">{policy.companies_with_policy} of {policy.total_companies} companies</p>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Action Plan Status" subtitle="Portfolio-Wide Initiatives">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-blue-50 p-6 rounded-lg text-center">
            <p className="text-sm text-gray-600 mb-2">In Progress</p>
            <p className="ui-text-display text-blue-900">{actionPlanStatus.in_progress}</p>
            <p className="text-xs text-gray-500 mt-2">Active initiatives</p>
          </div>
          <div className="bg-green-50 p-6 rounded-lg text-center">
            <p className="text-sm text-gray-600 mb-2">Completed</p>
            <p className="ui-text-display text-green-900">{actionPlanStatus.completed}</p>
            <p className="text-xs text-gray-500 mt-2">Closed initiatives</p>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Snapshot Notes" subtitle="Data is sourced from the live backend response">
        <p className="text-sm text-gray-600">
          This view is driven by {keyMetricCount} portfolio metrics, live submission status, and export-ready portfolio summaries.
        </p>
      </SectionCard>
    </div>
  )
}
