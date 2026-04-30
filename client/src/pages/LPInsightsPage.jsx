import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import SectionCard from '../components/SectionCard'
import DataTable from '../components/DataTable'
import KpiCard from '../components/KpiCard'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

export default function LPInsightsPage() {
  const { user } = useOutletContext()
  const [dashboard, setDashboard] = useState(null)
  const [metrics, setMetrics] = useState([])
  const [reports, setReports] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const headers = {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        }
        const [dashRes, metricRes, reportRes] = await Promise.all([
          fetch(`${BACKEND_URL}/lp/dashboard`, { headers }),
          fetch(`${BACKEND_URL}/lp/metrics`, { headers }),
          fetch(`${BACKEND_URL}/lp/reports`, { headers }),
        ])
        if (!dashRes.ok || !metricRes.ok || !reportRes.ok) {
          const detail = await dashRes.text()
          throw new Error(detail || 'Unable to load LP compatibility endpoints.')
        }
        const [dashJson, metricJson, reportJson] = await Promise.all([dashRes.json(), metricRes.json(), reportRes.json()])
        if (!cancelled) {
          setDashboard(dashJson)
          setMetrics(Array.isArray(metricJson.key_metrics) ? metricJson.key_metrics : [])
          setReports(reportJson)
        }
      } catch (requestError) {
        if (!cancelled) setError(requestError.message || 'Failed to load LP insights.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [user?.email, user?.role])

  const metricRows = useMemo(
    () =>
      metrics.map((item, index) => ({
        id: index + 1,
        metric_name: item.metric_name || 'Metric',
        current_value: item.current_value || '-',
        benchmark_value: item.benchmark_value || '-',
        benchmark_status: item.benchmark_status || '-',
      })),
    [metrics],
  )

  const completion = dashboard?.completion_status || {}
  const scoreBreakdown = dashboard?.score_breakdown || {}
  const impactStory = dashboard?.impact_story || {}

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="LP Insights Dashboard" subtitle="Loading LP compatibility endpoints...">
          <p>Loading data from backend.</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="LP Insights Dashboard" subtitle="Live data unavailable">
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <section className="kpi-grid">
        <KpiCard title="Completion %" value={`${Number(completion.completion_percent || 0).toFixed(1)}%`} />
        <KpiCard title="Approved Companies" value={`${completion.companies_with_approved_submission || 0}`} />
        <KpiCard title="Active Cycle" value={`${completion.active_cycle_year || reports?.active_cycle_year || 'N/A'}`} />
        <KpiCard title="Score (E/S/G)" value={`${scoreBreakdown.environmental?.current_score || 0}/${scoreBreakdown.social?.current_score || 0}/${scoreBreakdown.governance?.current_score || 0}`} />
      </section>

      <SectionCard title="LP Metrics" subtitle="Portfolio metrics benchmark feed">
        <DataTable
          columns={[
            { key: 'metric_name', label: 'Metric', sortable: true },
            { key: 'current_value', label: 'Current', sortable: true },
            { key: 'benchmark_value', label: 'Benchmark', sortable: true },
            { key: 'benchmark_status', label: 'Status', sortable: true },
          ]}
          rows={metricRows}
          pageSize={8}
          emptyMessage="No LP metrics available."
        />
      </SectionCard>

      <SectionCard title="LP Impact Story" subtitle="Narrative and benchmark callouts for LP reporting">
        <p><strong>{impactStory.headline || 'Impact story'}</strong></p>
        <p>{impactStory.summary || 'No impact summary available.'}</p>
        <ul className="mini-legend">
          {(impactStory.highlights || []).slice(0, 5).map((item, index) => (
            <li key={`impact-${index}`}>
              <span style={{ background: '#2563eb' }} />
              {item}
            </li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard title="LP Reports Feed" subtitle="Available reporting documents">
        <p>Reports: {(reports?.available_reports || []).join(', ') || 'N/A'}</p>
        <p>Active cycle year: {reports?.active_cycle_year || 'N/A'}</p>
      </SectionCard>
    </div>
  )
}
