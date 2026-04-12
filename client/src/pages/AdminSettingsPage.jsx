import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData from '../hooks/useDashboardData'

const adminSettingsTabs = ['Data Collection Cycles', 'Users']

export default function AdminSettingsPage() {
  const { user } = useOutletContext()
  const { cycles } = useDashboardData(user)
  const [activeTab, setActiveTab] = useState(adminSettingsTabs[0])

  const current = useMemo(() => {
    if (activeTab === 'Users') {
      return {
        rows: user ? [{ id: user.id, name: user.name, role: user.role, email: user.email, status: 'Active' }] : [],
        columns: [
          { key: 'name', label: 'Name', sortable: true },
          { key: 'role', label: 'Role', sortable: true },
          { key: 'email', label: 'Email', sortable: true },
          { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
        ]
      }
    }
    return {
      rows: cycles.map(c => ({
        id: c.id,
        cycle: `FY${c.cycle_year}`,
        openDate: c.submission_open_date,
        deadline: c.submission_deadline,
        status: c.status
      })),
      columns: [
        { key: 'cycle', label: 'Cycle', sortable: true },
        { key: 'openDate', label: 'Open Date', sortable: true },
        { key: 'deadline', label: 'Deadline', sortable: true },
        { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
      ]
    }
  }, [activeTab, cycles, user])

  return (
    <div className="page-grid">
      <SectionCard
        title="Admin Settings"
        subtitle="Manage access, templates, rules, and data governance controls"
        actions={
          <div className="tab-row">
            {adminSettingsTabs.map((tab) => (
              <button
                key={tab}
                type="button"
                className={`tab-button ${tab === activeTab ? 'active' : ''}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
        }
      >
        <DataTable columns={current.columns} rows={current.rows} pageSize={8} />
      </SectionCard>
    </div>
  )
}
