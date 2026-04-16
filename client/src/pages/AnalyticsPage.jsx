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
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import { API_BASE_URL } from '../lib/api'

const CHART_COLORS = {
  'Not Started': '#94a3b8',
  'In Progress': '#0ea5e9',
  Submitted: '#f59e0b',
  'Under Review': '#8b5cf6',
  Approved: '#10b981',
  'Resubmission Requested': '#ef4444',
}

function formatWindowDate(value) {
  if (!value) return 'N/A'
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

function formatDaysRemaining(value) {
  if (value == null) return 'Deadline timing unavailable.'
  if (value < 0) return `${Math.abs(value)} days overdue`
  return `${value} days remaining`
}

function SectorTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload || {}
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm">
      <p className="text-sm ui-text-strong text-slate-800">{label}</p>
      <p className="text-xs text-slate-600">Avg ESG Score: {Number(row.avg_esg_score || 0).toFixed(1)}</p>
      <p className="text-xs text-slate-600">Avg GHG: {Number(row.avg_ghg_emissions || 0).toLocaleString()} tCO2e</p>
      <p className="text-xs text-slate-600">Companies: {Number(row.company_count || 0)}</p>
    </div>
  )
}

export default function AnalyticsPage() {
  const { user } = useOutletContext()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    const loadAnalytics = async () => {
      try {
        setLoading(true)
        setError('')

        const response = await fetch(`${API_BASE_URL}/analytics/manager`, {
          headers: {
            'x-user-role': user?.role || 'manager',
            'x-user-email': user?.email || '',
          },
        })

        if (!response.ok) {
          const payload = await response.json().catch(() => ({}))
          throw new Error(payload.detail || `Failed to fetch analytics data (${response.status})`)
        }

        const payload = await response.json()
        if (!cancelled) setData(payload)
      } catch (fetchError) {
        if (!cancelled) {
          setData(null)
          setError(fetchError.message || 'Unable to load analytics data.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadAnalytics()

    return () => {
      cancelled = true
    }
  }, [user?.email, user?.role])

  const summaryCards = useMemo(() => data?.summary_cards || [], [data])
  const statusDistribution = useMemo(() => data?.status_distribution || [], [data])
  const emissionsTrend = useMemo(() => data?.emissions_trend || [], [data])
  const sectorPerformance = useMemo(() => data?.sector_performance || [], [data])
  const policyAdoption = useMemo(() => data?.policy_adoption || [], [data])
  const topPerformers = useMemo(() => data?.top_performers || [], [data])
  const bottomPerformers = useMemo(() => data?.bottom_performers || [], [data])
  const cycleSnapshot = data?.cycle_snapshot || {}

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="ESG Analytics" subtitle="Loading live analytics from the backend...">
          <p>Loading data from backend.</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="ESG Analytics" subtitle="Live data unavailable">
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <section className="analytics-hero manager-hero">
        <div className="analytics-hero-copy">
          <p className="eyebrow">Manager Analytics</p>
          <h1>Portfolio performance, grounded in live submission data.</h1>
          <p>
            The charts below are rendered from backend analytics, so the view stays aligned with the imported fixture
            dataset and current database state.
          </p>
          <div className="analytics-hero-chips">
            <span className="analytics-chip analytics-chip-manager-live">Backend-fed</span>
            <span className="analytics-chip analytics-chip-manager-state">{cycleSnapshot.status || 'closed'} cycle</span>
            <span className="analytics-chip analytics-chip-manager-warning">
              {cycleSnapshot.days_remaining == null ? 'Deadline unavailable' : formatDaysRemaining(cycleSnapshot.days_remaining)}
            </span>
          </div>
        </div>
        <div className="analytics-hero-panel">
          <div className="summary-grid three">
            <article className="summary-box">
              <p>Active Cycle</p>
              <strong>{cycleSnapshot.cycle_year ?? 'N/A'}</strong>
            </article>
            <article className="summary-box">
              <p>Reporting Companies</p>
              <strong>{data?.summary_cards?.[1]?.value ?? '0'}</strong>
            </article>
            <article className="summary-box">
              <p>Portfolio ESG Score</p>
              <strong>{data?.summary_cards?.[0]?.value ?? '0.0'}</strong>
            </article>
          </div>
        </div>
      </section>

      <section className="kpi-grid">
        {summaryCards.map((card) => (
          <KpiCard key={card.title} title={card.title} value={card.value} trend={card.trend} trendLabel={card.trendLabel} />
        ))}
      </section>

      <SectionCard title="Cycle Snapshot" subtitle="Live collection window and portfolio context">
        <div className="summary-grid three">
          <article className="summary-box">
            <p>Active Cycle</p>
            <strong>{cycleSnapshot.cycle_year ?? 'N/A'}</strong>
          </article>
          <article className="summary-box">
            <p>Window</p>
            <strong>
              {formatWindowDate(cycleSnapshot.submission_open_date)} to {formatWindowDate(cycleSnapshot.submission_deadline)}
            </strong>
          </article>
          <article className="summary-box">
            <p>Status</p>
            <strong>{cycleSnapshot.status || 'closed'}</strong>
          </article>
        </div>
        <p className="text-sm text-slate-600 mt-3">{formatDaysRemaining(cycleSnapshot.days_remaining)}</p>
      </SectionCard>

      <section className="two-col-grid">
        <SectionCard title="Status Mix" subtitle="Portfolio submission distribution from the backend">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={statusDistribution}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={72}
                  outerRadius={108}
                  paddingAngle={3}
                >
                  {statusDistribution.map((entry) => (
                    <Cell key={entry.name} fill={CHART_COLORS[entry.name] || entry.color || '#64748b'} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Emissions Trend" subtitle="Live portfolio emissions trend from backend analytics">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={emissionsTrend}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" />
                <YAxis />
                <Tooltip formatter={(value) => `${Number(value || 0).toLocaleString()} tCO2e`} />
                <Line type="monotone" dataKey="total_emissions" stroke="#0f766e" strokeWidth={3} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </section>

      <section className="two-col-grid">
        <SectionCard title="Sector ESG Scores" subtitle="Average score and average emissions by sector">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={sectorPerformance}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="sector" tick={{ fontSize: 12 }} angle={-15} textAnchor="end" height={60} />
                <YAxis domain={[0, 100]} />
                <Tooltip content={<SectorTooltip />} />
                <Legend />
                <Bar dataKey="avg_esg_score" name="Avg ESG Score" fill="#2563eb" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 text-sm text-slate-600">
            Higher bars indicate stronger ESG performance. Hover a sector to see company count and emissions profile.
          </div>
        </SectionCard>

        <SectionCard title="Policy Adoption" subtitle="Policy coverage across the portfolio">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={policyAdoption} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} />
                <YAxis type="category" dataKey="policy_name" width={160} />
                <Tooltip formatter={(value) => `${Number(value || 0).toFixed(1)}%`} />
                <Bar dataKey="adoption_percentage" fill="#7c3aed" radius={[0, 8, 8, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </section>

      <SectionCard title="Performance Leaders and Watchlist" subtitle="Backend-ranked companies for quick review">
        <div className="two-col-grid compact">
          <div>
            <p className="text-sm ui-text-strong text-slate-700 mb-3">Top Performers</p>
            <ul className="space-y-2">
              {topPerformers.map((item, index) => (
                <li key={`${item.company_name}-${index}`} className="flex items-center justify-between rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2">
                  <span className="font-medium text-slate-800">{item.company_name}</span>
                  <span className="text-sm ui-text-strong text-emerald-700">{Number(item.esg_score || 0).toFixed(2)}</span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <p className="text-sm ui-text-strong text-slate-700 mb-3">Bottom Performers</p>
            <ul className="space-y-2">
              {bottomPerformers.map((item, index) => (
                <li key={`${item.company_name}-${index}`} className="flex items-center justify-between rounded-lg border border-rose-100 bg-rose-50 px-3 py-2">
                  <span className="font-medium text-slate-800">{item.company_name}</span>
                  <span className="text-sm ui-text-strong text-rose-700">{Number(item.esg_score || 0).toFixed(2)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </SectionCard>
    </div>
  )
}

