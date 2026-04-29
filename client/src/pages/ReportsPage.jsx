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
  const [format, setFormat] = useState('csv')
  const [message, setMessage] = useState('')
  const [download, setDownload] = useState(null)
  const [loading, setLoading] = useState(false)

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
      const response = await fetch(`${BACKEND_URL}/reports/${framework.toLowerCase()}/export?${query.toString()}`, {
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || 'Failed to export report')
      }
      const payload = await response.json()
      setDownload(payload)
      setMessage(`Generated ${framework} export (${payload.rows_exported} rows).`)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-grid">
      <SectionCard title="Reports" subtitle="Generate aligned reporting exports for LPs and internal committees">
        {user?.role !== 'manager' ? (
          <p className="action-message">CSV/PDF exports are available to manager role only in V1.</p>
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
              <option value="csv">CSV</option>
              <option value="pdf">PDF</option>
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
