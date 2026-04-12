import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import SectionCard from '../components/SectionCard'
import useDashboardData from '../hooks/useDashboardData'

const reportFrameworks = ['EDCI', 'SFDR', 'Custom ESG']

export default function ReportsPage() {
  const { user } = useOutletContext()
  const { companies } = useDashboardData(user)
  const [framework, setFramework] = useState(reportFrameworks[0])
  const [portfolio, setPortfolio] = useState('All Portfolio Companies')
  const [period, setPeriod] = useState('FY2026')
  const [format, setFormat] = useState('PDF')
  const [message, setMessage] = useState('')

  const portfolios = useMemo(() => ['All Portfolio Companies', ...companies.map((c) => c.name)], [companies])

  return (
    <div className="page-grid">
      <SectionCard title="Reports" subtitle="Generate aligned reporting exports for LPs and internal committees">
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

        <form className="report-form" onSubmit={(event) => {
          event.preventDefault()
          setMessage(`Generated ${framework} report for ${portfolio} (${period}) in ${format}.`)
        }}>
          <label>
            <span>Select portfolio/company</span>
            <select value={portfolio} onChange={(event) => setPortfolio(event.target.value)}>
              {portfolios.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>

          <label>
            <span>Select time period</span>
            <select value={period} onChange={(event) => setPeriod(event.target.value)}>
              <option value="FY2026">FY2026</option>
              <option value="FY2025">FY2025</option>
              <option value="Last 12 Months">Last 12 Months</option>
            </select>
          </label>

          <label>
            <span>Export format</span>
            <select value={format} onChange={(event) => setFormat(event.target.value)}>
              <option value="PDF">PDF</option>
              <option value="Excel">Excel</option>
            </select>
          </label>

          <button className="button" type="submit">Generate Report</button>
        </form>

        {message ? <p className="action-message">{message}</p> : null}
      </SectionCard>
    </div>
  )
}
