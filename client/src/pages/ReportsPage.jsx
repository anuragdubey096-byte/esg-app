import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import SectionCard from '../components/SectionCard'
import useDashboardData from '../hooks/useDashboardData'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL
const reportFrameworks = ['EDCI', 'SFDR']

export default function ReportsPage() {
  const { user } = useOutletContext()
  const { companies, cycles } = useDashboardData(user)
  const [framework, setFramework] = useState(reportFrameworks[0])
  const [portfolio, setPortfolio] = useState('All Portfolio Companies')
  const [period, setPeriod] = useState('Current Cycle')
  const [format, setFormat] = useState('pdf')
  const [message, setMessage] = useState('')
  const [download, setDownload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [lpFeed, setLpFeed] = useState(null)

  const portfolios = useMemo(() => ['All Portfolio Companies', ...companies.map((c) => c.name)], [companies])
  const periods = useMemo(() => {
    const cyclePeriods = (cycles || []).map((cycle) => `FY${cycle.cycle_year}`)
    return ['Current Cycle', ...cyclePeriods]
  }, [cycles])

  const exportReport = async (event) => {
    event.preventDefault()
    setLoading(true)
    setMessage('Generating report...')
    setDownload(null)
    try {
      const query = new URLSearchParams({
        format,
        period,
        portfolio,
      })
      const response = await fetch(`${BACKEND_URL}/reports/${framework.toLowerCase()}/export?${query.toString()}`)
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || 'Failed to export report')
      }
      const payload = await response.json()
      setDownload(payload)
      setMessage(`Generated ${framework} ${payload.format.toUpperCase()} report for ${payload.rows_exported} companies.`)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setLoading(false)
    }
  }

  const loadLpReports = async () => {
    setLoading(true)
    setMessage('Loading LP reports...')
    try {
      const response = await fetch(`${BACKEND_URL}/lp/reports`, {
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || 'Failed to load LP reports')
      }
      const payload = await response.json()
      setLpFeed(payload)
      setMessage('LP reports feed loaded.')
    } catch (error) {
      setLpFeed(null)
      setMessage(error.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-grid">
      <SectionCard title="Reports" subtitle="Generate aligned reporting exports for LPs and internal committees">
        {user?.role !== 'manager' ? (
          <div className="space-y-3">
            <p className="action-message">Direct CSV/PDF export is manager-only. LP reports feed is available below.</p>
            <button className="button" type="button" onClick={loadLpReports} disabled={loading}>
              {loading ? 'Loading...' : 'Load LP Reports Feed'}
            </button>
            {lpFeed ? (
              <div className="text-sm text-slate-700">
                <p><strong>Available reports:</strong> {(lpFeed.available_reports || []).join(', ') || 'None'}</p>
                <p><strong>Active cycle year:</strong> {lpFeed.active_cycle_year || 'N/A'}</p>
                <p>{lpFeed.message || ''}</p>
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="framework-row">
          {reportFrameworks.map((item) => (
            <button
              key={item}
              type="button"
              className={`framework-button ${framework === item ? 'active' : ''}`}
              onClick={() => setFramework(item)}
            >
              {item}
            </button>
          ))}
        </div>

        {user?.role === 'manager' ? (
          <div className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Formal report</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">Company, cycle and ESG pillars</p>
              <p className="mt-1 text-xs text-slate-600">Environmental, Social and Governance metrics with internal scores.</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Supporting record</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">Evidence and audit history</p>
              <p className="mt-1 text-xs text-slate-600">Evidence coverage, validation findings, review activity and methodology.</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Later phase</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">Scheduled generation</p>
              <p className="mt-1 text-xs text-slate-600">Planned, but intentionally not active until delivery and retention controls are defined.</p>
            </div>
          </div>
        ) : null}

        <form className="report-form" onSubmit={exportReport}>
          <label>
            <span>Select portfolio/company</span>
            <select value={portfolio} onChange={(event) => setPortfolio(event.target.value)}>
              {portfolios.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>

          <label>
            <span>Select time period</span>
            <select value={period} onChange={(event) => setPeriod(event.target.value)}>
              {periods.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>

          <label>
            <span>Export format</span>
            <select value={format} onChange={(event) => setFormat(event.target.value)}>
              <option value="pdf">Formal PDF report</option>
              <option value="csv">CSV data extract</option>
            </select>
          </label>

          <button className="button" type="submit" disabled={loading || user?.role !== 'manager'}>
            {loading ? 'Generating...' : 'Generate Report'}
          </button>
        </form>

        {message ? <p className="action-message">{message}</p> : null}
        {download ? (
          <p className="text-sm text-slate-700">
            Download:
            {' '}
            <a href={`${BACKEND_URL}${download.download_url}`} target="_blank" rel="noreferrer">
              {download.file_name}
            </a>
          </p>
        ) : null}
      </SectionCard>
    </div>
  )
}
