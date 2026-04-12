import { useMemo } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData from '../hooks/useDashboardData'

export default function AlertsRisksPage() {
  const { user } = useOutletContext()
  const { companies } = useDashboardData(user)

  const riskIssueRows = useMemo(() => {
    return companies.flatMap(company => 
      (company.validation_flags || []).map(flag => ({
        id: flag.id,
        company: company.name,
        issue: flag.issue_description,
        severity: flag.severity,
      }))
    )
  }, [companies])

  const alertCards = useMemo(() => {
    let high = 0, medium = 0, low = 0;
    riskIssueRows.forEach(row => {
      if (row.severity === 'High') high++;
      else if (row.severity === 'Medium') medium++;
      else low++;
    })
    return [
      { title: 'High Severity Flags', value: high, severity: 'critical' },
      { title: 'Medium Severity Flags', value: medium, severity: 'warning' },
      { title: 'Total Active Issues', value: riskIssueRows.length, severity: 'info' }
    ]
  }, [riskIssueRows])

  const columns = [
    { key: 'company', label: 'Company', sortable: true },
    { key: 'issue', label: 'Issue', sortable: true },
    { key: 'severity', label: 'Severity', sortable: true, render: (row) => <StatusBadge value={row.severity} /> },
    { key: 'action', label: 'Action', render: () => <button className="button">Open</button> },
  ]

  return (
    <div className="page-grid">
      <section className="alert-card-grid">
        {alertCards.map((card) => (
          <article key={card.title} className={`alert-card ${card.severity}`}>
            <p>{card.title}</p>
            <strong>{card.value}</strong>
          </article>
        ))}
      </section>

      <SectionCard title="Risk Register" subtitle="Operational risk and compliance alerts requiring follow-up">
        <DataTable columns={columns} rows={riskIssueRows} pageSize={10} />
      </SectionCard>
    </div>
  )
}
