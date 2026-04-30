import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import SectionCard from '../components/SectionCard'
import DataTable from '../components/DataTable'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

export default function AnomalyIntelPage() {
  const { user } = useOutletContext()
  const [summary, setSummary] = useState([])
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
        let companyJson = { items: [] }
        if (String(user?.role || '').toLowerCase() === 'company') {
          const companyRes = await fetch(`${BACKEND_URL}/company/anomalies`, { headers })
          if (companyRes.ok) companyJson = await companyRes.json()
        }
        if (!cancelled) {
          setSummary(Array.isArray(summaryJson.items) ? summaryJson.items : [])
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

  const rows = useMemo(
    () =>
      summary.map((item, index) => ({
        id: index + 1,
        company_name: item.company_name || 'Company',
        severity: item.severity || 'info',
        issue: item.issue_description || item.title || 'Issue',
      })),
    [summary],
  )

  const companyRows = useMemo(
    () =>
      companyItems.map((item, index) => ({
        id: index + 1,
        field_name: item.field_name || 'Field',
        severity: item.severity || 'info',
        issue: item.issue_description || 'Issue',
      })),
    [companyItems],
  )

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
      <SectionCard title="Portfolio Anomaly Summary" subtitle="Cross-portfolio validation flags">
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
