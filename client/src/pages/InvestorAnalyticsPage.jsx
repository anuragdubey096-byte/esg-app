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
import SectionCard from '../components/SectionCard'
import useDashboardData from '../hooks/useDashboardData'
import useNewsletterPreview from '../hooks/useNewsletterPreview'
import useNarrativeSummary from '../hooks/useNarrativeSummary'

export default function InvestorAnalyticsPage() {
  const { user } = useOutletContext()
  const { summary, loading, error } = useDashboardData(user)
  const narrative = useNarrativeSummary({ user, audience: 'lp', tone: 'board-ready', enabled: Boolean(user) })
  const newsletter = useNewsletterPreview({ user, audience: 'investor', tone: 'board-ready' })

  const analytics = summary || {}

  const resourceData = useMemo(() => {
    const totals = analytics.resource_totals || {}
    return [
      { metric: 'Energy', value: Number(totals.energy || 0) },
      { metric: 'Water', value: Number(totals.water || 0) },
      { metric: 'Waste', value: Number(totals.waste || 0) },
    ]
  }, [analytics.resource_totals])

  const emissionsTrend = useMemo(() => {
    return (analytics.emissions_trend || []).map((point) => ({
      period: point.period,
      total_emissions: Number(point.total_emissions || 0),
    }))
  }, [analytics.emissions_trend])

  const socialData = useMemo(() => {
    const values = analytics.diversity_safety || {}
    return [
      { metric: 'Female Representation %', value: Number(values.female_representation_percent || 0) },
      { metric: 'TRIFR', value: Number(values.trifr || 0) },
      { metric: 'High Variance Flags', value: Number(values.high_variance_flags || 0) },
    ]
  }, [analytics.diversity_safety])

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
      <SectionCard title="AI Analytics Narrative" subtitle="OpenAI-generated interpretation of portfolio analytics">
        {narrative.loading ? <p>Generating summary...</p> : null}
        {narrative.error ? <p>{narrative.error}</p> : null}
        {!narrative.loading && !narrative.error && narrative.data ? (
          <>
            <h4>{narrative.data.headline || 'Portfolio Analytics Summary'}</h4>
            <p>{narrative.data.summary || 'No narrative summary available.'}</p>
          </>
        ) : null}
      </SectionCard>

      <SectionCard title="Newsletter Preview" subtitle="Generate the latest LP newsletter draft from approved portfolio data">
        <button className="button" type="button" onClick={newsletter.generate} disabled={newsletter.loading}>
          {newsletter.loading ? 'Generating...' : 'Generate Newsletter Preview'}
        </button>
        {newsletter.error ? <p>{newsletter.error}</p> : null}
        {newsletter.data ? (
          <div className="mt-3 space-y-2 text-sm text-slate-700">
            <p><strong>{newsletter.data.subject_line || 'Portfolio newsletter'}</strong></p>
            <p>{newsletter.data.summary || 'No summary available.'}</p>
          </div>
        ) : null}
      </SectionCard>

      <section className="two-col-grid">
        <SectionCard title="Emissions Trend" subtitle="Portfolio total emissions over recent periods">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={emissionsTrend}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="total_emissions" stroke="#0f766e" strokeWidth={3} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Resource Analytics" subtitle="Water, waste, and energy totals">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={resourceData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="metric" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="value" fill="#2563eb" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </section>

      <SectionCard title="Social & Safety Metrics" subtitle="Portfolio-level diversity and safety indicators">
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={socialData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="metric" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#7c3aed" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </SectionCard>
    </div>
  )
}
