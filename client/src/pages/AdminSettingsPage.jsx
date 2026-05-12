import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData from '../hooks/useDashboardData'
import { API_BASE_URL } from '../lib/api'

const adminSettingsTabs = [
  'Data Collection Cycles',
  'Users',
  'Permissions',
  'Security',
  'Contextual Help',
  'Audit Trail',
  'Onboarding',
]

const BACKEND_URL = API_BASE_URL
const defaultCycleForm = {
  cycle_year: '',
  submission_open_date: '',
  submission_deadline: '',
  extension_date: '',
  reminder_days_before_deadline: '14, 7, 1',
  private_equity_template: 'Standard Private Equity ESG Template',
  real_estate_template: 'Real Estate Asset ESG Template',
  debt_template: 'Debt Portfolio ESG Template',
  activate_on_create: true,
  carry_forward_prefill: true,
}

function toStatusLabel(status) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'active') return 'Active'
  if (normalized === 'closed') return 'Closed'
  if (normalized === 'draft') return 'Draft'
  return status || 'Draft'
}

function parseReminderDays(value) {
  const parsed = String(value || '')
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isInteger(item) && item >= 0)
  return [...new Set(parsed)]
}

export default function AdminSettingsPage() {
  const { user } = useOutletContext()
  const { cycles: dashboardCycles, refresh } = useDashboardData(user)
  const [activeTab, setActiveTab] = useState(adminSettingsTabs[0])
  const [message, setMessage] = useState('')
  const [adminCycles, setAdminCycles] = useState([])
  const [users, setUsers] = useState([])
  const [permissions, setPermissions] = useState([])
  const [sessionPolicies, setSessionPolicies] = useState([])
  const [policyDrafts, setPolicyDrafts] = useState({})
  const [ipAllowlist, setIpAllowlist] = useState([])
  const [ipEntry, setIpEntry] = useState({ ip_address: '', note: '' })
  const [helpContentItems, setHelpContentItems] = useState([])
  const [helpForm, setHelpForm] = useState({ cycle_id: '', field_key: '', title: '', body: '' })
  const [auditEvents, setAuditEvents] = useState([])
  const [onboardingRows, setOnboardingRows] = useState([])
  const [cloneTargetYears, setCloneTargetYears] = useState({})
  const [cycleForm, setCycleForm] = useState(defaultCycleForm)
  const [editingCycleId, setEditingCycleId] = useState(null)
  const [cycleSaving, setCycleSaving] = useState(false)
  const cycles = adminCycles.length ? adminCycles : dashboardCycles

  const authHeaders = useMemo(() => ({
    'x-user-role': user?.role || '',
    'x-user-email': user?.email || '',
    ...(user?.sessionToken ? { 'x-session-token': user.sessionToken } : {}),
  }), [user?.email, user?.role, user?.sessionToken])

  const requestJson = async (path, options = {}, defaultError = 'Request failed') => {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      ...options,
      headers: {
        ...authHeaders,
        ...(options.headers || {}),
      },
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.detail || defaultError)
    }
    return response.json().catch(() => ({}))
  }

  const updateCycleForm = (field, value) => {
    setCycleForm((current) => ({ ...current, [field]: value }))
  }

  const resetCycleForm = () => {
    setEditingCycleId(null)
    setCycleForm(defaultCycleForm)
  }

  const buildCyclePayload = ({ includeCreateOptions = false } = {}) => {
    const reminderDays = parseReminderDays(cycleForm.reminder_days_before_deadline)
    const cycleYear = Number(cycleForm.cycle_year)
    if (!Number.isInteger(cycleYear) || cycleYear <= 0) {
      throw new Error('Enter a valid cycle year.')
    }
    if (!cycleForm.submission_open_date || !cycleForm.submission_deadline) {
      throw new Error('Open date and deadline are required.')
    }

    const payload = {
      cycle_year: cycleYear,
      submission_open_date: cycleForm.submission_open_date,
      submission_deadline: cycleForm.submission_deadline,
      extension_date: cycleForm.extension_date || null,
      reminder_days_before_deadline: reminderDays,
      private_equity_template: cycleForm.private_equity_template.trim(),
      real_estate_template: cycleForm.real_estate_template.trim(),
      debt_template: cycleForm.debt_template.trim(),
      carry_forward_prefill: Boolean(cycleForm.carry_forward_prefill),
    }

    if (includeCreateOptions) {
      payload.activate_on_create = Boolean(cycleForm.activate_on_create)
    }
    return payload
  }

  const loadUsers = async () => {
    const data = await requestJson('/users', {}, 'Failed to load users')
    setUsers(Array.isArray(data) ? data : [])
  }

  const loadCycles = async () => {
    const data = await requestJson('/cycles', {}, 'Failed to load cycles')
    setAdminCycles(Array.isArray(data) ? data : [])
  }

  const loadPermissions = async () => {
    const data = await requestJson('/permissions', {}, 'Failed to load permissions')
    setPermissions(Array.isArray(data) ? data : [])
  }

  const loadSecurity = async () => {
    const [policies, ipRows] = await Promise.all([
      requestJson('/admin/security/session-policies', {}, 'Failed to load session policies'),
      requestJson('/admin/security/ip-allowlist', {}, 'Failed to load IP allowlist'),
    ])
    const policyRows = Array.isArray(policies) ? policies : []
    setSessionPolicies(policyRows)
    setIpAllowlist(Array.isArray(ipRows) ? ipRows : [])

    const drafts = {}
    policyRows.forEach((row) => {
      drafts[row.role] = {
        timeout_minutes: String(row.timeout_minutes),
        warn_before_minutes: String(row.warn_before_minutes),
        max_failed_logins: String(row.max_failed_logins),
        lockout_minutes: String(row.lockout_minutes),
      }
    })
    setPolicyDrafts(drafts)
  }

  const loadHelpContent = async () => {
    const selectedCycleId = helpForm.cycle_id || cycles[0]?.id || ''
    if (!selectedCycleId) {
      setHelpContentItems([])
      return
    }
    const data = await requestJson(`/help-content?cycle_id=${encodeURIComponent(selectedCycleId)}`, {}, 'Failed to load help content')
    setHelpContentItems(Array.isArray(data?.items) ? data.items : [])
  }

  const loadAuditEvents = async () => {
    const data = await requestJson('/audit/events?limit=150', {}, 'Failed to load audit events')
    setAuditEvents(Array.isArray(data?.items) ? data.items : [])
  }

  const loadOnboardingOverview = async () => {
    const data = await requestJson('/companies/onboarding/overview', {}, 'Failed to load onboarding overview')
    setOnboardingRows(Array.isArray(data?.items) ? data.items : [])
  }

  useEffect(() => {
    const normalizedRole = String(user?.role || '').toLowerCase()
    if (activeTab !== 'Data Collection Cycles') return
    if (normalizedRole !== 'manager' && normalizedRole !== 'admin') return

    loadCycles().catch((error) => setMessage(error.message))
  }, [activeTab, user?.email, user?.role, user?.sessionToken])

  useEffect(() => {
    const normalizedRole = String(user?.role || '').toLowerCase()
    if (normalizedRole !== 'manager' && normalizedRole !== 'admin') return

    const run = async () => {
      try {
        if (activeTab === 'Users') {
          await loadUsers()
        } else if (activeTab === 'Permissions') {
          await Promise.all([loadUsers(), loadPermissions()])
        } else if (activeTab === 'Security') {
          await loadSecurity()
        } else if (activeTab === 'Contextual Help') {
          await loadHelpContent()
        } else if (activeTab === 'Audit Trail') {
          await loadAuditEvents()
        } else if (activeTab === 'Onboarding') {
          await loadOnboardingOverview()
        }
      } catch (error) {
        setMessage(error.message)
      }
    }

    run()
  }, [activeTab, authHeaders, helpForm.cycle_id, user?.role])

  const updateCycleStatus = async (cycleId, status) => {
    setMessage('Updating cycle status...')
    try {
      await requestJson(
        `/cycles/${cycleId}/status`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status }),
        },
        'Failed to update cycle status'
      )
      setMessage(`Cycle updated to ${status}.`)
      refresh()
      await loadCycles()
    } catch (error) {
      setMessage(error.message)
    }
  }

  const cloneCycle = async (cycleId) => {
    const targetYear = Number(cloneTargetYears[cycleId])
    if (!Number.isFinite(targetYear)) {
      setMessage('Enter a valid target year before cloning.')
      return
    }

    setMessage('Cloning cycle...')
    try {
      await requestJson(
        `/cycles/${cycleId}/clone`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_year: targetYear }),
        },
        'Failed to clone cycle'
      )
      setMessage(`Cycle cloned to FY${targetYear} draft.`)
      refresh()
      await loadCycles()
    } catch (error) {
      setMessage(error.message)
    }
  }

  const saveCycle = async (event) => {
    event.preventDefault()
    setCycleSaving(true)
    setMessage(editingCycleId ? 'Saving cycle changes...' : 'Starting new cycle...')

    try {
      const payload = buildCyclePayload({ includeCreateOptions: !editingCycleId })
      if (editingCycleId) {
        await requestJson(
          `/cycles/${editingCycleId}`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          },
          'Failed to update cycle'
        )
        setMessage(`FY${payload.cycle_year} cycle updated.`)
      } else {
        await requestJson(
          '/cycles',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          },
          'Failed to start new cycle'
        )
        setMessage(`FY${payload.cycle_year} cycle ${payload.activate_on_create ? 'started' : 'created as draft'}.`)
      }
      resetCycleForm()
      refresh()
      await loadCycles()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setCycleSaving(false)
    }
  }

  const editCycle = (cycle) => {
    setEditingCycleId(cycle.id)
    setCycleForm({
      cycle_year: String(cycle.cycle_year || ''),
      submission_open_date: cycle.submission_open_date || '',
      submission_deadline: cycle.submission_deadline || '',
      extension_date: cycle.extension_date || '',
      reminder_days_before_deadline: Array.isArray(cycle.reminder_days_before_deadline)
        ? cycle.reminder_days_before_deadline.join(', ')
        : '14, 7, 1',
      private_equity_template: cycle.private_equity_template || defaultCycleForm.private_equity_template,
      real_estate_template: cycle.real_estate_template || defaultCycleForm.real_estate_template,
      debt_template: cycle.debt_template || defaultCycleForm.debt_template,
      activate_on_create: String(cycle.status || '').toLowerCase() === 'active',
      carry_forward_prefill: Boolean(cycle.carry_forward_prefill),
    })
    setActiveTab('Data Collection Cycles')
    setMessage(`Editing FY${cycle.cycle_year}.`)
  }

  const upsertPermission = async (userId, updates) => {
    const current = permissions.find((row) => row.user_id === userId) || {
      can_manage_security: false,
      can_view_portfolio_audit: false,
      can_clone_cycles: false,
      read_only_audit_scope: ['*'],
    }
    const payload = {
      can_manage_security: updates.can_manage_security ?? current.can_manage_security,
      can_view_portfolio_audit: updates.can_view_portfolio_audit ?? current.can_view_portfolio_audit,
      can_clone_cycles: updates.can_clone_cycles ?? current.can_clone_cycles,
      read_only_audit_scope: updates.read_only_audit_scope ?? current.read_only_audit_scope,
    }

    try {
      await requestJson(
        `/permissions/${userId}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
        'Failed to update permissions'
      )
      await loadPermissions()
      setMessage('Permission flags updated.')
    } catch (error) {
      setMessage(error.message)
    }
  }

  const savePolicy = async (role) => {
    const draft = policyDrafts[role]
    if (!draft) return

    try {
      await requestJson(
        `/admin/security/session-policies/${role}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            timeout_minutes: Number(draft.timeout_minutes),
            warn_before_minutes: Number(draft.warn_before_minutes),
            max_failed_logins: Number(draft.max_failed_logins),
            lockout_minutes: Number(draft.lockout_minutes),
          }),
        },
        'Failed to update session policy'
      )
      await loadSecurity()
      setMessage(`Session policy updated for ${role}.`)
    } catch (error) {
      setMessage(error.message)
    }
  }

  const addIp = async () => {
    if (!ipEntry.ip_address.trim()) {
      setMessage('IP address is required.')
      return
    }

    try {
      await requestJson(
        '/admin/security/ip-allowlist',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ip_address: ipEntry.ip_address.trim(), note: ipEntry.note.trim() }),
        },
        'Failed to add IP allowlist entry'
      )
      setIpEntry({ ip_address: '', note: '' })
      await loadSecurity()
      setMessage('IP allowlist updated.')
    } catch (error) {
      setMessage(error.message)
    }
  }

  const removeIp = async (entryId) => {
    try {
      await requestJson(`/admin/security/ip-allowlist/${entryId}`, { method: 'DELETE' }, 'Failed to remove IP entry')
      await loadSecurity()
      setMessage('IP entry removed.')
    } catch (error) {
      setMessage(error.message)
    }
  }

  const saveHelpContent = async () => {
    if (!helpForm.cycle_id || !helpForm.field_key.trim() || !helpForm.body.trim()) {
      setMessage('Cycle, field key, and help body are required.')
      return
    }

    try {
      await requestJson(
        `/admin/help-content/${helpForm.cycle_id}/${encodeURIComponent(helpForm.field_key.trim())}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: helpForm.title.trim(), body: helpForm.body.trim() }),
        },
        'Failed to save contextual help'
      )
      await loadHelpContent()
      setMessage('Help content updated.')
    } catch (error) {
      setMessage(error.message)
    }
  }

  const retriggerOnboarding = async (companyId) => {
    try {
      await requestJson(
        `/companies/${companyId}/onboarding/retrigger`,
        { method: 'POST' },
        'Failed to retrigger onboarding'
      )
      await loadOnboardingOverview()
      setMessage('Onboarding workflow reset for company.')
    } catch (error) {
      setMessage(error.message)
    }
  }

  const permissionRows = useMemo(() => {
    const managerUsers = users.filter((row) => row.role === 'manager')
    return managerUsers.map((manager) => {
      const row = permissions.find((item) => item.user_id === manager.id)
      return {
        id: manager.id,
        name: manager.name,
        email: manager.email,
        can_manage_security: Boolean(row?.can_manage_security),
        can_view_portfolio_audit: Boolean(row?.can_view_portfolio_audit),
        can_clone_cycles: Boolean(row?.can_clone_cycles),
        read_only_audit_scope: Array.isArray(row?.read_only_audit_scope) ? row.read_only_audit_scope.join(', ') : '*',
      }
    })
  }, [permissions, users])

  const cyclesTable = {
    rows: cycles.map((cycle) => ({
      id: cycle.id,
      cycle: `FY${cycle.cycle_year}`,
      cycle_year: cycle.cycle_year,
      submission_open_date: cycle.submission_open_date,
      submission_deadline: cycle.submission_deadline,
      extension_date: cycle.extension_date,
      reminder_days_before_deadline: cycle.reminder_days_before_deadline,
      private_equity_template: cycle.private_equity_template,
      real_estate_template: cycle.real_estate_template,
      debt_template: cycle.debt_template,
      carry_forward_prefill: cycle.carry_forward_prefill,
      openDate: cycle.submission_open_date,
      deadline: cycle.submission_deadline,
      status: cycle.status,
      statusLabel: toStatusLabel(cycle.status),
    })),
    columns: [
      { key: 'cycle', label: 'Cycle', sortable: true },
      { key: 'openDate', label: 'Open Date', sortable: true },
      { key: 'deadline', label: 'Deadline', sortable: true },
      { key: 'statusLabel', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.statusLabel} /> },
      {
        key: 'actions',
        label: 'Actions',
        render: (row) => (
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="text-xs text-blue-700 font-bold uppercase tracking-wide hover:underline" onClick={() => editCycle(row)}>Edit</button>
            <button type="button" className="text-xs text-green-700 font-bold uppercase tracking-wide hover:underline" onClick={() => updateCycleStatus(row.id, 'active')}>Activate</button>
            <button type="button" className="text-xs text-red-700 font-bold uppercase tracking-wide hover:underline" onClick={() => updateCycleStatus(row.id, 'closed')}>Close</button>
            <button type="button" className="text-xs text-slate-700 font-bold uppercase tracking-wide hover:underline" onClick={() => updateCycleStatus(row.id, 'draft')}>Draft</button>
            <input
              type="number"
              className="w-24 rounded-md border border-slate-300 px-2 py-1 text-xs"
              value={cloneTargetYears[row.id] || row.cycle_year + 1}
              onChange={(event) => setCloneTargetYears((current) => ({ ...current, [row.id]: event.target.value }))}
            />
            <button type="button" className="text-xs text-indigo-700 font-bold uppercase tracking-wide hover:underline" onClick={() => cloneCycle(row.id)}>Clone</button>
          </div>
        ),
      },
    ],
  }

  const usersTable = {
    rows: users.map((row) => ({
      id: row.id,
      name: row.name,
      role: row.role,
      email: row.email,
      status: 'Active',
    })),
    columns: [
      { key: 'name', label: 'Name', sortable: true },
      { key: 'role', label: 'Role', sortable: true },
      { key: 'email', label: 'Email', sortable: true },
      { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
    ],
  }

  const permissionsTable = {
    rows: permissionRows,
    columns: [
      { key: 'name', label: 'Name', sortable: true },
      { key: 'email', label: 'Email', sortable: true },
      {
        key: 'can_manage_security',
        label: 'Manage Security',
        render: (row) => (
          <input
            type="checkbox"
            checked={row.can_manage_security}
            onChange={(event) => upsertPermission(row.id, { can_manage_security: event.target.checked })}
          />
        ),
      },
      {
        key: 'can_view_portfolio_audit',
        label: 'View Audit',
        render: (row) => (
          <input
            type="checkbox"
            checked={row.can_view_portfolio_audit}
            onChange={(event) => upsertPermission(row.id, { can_view_portfolio_audit: event.target.checked })}
          />
        ),
      },
      {
        key: 'can_clone_cycles',
        label: 'Clone Cycles',
        render: (row) => (
          <input
            type="checkbox"
            checked={row.can_clone_cycles}
            onChange={(event) => upsertPermission(row.id, { can_clone_cycles: event.target.checked })}
          />
        ),
      },
      { key: 'read_only_audit_scope', label: 'Audit Scope', sortable: false },
    ],
  }

  const auditColumns = [
    { key: 'event_type', label: 'Event', sortable: true },
    { key: 'actor_email', label: 'Actor', sortable: true },
    { key: 'company_id', label: 'Company ID', sortable: true },
    { key: 'submission_id', label: 'Submission ID', sortable: true },
    { key: 'field_name', label: 'Field', sortable: true },
    { key: 'created_at', label: 'Timestamp', sortable: true },
  ]

  return (
    <div className="page-grid">
      <SectionCard
        title="Admin Settings"
        subtitle="Phase 1 controls using existing roles with permission flags and scoped access"
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
        {activeTab === 'Data Collection Cycles' ? (
          <div className="space-y-4">
            <form className="cycle-config-form" onSubmit={saveCycle}>
              <div className="cycle-config-form-header">
                <div>
                  <h4>{editingCycleId ? 'Edit Collection Cycle' : 'Start New Collection Cycle'}</h4>
                  <p>Managers can open a new reporting window, adjust templates, and control which cycle is active.</p>
                </div>
                {editingCycleId ? (
                  <button type="button" className="button" onClick={resetCycleForm} disabled={cycleSaving}>
                    Cancel Edit
                  </button>
                ) : null}
              </div>

              <div className="cycle-config-grid">
                <label>
                  <span>Cycle year</span>
                  <input
                    type="number"
                    min="2020"
                    value={cycleForm.cycle_year}
                    onChange={(event) => updateCycleForm('cycle_year', event.target.value)}
                    placeholder="2027"
                  />
                </label>
                <label>
                  <span>Open date</span>
                  <input
                    type="date"
                    value={cycleForm.submission_open_date}
                    onChange={(event) => updateCycleForm('submission_open_date', event.target.value)}
                  />
                </label>
                <label>
                  <span>Deadline</span>
                  <input
                    type="date"
                    value={cycleForm.submission_deadline}
                    onChange={(event) => updateCycleForm('submission_deadline', event.target.value)}
                  />
                </label>
                <label>
                  <span>Extension date</span>
                  <input
                    type="date"
                    value={cycleForm.extension_date}
                    onChange={(event) => updateCycleForm('extension_date', event.target.value)}
                  />
                </label>
                <label>
                  <span>Reminder days before deadline</span>
                  <input
                    value={cycleForm.reminder_days_before_deadline}
                    onChange={(event) => updateCycleForm('reminder_days_before_deadline', event.target.value)}
                    placeholder="14, 7, 1"
                  />
                </label>
                <label>
                  <span>Private equity template</span>
                  <input
                    value={cycleForm.private_equity_template}
                    onChange={(event) => updateCycleForm('private_equity_template', event.target.value)}
                  />
                </label>
                <label>
                  <span>Real estate template</span>
                  <input
                    value={cycleForm.real_estate_template}
                    onChange={(event) => updateCycleForm('real_estate_template', event.target.value)}
                  />
                </label>
                <label>
                  <span>Debt template</span>
                  <input
                    value={cycleForm.debt_template}
                    onChange={(event) => updateCycleForm('debt_template', event.target.value)}
                  />
                </label>
              </div>

              <div className="cycle-config-actions">
                {!editingCycleId ? (
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={cycleForm.activate_on_create}
                      onChange={(event) => updateCycleForm('activate_on_create', event.target.checked)}
                    />
                    <span>Start as active cycle</span>
                  </label>
                ) : null}
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={cycleForm.carry_forward_prefill}
                    onChange={(event) => updateCycleForm('carry_forward_prefill', event.target.checked)}
                  />
                  <span>Carry forward prior submission data</span>
                </label>
                <button type="submit" className="button good" disabled={cycleSaving}>
                  {cycleSaving ? 'Saving...' : editingCycleId ? 'Save Cycle' : 'Start New Cycle'}
                </button>
              </div>
            </form>

            <DataTable columns={cyclesTable.columns} rows={cyclesTable.rows} pageSize={8} />
          </div>
        ) : null}

        {activeTab === 'Users' ? (
          <DataTable columns={usersTable.columns} rows={usersTable.rows} pageSize={10} />
        ) : null}

        {activeTab === 'Permissions' ? (
          <DataTable columns={permissionsTable.columns} rows={permissionsTable.rows} pageSize={10} />
        ) : null}

        {activeTab === 'Security' ? (
          <div className="space-y-5">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <h4 className="mb-3 text-sm font-semibold text-slate-800">Session Policies by Role</h4>
              <div className="grid gap-4">
                {sessionPolicies.map((policy) => (
                  <div key={policy.role} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-600">{policy.role}</p>
                    <div className="grid gap-2 md:grid-cols-4">
                      {['timeout_minutes', 'warn_before_minutes', 'max_failed_logins', 'lockout_minutes'].map((field) => (
                        <label key={`${policy.role}-${field}`}>
                          <span className="block text-xs text-slate-500">{field.replace(/_/g, ' ')}</span>
                          <input
                            type="number"
                            value={policyDrafts[policy.role]?.[field] || ''}
                            onChange={(event) => setPolicyDrafts((current) => ({
                              ...current,
                              [policy.role]: {
                                ...(current[policy.role] || {}),
                                [field]: event.target.value,
                              },
                            }))}
                          />
                        </label>
                      ))}
                    </div>
                    <button type="button" className="button mt-3" onClick={() => savePolicy(policy.role)}>Save Policy</button>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <h4 className="mb-3 text-sm font-semibold text-slate-800">IP Allowlist</h4>
              <div className="mb-3 grid gap-2 md:grid-cols-[1fr_1fr_auto]">
                <input
                  placeholder="IP address"
                  value={ipEntry.ip_address}
                  onChange={(event) => setIpEntry((current) => ({ ...current, ip_address: event.target.value }))}
                />
                <input
                  placeholder="Note"
                  value={ipEntry.note}
                  onChange={(event) => setIpEntry((current) => ({ ...current, note: event.target.value }))}
                />
                <button type="button" className="button" onClick={addIp}>Add</button>
              </div>
              <DataTable
                pageSize={8}
                rows={ipAllowlist.map((entry) => ({ ...entry, status: entry.enabled ? 'Enabled' : 'Disabled' }))}
                columns={[
                  { key: 'ip_address', label: 'IP Address', sortable: true },
                  { key: 'note', label: 'Note', sortable: true },
                  { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
                  { key: 'actions', label: 'Actions', render: (row) => <button type="button" className="text-xs text-red-700 font-bold uppercase tracking-wide hover:underline" onClick={() => removeIp(row.id)}>Remove</button> },
                ]}
              />
            </div>
          </div>
        ) : null}

        {activeTab === 'Contextual Help' ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <h4 className="mb-3 text-sm font-semibold text-slate-800">Edit Help Content</h4>
              <div className="grid gap-2 md:grid-cols-2">
                <label>
                  <span className="block text-xs text-slate-500">Cycle</span>
                  <select
                    value={helpForm.cycle_id || cycles[0]?.id || ''}
                    onChange={(event) => setHelpForm((current) => ({ ...current, cycle_id: event.target.value }))}
                  >
                    {cycles.map((cycle) => (
                      <option key={cycle.id} value={cycle.id}>FY{cycle.cycle_year}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span className="block text-xs text-slate-500">Field Key</span>
                  <input
                    value={helpForm.field_key}
                    onChange={(event) => setHelpForm((current) => ({ ...current, field_key: event.target.value }))}
                    placeholder="scope_1_emissions"
                  />
                </label>
                <label className="md:col-span-2">
                  <span className="block text-xs text-slate-500">Title</span>
                  <input
                    value={helpForm.title}
                    onChange={(event) => setHelpForm((current) => ({ ...current, title: event.target.value }))}
                    placeholder="Optional title"
                  />
                </label>
                <label className="md:col-span-2">
                  <span className="block text-xs text-slate-500">Body</span>
                  <textarea
                    value={helpForm.body}
                    onChange={(event) => setHelpForm((current) => ({ ...current, body: event.target.value }))}
                    rows={4}
                    placeholder="Guidance text visible to company users in the form"
                  />
                </label>
              </div>
              <div className="mt-3 flex gap-2">
                <button type="button" className="button" onClick={saveHelpContent}>Save Help</button>
                <button type="button" className="button" onClick={loadHelpContent}>Reload</button>
              </div>
            </div>

            <DataTable
              pageSize={8}
              rows={helpContentItems.map((item) => ({
                id: `${item.field_key}-${item.version}`,
                field_key: item.field_key,
                title: item.title,
                body: item.body,
                version: item.version,
                updated_at: item.updated_at,
              }))}
              columns={[
                { key: 'field_key', label: 'Field Key', sortable: true },
                { key: 'title', label: 'Title', sortable: true },
                { key: 'version', label: 'Version', sortable: true },
                { key: 'updated_at', label: 'Updated At', sortable: true },
                {
                  key: 'actions',
                  label: 'Actions',
                  render: (row) => (
                    <button
                      type="button"
                      className="text-xs text-indigo-700 font-bold uppercase tracking-wide hover:underline"
                      onClick={() => setHelpForm((current) => ({
                        ...current,
                        field_key: row.field_key,
                        title: row.title,
                        body: row.body,
                      }))}
                    >
                      Edit
                    </button>
                  ),
                },
              ]}
            />
          </div>
        ) : null}

        {activeTab === 'Audit Trail' ? (
          <DataTable columns={auditColumns} rows={auditEvents.map((row) => ({ ...row, id: row.id || `${row.event_type}-${row.created_at}` }))} pageSize={12} />
        ) : null}

        {activeTab === 'Onboarding' ? (
          <DataTable
            pageSize={10}
            rows={onboardingRows.map((row) => ({
              id: row.company_id,
              company_name: row.company_name,
              company_status: row.company_status,
              progress_percent: row.progress_percent,
              completed: row.completed ? 'Completed' : 'In Progress',
              steps: Object.entries(row.steps || {}).map(([step, meta]) => `${step}:${meta?.completed ? 'done' : 'pending'}`).join(' | '),
            }))}
            columns={[
              { key: 'company_name', label: 'Company', sortable: true },
              { key: 'company_status', label: 'Status', sortable: true },
              { key: 'progress_percent', label: 'Progress %', sortable: true },
              { key: 'completed', label: 'Completed', sortable: true, render: (row) => <StatusBadge value={row.completed} /> },
              { key: 'steps', label: 'Steps', sortable: false },
              {
                key: 'actions',
                label: 'Actions',
                render: (row) => (
                  <button
                    type="button"
                    className="text-xs text-orange-700 font-bold uppercase tracking-wide hover:underline"
                    onClick={() => retriggerOnboarding(row.id)}
                  >
                    Retrigger
                  </button>
                ),
              },
            ]}
          />
        ) : null}

        {message ? <p className="action-message">{message}</p> : null}
      </SectionCard>
    </div>
  )
}
