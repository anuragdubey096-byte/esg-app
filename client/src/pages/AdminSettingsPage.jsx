import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData from '../hooks/useDashboardData'
import { API_BASE_URL } from '../lib/api'

const adminSettingsTabs = ['Data Collection Cycles', 'Users']
const BACKEND_URL = API_BASE_URL

export default function AdminSettingsPage() {
  const { user } = useOutletContext()
  const { cycles, refresh } = useDashboardData(user)
  const [activeTab, setActiveTab] = useState(adminSettingsTabs[0])
  const [message, setMessage] = useState('')

  const updateCycleStatus = async (cycleId, status) => {
    setMessage('Updating cycle status...')
    try {
      const response = await fetch(`${BACKEND_URL}/cycles/${cycleId}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
        body: JSON.stringify({ status }),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || 'Failed to update cycle status')
      }
      setMessage(`Cycle updated to ${status}.`)
      refresh()
    } catch (error) {
      setMessage(error.message)
    }
  }

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
      rows: cycles.map((cycle) => ({
        id: cycle.id,
        cycle: `FY${cycle.cycle_year}`,
        openDate: cycle.submission_open_date,
        deadline: cycle.submission_deadline,
        status: cycle.status,
      })),
      columns: [
        { key: 'cycle', label: 'Cycle', sortable: true },
        { key: 'openDate', label: 'Open Date', sortable: true },
        { key: 'deadline', label: 'Deadline', sortable: true },
        { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
        {
          key: 'actions',
          label: 'Actions',
          render: (row) => (
            <div className="flex items-center gap-3">
              <button
                type="button"
                className="text-xs text-green-700 font-bold uppercase tracking-wide hover:underline"
                onClick={() => updateCycleStatus(row.id, 'active')}
              >
                Activate
              </button>
              <button
                type="button"
                className="text-xs text-red-700 font-bold uppercase tracking-wide hover:underline"
                onClick={() => updateCycleStatus(row.id, 'closed')}
              >
                Close
              </button>
              <button
                type="button"
                className="text-xs text-slate-700 font-bold uppercase tracking-wide hover:underline"
                onClick={() => updateCycleStatus(row.id, 'draft')}
              >
                Draft
              </button>
            </div>
          ),
        },
      ],
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
        {message ? <p className="action-message">{message}</p> : null}
      </SectionCard>
    </div>
  )
}
