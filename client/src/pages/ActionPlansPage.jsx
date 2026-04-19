import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData from '../hooks/useDashboardData'
import { UI_LABELS } from '../lib/uiLabels'

export default function ActionPlansPage() {
  const { user } = useOutletContext()
  const { companies } = useDashboardData(user)
  const [status, setStatus] = useState('All')
  const [pillar, setPillar] = useState('All')
  const [company, setCompany] = useState('All')

  const actionPlanRows = useMemo(() => {
    return companies.flatMap((c) => 
      (c.action_plans || []).map((ap) => ({
        id: ap.id,
        company: c.name,
        action: ap.initiative_name,
        owner: ap.assigned_owner,
        deadline: ap.target_completion_date,
        status: ap.status,
        pillar: 'General'
      }))
    )
  }, [companies])

  const options = useMemo(() => ({
    status: ['All', ...new Set(actionPlanRows.map((row) => row.status))],
    pillars: ['All', ...new Set(actionPlanRows.map((row) => row.pillar))],
    companies: ['All', ...new Set(actionPlanRows.map((row) => row.company))],
  }), [])

  const filteredRows = useMemo(() => {
    return actionPlanRows.filter((row) => {
      const statusMatch = status === 'All' || row.status === status
      const pillarMatch = pillar === 'All' || row.pillar === pillar
      const companyMatch = company === 'All' || row.company === company
      return statusMatch && pillarMatch && companyMatch
    })
  }, [company, pillar, status])

  const columns = [
    { key: 'company', label: 'Company', sortable: true },
    { key: 'action', label: 'Action', sortable: true },
    { key: 'owner', label: 'Owner', sortable: true },
    { key: 'deadline', label: 'Deadline', sortable: true },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
  ]

  return (
    <div className="page-grid">
      <SectionCard title={UI_LABELS.pages.actionPlans.title} subtitle={UI_LABELS.pages.actionPlans.subtitle}>
        <div className="filter-bar sticky">
          <label>
            <span>Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              {options.status.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>

          <label>
            <span>ESG Pillar</span>
            <select value={pillar} onChange={(event) => setPillar(event.target.value)}>
              {options.pillars.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>

          <label>
            <span>Company</span>
            <select value={company} onChange={(event) => setCompany(event.target.value)}>
              {options.companies.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>
        </div>

        <DataTable columns={columns} rows={filteredRows} pageSize={10} />
      </SectionCard>
    </div>
  )
}
