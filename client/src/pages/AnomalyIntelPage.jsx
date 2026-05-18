import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import SectionCard from '../components/SectionCard'
import DataTable from '../components/DataTable'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

function normalizeSeverity(value) {
  return String(value || '').trim().toLowerCase()
}

function humanizeLabel(value) {
  const normalized = String(value || '').trim().toLowerCase()
  if (!normalized) return 'Unknown'
  return normalized
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(' ')
}

function severityLabel(value) {
  return humanizeLabel(normalizeSeverity(value))
}

function severityRank(value) {
  const normalized = normalizeSeverity(value)
  if (normalized === 'critical') return 5
  if (normalized === 'high') return 4
  if (normalized === 'medium') return 3
  if (normalized === 'low') return 2
  if (normalized === 'warning') return 1
  return 0
}

function severityCardTone(value) {
  const normalized = normalizeSeverity(value)
  if (normalized === 'critical' || normalized === 'high') return 'critical'
  if (normalized === 'medium' || normalized === 'warning') return 'warning'
  return 'info'
}

export default function AnomalyIntelPage() {
  const { user } = useOutletContext()
  const [summaryPayload, setSummaryPayload] = useState({ items: [], severity_counts: {} })
  const [companyItems, setCompanyItems] = useState([])
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
        const summaryRes = await fetch(`${BACKEND_URL}/anomalies/summary`, { headers })
        if (!summaryRes.ok) {
          const detail = await summaryRes.json().catch(() => ({}))
          throw new Error(detail.detail || `Summary request failed (${summaryRes.status})`)
        }
        const summaryJson = await summaryRes.json()
        const normalizedSummary = summaryJson && typeof summaryJson === 'object' ? summaryJson : { items: [] }
        let companyJson = { items: [] }
        if (String(user?.role || '').toLowerCase() === 'company') {
          const companyRes = await fetch(`${BACKEND_URL}/company/anomalies`, { headers })
          if (companyRes.ok) companyJson = await companyRes.json()
        }
        if (!cancelled) {
          setSummaryPayload(normalizedSummary)
          setCompanyItems(Array.isArray(companyJson.items) ? companyJson.items : [])
        }
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
  }, [user?.email, user?.role])

  const summaryItems = useMemo(() => (Array.isArray(summaryPayload?.items) ? summaryPayload.items : []), [summaryPayload])

  const rows = useMemo(
    () =>
      summaryItems.map((item, index) => ({
        id: index + 1,
        company_name:
          item.company_name ||
          item.company_code ||
          (item.company_id ? `Company #${item.company_id}` : 'Company'),
        severity: severityLabel(item.severity),
        issue: item.issue_description || item.field_name || item.title || 'Issue',
      })),
    [summaryItems],
  )

  const companyRows = useMemo(
    () =>
      companyItems.map((item, index) => ({
        id: index + 1,
        field_name: item.field_name || 'Field',
        severity: severityLabel(item.severity),
        issue: item.issue_description || 'Issue',
      })),
    [companyItems],
  )

  const summaryCards = useMemo(() => {
    const counts = summaryPayload?.severity_counts && typeof summaryPayload.severity_counts === 'object'
      ? summaryPayload.severity_counts
      : {}
    const dynamicCards = Object.entries(counts)
      .map(([key, value]) => ({
        key,
        label: severityLabel(key),
        value: Number(value) || 0,
      }))
      .filter((item) => item.value > 0)
      .sort((a, b) => severityRank(b.key) - severityRank(a.key) || b.value - a.value)
      .slice(0, 2)
      .map((item) => ({
        title: `${item.label} Severity`,
        value: item.value,
        severity: severityCardTone(item.key),
      }))

    dynamicCards.push({
      title: 'Total Active Issues',
      value: rows.length,
      severity: rows.length > 0 ? 'warning' : 'info',
    })
    return dynamicCards
  }, [rows.length, summaryPayload?.severity_counts])

  const flagTypeCards = useMemo(() => {
    const counts = summaryPayload?.flag_type_counts && typeof summaryPayload.flag_type_counts === 'object'
      ? summaryPayload.flag_type_counts
      : {}
    const cards = Object.entries(counts)
      .map(([key, value]) => ({
        key,
        title: humanizeLabel(key),
        value: Number(value) || 0,
      }))
      .filter((item) => item.value > 0)
      .sort((a, b) => b.value - a.value || a.title.localeCompare(b.title))
      .slice(0, 3)
      .map((item) => ({
        title: `${item.title} Flags`,
        value: item.value,
        severity: item.value > 0 ? 'info' : 'warning',
      }))

    if (cards.length === 0) {
      cards.push({
        title: 'No Flag Types',
        value: 0,
        severity: 'info',
      })
    }
    return cards
  }, [summaryPayload?.flag_type_counts])

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
    <div className="page-grid">
      <section className="alert-card-grid">
        {summaryCards.map((card) => (
          <article key={card.title} className={`alert-card ${card.severity}`}>
            <p>{card.title}</p>
            <strong>{card.value}</strong>
          </article>
        ))}
      </section>

      <section className="alert-card-grid">
        {flagTypeCards.map((card) => (
          <article key={card.title} className={`alert-card ${card.severity}`}>
            <p>{card.title}</p>
            <strong>{card.value}</strong>
          </article>
        ))}
      </section>

      <SectionCard
        title={summaryPayload.headline || 'Portfolio Anomaly Summary'}
        subtitle={summaryPayload.summary || 'Cross-portfolio validation flags'}
      >
        <DataTable
          columns={[
            { key: 'company_name', label: 'Company', sortable: true },
            { key: 'severity', label: 'Severity', sortable: true },
            { key: 'issue', label: 'Issue', sortable: false },
          ]}
          rows={rows}
          pageSize={10}
          emptyMessage="No portfolio anomalies found."
        />
      </SectionCard>

      {companyRows.length > 0 ? (
        <SectionCard title="Company Anomalies" subtitle="Company-scoped anomaly list">
          <DataTable
            columns={[
              { key: 'field_name', label: 'Field', sortable: true },
              { key: 'severity', label: 'Severity', sortable: true },
              { key: 'issue', label: 'Issue', sortable: false },
            ]}
            rows={companyRows}
            pageSize={8}
            emptyMessage="No company anomalies found."
          />
        </SectionCard>
      ) : null}
    </div>
  )
}
