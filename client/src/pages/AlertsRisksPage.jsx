import { useMemo } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import AnomalySummaryCard from '../components/AnomalySummaryCard'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useAnomalySummary from '../hooks/useAnomalySummary'
import useDashboardData from '../hooks/useDashboardData'
import { Button } from '../components/ui'
import { UI_LABELS } from '../lib/uiLabels'

export default function AlertsRisksPage() {
  const { user } = useOutletContext()
  const navigate = useNavigate()
  const { companies } = useDashboardData(user)
  const anomalySummary = useAnomalySummary({ user, enabled: Boolean(user) })

  const riskIssueRows = useMemo(() => {
    return companies.flatMap(company => 
      (company.validation_flags || []).map(flag => ({
        id: flag.id,
        companyId: company.id,
        company: company.name,
        fieldName: flag.field_name,
        issue: flag.issue_description,
        severity: flag.severity,
      }))
    )
  }, [companies])

  const anomalyRows = useMemo(() => {
    return (anomalySummary.data?.items || []).map((item) => ({
      id: item.id,
      companyId: item.company_id,
      company: item.company_name || 'Portfolio',
      fieldName: item.metric_name,
      issue: item.rationale,
      severity: item.severity,
    }))
  }, [anomalySummary.data?.items])

  const combinedRows = anomalyRows.length ? anomalyRows : riskIssueRows

  const alertCards = useMemo(() => {
    let high = 0, medium = 0, low = 0;
    combinedRows.forEach(row => {
      if (row.severity === 'High') high++;
      else if (row.severity === 'high') high++;
      else if (row.severity === 'Medium') medium++;
      else if (row.severity === 'medium') medium++;
      else low++;
    })
    return [
      { title: 'High Severity Flags', value: high, severity: 'critical' },
      { title: 'Medium Severity Flags', value: medium, severity: 'warning' },
      { title: 'Total Active Issues', value: combinedRows.length, severity: 'info' }
    ]
  }, [combinedRows])

  const columns = [
    { key: 'company', label: 'Company', sortable: true },
    { key: 'fieldName', label: 'Field', sortable: true },
    { key: 'issue', label: 'Issue', sortable: true },
    { key: 'severity', label: 'Severity', sortable: true, render: (row) => <StatusBadge value={row.severity} /> },
    {
      key: 'action',
      label: 'Action',
      render: (row) => (
        user?.role === 'manager' && row.companyId ? (
          <Button
            type="button"
            className="button"
            onClick={() => navigate(`/review-hub?companyId=${row.companyId}&field=${encodeURIComponent(row.fieldName || '')}`)}
          >
            Open
          </Button>
        ) : (
          <span className="text-xs text-slate-500">Review only</span>
        )
      ),
    },
  ]

  return (
    <div className="page-grid">
      <AnomalySummaryCard
        title="Anomaly Watchlist"
        subtitle="Approved-data issues surfaced by the anomaly engine"
        data={anomalySummary.data}
        loading={anomalySummary.loading}
        error={anomalySummary.error}
        maxItems={4}
      />

      <section className="alert-card-grid">
        {alertCards.map((card) => (
          <article key={card.title} className={`alert-card ${card.severity}`}>
            <p>{card.title}</p>
            <strong>{card.value}</strong>
          </article>
        ))}
      </section>

      <SectionCard title={UI_LABELS.pages.alertsRisks.title} subtitle={UI_LABELS.pages.alertsRisks.subtitle}>
        <DataTable columns={columns} rows={combinedRows} pageSize={10} />
      </SectionCard>
    </div>
  )
}

