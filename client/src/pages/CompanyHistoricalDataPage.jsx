import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import { API_BASE_URL } from '../lib/api'
import { UI_LABELS } from '../lib/uiLabels'

function parseSubmissionPayload(submission) {
  if (!submission?.esg_data) return null
  try {
    const parsed = JSON.parse(submission.esg_data)
    return typeof parsed === 'object' && parsed ? parsed : null
  } catch {
    return null
  }
}

function computeYoy(current, previous) {
  const currentNum = Number(current)
  const previousNum = Number(previous)
  if (!Number.isFinite(currentNum) || !Number.isFinite(previousNum) || previousNum === 0) return null
  return Number((((currentNum - previousNum) / previousNum) * 100).toFixed(2))
}

export default function CompanyHistoricalDataPage() {
  const { user } = useOutletContext()
  const [company, setCompany] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        setLoading(true)
        const response = await fetch(`${API_BASE_URL}/dashboard/company/${user?.id}`, {
          headers: {
            'x-user-role': user?.role || 'company',
            'x-user-email': user?.email || '',
          },
        })
        if (!response.ok) {
          throw new Error(`Failed to load historical submissions (${response.status})`)
        }
        const payload = await response.json()
        setCompany(Array.isArray(payload) ? payload[0] : null)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchHistory()
  }, [user?.email, user?.id, user?.role])

  const rows = useMemo(() => {
    if (!company?.submissions?.length) return []
    const submissions = [...company.submissions].sort((a, b) => {
      const aPayload = parseSubmissionPayload(a) || {}
      const bPayload = parseSubmissionPayload(b) || {}
      const aYear = Number(aPayload.reporting_year || 0)
      const bYear = Number(bPayload.reporting_year || 0)
      if (aYear !== bYear) return bYear - aYear
      return (b.id || 0) - (a.id || 0)
    })

    return submissions.map((submission, index) => {
      const payload = parseSubmissionPayload(submission) || {}
      const previous = submissions[index + 1] ? parseSubmissionPayload(submissions[index + 1]) || {} : null
      const totalGhg = payload.total_ghg_emissions
      const prevTotalGhg = previous?.total_ghg_emissions
      const ghgYoy = computeYoy(totalGhg, prevTotalGhg)

      return {
        id: submission.id,
        reportingYear: payload.reporting_year || `Cycle ${submission.cycle_id || '-'}`,
        status: submission.status || 'unknown',
        cycle: submission.cycle_id || '-',
        totalGhg: totalGhg ?? '-',
        previousTotalGhg: prevTotalGhg ?? '-',
        ghgYoy: ghgYoy === null ? '-' : `${ghgYoy > 0 ? '+' : ''}${ghgYoy}%`,
        trifr: payload.trifr ?? '-',
        femaleLeadership: payload.female_leadership_representation_percent ?? '-',
      }
    })
  }, [company])

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.companyHistorical.title} subtitle={UI_LABELS.pages.companyHistorical.loadingSubtitle}>
          <p>{UI_LABELS.common.loadingDataFromBackend}</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.companyHistorical.title} subtitle={UI_LABELS.pages.companyHistorical.errorSubtitle}>
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <SectionCard
        title={UI_LABELS.pages.companyHistorical.title}
        subtitle={company ? `${company.name} - previous submissions and year-on-year reference` : UI_LABELS.pages.companyHistorical.noDataSubtitle}
      >
        <DataTable
          columns={[
            { key: 'reportingYear', label: 'Reporting Year', sortable: true },
            { key: 'status', label: 'Status', sortable: true },
            { key: 'cycle', label: 'Cycle', sortable: true },
            { key: 'totalGhg', label: 'Current Total GHG', sortable: true },
            { key: 'previousTotalGhg', label: 'Previous Total GHG', sortable: true },
            { key: 'ghgYoy', label: 'YoY GHG Change', sortable: true },
            { key: 'trifr', label: 'TRIFR', sortable: true },
            { key: 'femaleLeadership', label: 'Female Leadership %', sortable: true },
          ]}
          rows={rows}
          pageSize={8}
          emptyMessage="No historical submissions available yet."
        />
      </SectionCard>
    </div>
  )
}
