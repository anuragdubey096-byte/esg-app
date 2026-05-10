import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import SectionCard from '../components/SectionCard'
import DataTable from '../components/DataTable'
import StatusBadge from '../components/StatusBadge'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL
const SEVERITY_ORDER = { Critical: 4, High: 3, Medium: 2, Low: 1, Info: 0 }
const SEVERITY_COLORS = {
  Critical: '#dc2626',
  High: '#ef4444',
  Medium: '#f59e0b',
  Low: '#16a34a',
  Info: '#2563eb',
}

function titleCase(value) {
  return String(value || '')
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((word) => {
      const lower = word.toLowerCase()
      if (lower === 'ghg' || lower === 'esg' || lower === 'trifr') return lower.toUpperCase()
      return lower.charAt(0).toUpperCase() + lower.slice(1)
    })
    .join(' ')
}

function normalizeSeverity(value) {
  const normalized = titleCase(value)
  return SEVERITY_ORDER[normalized] !== undefined ? normalized : 'Info'
}

function formatNumber(value, digits = 1) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'n/a'
  return numeric.toLocaleString(undefined, { maximumFractionDigits: digits })
}

function getRemediationStatus(item) {
  return titleCase(item?.remediation?.status || 'No Plan')
}

function normalizeItem(item, index) {
  const severity = normalizeSeverity(item.severity)
  const remediationStatus = getRemediationStatus(item)
  return {
    ...item,
    id: `${item.type || 'anomaly'}-${item.id || index}`,
    company_name: item.company_name || `Company ${item.company_id || ''}`.trim(),
    field_label: item.field_label || titleCase(item.field_name || 'Metric'),
    severity,
    severityRank: SEVERITY_ORDER[severity] || 0,
    type: item.type || 'Anomaly',
    issue: item.issue_description || 'Review required.',
    remediationStatus,
    remediationAction: item?.remediation?.latest_action || 'No action plan linked',
  }
}

function buildCountOptions(rows, key) {
  return ['All', ...Array.from(new Set(rows.map((row) => row[key]).filter(Boolean))).sort()]
}

function RemediationCell({ row }) {
  return (
    <div className="anomaly-remediation-cell">
      <StatusBadge value={row.remediationStatus} />
      <span>{row.remediationAction}</span>
    </div>
  )
}

function MetricCell({ row }) {
  if (row.type !== 'Statistical Outlier') return <span>{row.field_label}</span>
  return (
    <div className="anomaly-metric-cell">
      <strong>{row.field_label}</strong>
      <span>
        {formatNumber(row.value, 2)} vs mean {formatNumber(row.portfolio_mean, 2)}
      </span>
    </div>
  )
}

