import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData from '../hooks/useDashboardData'
import { API_BASE_URL } from '../lib/api'
import { Button } from '../components/ui'

const adminSettingsTabs = ['Data Collection Cycles', 'Users']
export default function AdminSettingsPage() {
  const { user } = useOutletContext()
  const { cycles, refresh } = useDashboardData(user)
  const [activeTab, setActiveTab] = useState(adminSettingsTabs[0])
  const [message, setMessage] = useState('')
  const [users, setUsers] = useState([])

  useEffect(() => {
    if (activeTab !== 'Users') return
    if (user?.role !== 'manager') return
    const run = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/users`, {
          headers: {
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          },
        })
        if (!response.ok) throw new Error('Failed to load users')
        const payload = await response.json()
        setUsers(Array.isArray(payload) ? payload : [])
      } catch (error) {
        setUsers([])
        setMessage(error.message)
      }
    }
    run()
  }, [activeTab, user?.email, user?.role])

  const updateCycleStatus = async (cycleId, status) => {
    setMessage('Updating cycle status...')
    try {
      const response = await fetch(`${API_BASE_URL}/cycles/${cycleId}/status`, {
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
        rows: users.map((item) => ({
          id: item.id,
          name: item.name,
          role: item.role,
          email: item.email,
          status: 'Active',
        })),
        columns: [
          { key: 'name', label: 'Name', sortable: true },
          { key: 'role', label: 'Role', sortable: true },
          { key: 'email', label: 'Email', sortable: true },
          { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
        ],
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
              <Button type="button" className="text-xs text-green-700 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => updateCycleStatus(row.id, 'active')}>
                Activate
              </Button>
              <Button type="button" className="text-xs text-red-700 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => updateCycleStatus(row.id, 'closed')}>
                Close
              </Button>
              <Button type="button" className="text-xs text-slate-700 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => updateCycleStatus(row.id, 'draft')}>
                Draft
              </Button>
            </div>
          ),
        },
      ],
    }
  }, [activeTab, cycles, users])

  return (
    <div className="page-grid">
      <SectionCard
        title="Admin Settings"
        subtitle="Manage access, templates, rules, and data governance controls"
        actions={
          <div className="tab-row">
            {adminSettingsTabs.map((tab) => (
              <Button key={tab} type="button" className={`tab-button ${tab === activeTab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>
                {tab}
              </Button>
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