export default function AnomalyIntelPage() {
  const { user } = useOutletContext()
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [severity, setSeverity] = useState('All')
  const [company, setCompany] = useState('All')
  const [type, setType] = useState('All')
  const [remediation, setRemediation] = useState('All')
  const [query, setQuery] = useState('')

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        const role = String(user?.role || '').toLowerCase()
        const headers = {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
          ...(user?.sessionToken ? { 'x-session-token': user.sessionToken } : {}),
        }
        const path = role === 'company' ? '/company/anomalies' : '/anomalies/summary'
        const response = await fetch(`${BACKEND_URL}${path}`, { headers })
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}))
          throw new Error(detail.detail || `Anomaly request failed (${response.status})`)
        }
        const json = await response.json()
        if (!cancelled) setPayload(json)
      } catch (requestError) {
        if (!cancelled) setError(requestError.message || 'Unable to load anomaly intelligence.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [user?.email, user?.role, user?.sessionToken])

  const rows = useMemo(
    () => (Array.isArray(payload?.items) ? payload.items : []).map(normalizeItem),
    [payload],
  )

  const options = useMemo(
    () => ({
      severities: ['All', 'Critical', 'High', 'Medium', 'Low'],
      companies: buildCountOptions(rows, 'company_name'),
      types: buildCountOptions(rows, 'type'),
      remediations: buildCountOptions(rows, 'remediationStatus'),
    }),
    [rows],
  )

  const filteredRows = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return rows.filter((row) => {
      const severityMatch = severity === 'All' || row.severity === severity
      const companyMatch = company === 'All' || row.company_name === company
      const typeMatch = type === 'All' || row.type === type
      const remediationMatch = remediation === 'All' || row.remediationStatus === remediation
      const searchMatch = !needle || [
        row.company_name,
        row.field_label,
        row.issue,
        row.sector,
        row.remediationAction,
      ].some((value) => String(value || '').toLowerCase().includes(needle))
      return severityMatch && companyMatch && typeMatch && remediationMatch && searchMatch
    })
  }, [company, query, remediation, rows, severity, type])

  const filteredOutlierRows = useMemo(
    () => filteredRows.filter((row) => row.type === 'Statistical Outlier'),
    [filteredRows],
  )

  const filteredValidationRows = useMemo(
    () => filteredRows.filter((row) => row.type !== 'Statistical Outlier'),
    [filteredRows],
  )

  const severityCards = useMemo(() => {
    const counts = rows.reduce((acc, row) => {
      acc[row.severity] = (acc[row.severity] || 0) + 1
      return acc
    }, {})
    return ['Critical', 'High', 'Medium', 'Low'].map((label) => ({
      label,
      value: counts[label] || 0,
      color: SEVERITY_COLORS[label],
    }))
  }, [rows])

  const chartData = useMemo(() => {
    const fields = new Map()
    filteredRows.forEach((row) => fields.set(row.field_label, (fields.get(row.field_label) || 0) + 1))
    return Array.from(fields.entries())
      .map(([field, count]) => ({ field, count }))
      .sort((left, right) => right.count - left.count)
      .slice(0, 8)
  }, [filteredRows])

  const remediationChartData = useMemo(() => {
    const statuses = new Map()
    filteredRows.forEach((row) => statuses.set(row.remediationStatus, (statuses.get(row.remediationStatus) || 0) + 1))
    return Array.from(statuses.entries()).map(([status, count]) => ({ status, count }))
  }, [filteredRows])

  const watchlistRows = useMemo(() => {
    const companies = new Map()
    filteredRows.forEach((row) => {
      const current = companies.get(row.company_name) || {
        id: `watch-${row.company_name}`,
        company_name: row.company_name,
        sector: row.sector || 'n/a',
        count: 0,
        maxSeverity: row.severity,
        remediationStatus: row.remediationStatus,
      }
      current.count += 1
      if (row.severityRank > (SEVERITY_ORDER[current.maxSeverity] || 0)) current.maxSeverity = row.severity
      companies.set(row.company_name, current)
    })
    return Array.from(companies.values()).sort((left, right) => right.count - left.count).slice(0, 8)
  }, [filteredRows])

  const columns = [
    { key: 'company_name', label: 'Company', sortable: true },
    { key: 'type', label: 'Type', sortable: true },
    { key: 'field_label', label: 'Metric', sortable: true, render: (row) => <MetricCell row={row} /> },
    { key: 'severity', label: 'Severity', sortable: true, sortAccessor: (row) => row.severityRank, render: (row) => <StatusBadge value={row.severity} /> },
    { key: 'z_score', label: 'Z-Score', sortable: true, render: (row) => formatNumber(row.z_score, 2) },
    { key: 'issue', label: 'Issue', sortable: false },
    { key: 'remediationStatus', label: 'Remediation', sortable: true, render: (row) => <RemediationCell row={row} /> },
  ]

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="Anomaly Intelligence" subtitle="Loading anomaly feed...">
          <p>Loading data from backend.</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="Anomaly Intelligence" subtitle="Live data unavailable">
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid anomaly-page">
      <section className="anomaly-severity-grid">
        {severityCards.map((card) => (
          <article key={card.label} className="anomaly-severity-card" style={{ borderTopColor: card.color }}>
            <p>{card.label}</p>
            <strong>{card.value}</strong>
          </article>
        ))}
      </section>

      <SectionCard title="Portfolio Anomaly Controls" subtitle={`Cycle ${payload?.cycle_year || 'current'} | ${filteredRows.length} active rows`}>
        <div className="filter-bar anomaly-filter-bar">
          <label>
            <span>Severity</span>
            <select value={severity} onChange={(event) => setSeverity(event.target.value)}>
              {options.severities.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label>
            <span>Company</span>
            <select value={company} onChange={(event) => setCompany(event.target.value)}>
              {options.companies.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label>
            <span>Type</span>
            <select value={type} onChange={(event) => setType(event.target.value)}>
              {options.types.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label>
            <span>Remediation</span>
            <select value={remediation} onChange={(event) => setRemediation(event.target.value)}>
              {options.remediations.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
          <label className="anomaly-search-control">
            <span>Search</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Company, metric, issue" />
          </label>
        </div>
      </SectionCard>

      <section className="two-col-grid">
        <SectionCard title="Anomaly Concentration" subtitle="Top metrics by filtered anomaly count">
          <div className="anomaly-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 14, left: 0, bottom: 28 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="field" angle={-18} textAnchor="end" height={54} interval={0} tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} width={30} />
                <Tooltip />
                <Bar dataKey="count" fill="#2563eb" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Remediation Coverage" subtitle="Open action-plan status across filtered anomalies">
          <div className="anomaly-chart compact">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={remediationChartData} dataKey="count" nameKey="status" outerRadius={92} label>
                  {remediationChartData.map((entry, index) => (
                    <Cell key={entry.status} fill={['#2563eb', '#0f766e', '#f59e0b', '#dc2626', '#64748b'][index % 5]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="mini-legend">
            {remediationChartData.map((entry, index) => (
              <li key={entry.status}>
                <span style={{ background: ['#2563eb', '#0f766e', '#f59e0b', '#dc2626', '#64748b'][index % 5] }} />
                {entry.status}: {entry.count}
              </li>
            ))}
          </ul>
        </SectionCard>
      </section>

      <SectionCard title="Company Watchlist" subtitle="Highest anomaly concentration by company">
        <DataTable
          columns={[
            { key: 'company_name', label: 'Company', sortable: true },
            { key: 'sector', label: 'Sector', sortable: true },
            { key: 'count', label: 'Anomalies', sortable: true },
            { key: 'maxSeverity', label: 'Max Severity', sortable: true, render: (row) => <StatusBadge value={row.maxSeverity} /> },
            { key: 'remediationStatus', label: 'Remediation', sortable: true, render: (row) => <StatusBadge value={row.remediationStatus} /> },
          ]}
          rows={watchlistRows}
          pageSize={8}
          emptyMessage="No watchlist companies found."
        />
      </SectionCard>

      <SectionCard title="Z-Score Outliers" subtitle={`${filteredOutlierRows.length} statistical outliers detected`}>
        <DataTable
          columns={columns.filter((column) => column.key !== 'type')}
          rows={filteredOutlierRows}
          pageSize={8}
          emptyMessage="No statistical outliers found."
        />
      </SectionCard>

      <SectionCard title="Validation Flag Register" subtitle={`${filteredValidationRows.length} validation and variance flags`}>
        <DataTable
          columns={columns.filter((column) => column.key !== 'z_score')}
          rows={filteredValidationRows}
          pageSize={10}
          emptyMessage="No anomalies match the current filters."
        />
      </SectionCard>
    </div>
  )
}
