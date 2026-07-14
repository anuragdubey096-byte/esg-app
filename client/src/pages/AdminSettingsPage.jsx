import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData from '../hooks/useDashboardData'
import { API_BASE_URL } from '../lib/api'

const adminSettingsTabs = ['Data Collection Cycles', 'Safe CSV Import', 'Users']
const BACKEND_URL = API_BASE_URL

function defaultCycleForm() {
  const nextYear = new Date().getFullYear() + 1
  return {
    cycle_year: nextYear,
    submission_open_date: `${nextYear}-01-01`,
    submission_deadline: `${nextYear}-03-31`,
    extension_date: '',
    activate_on_create: false,
  }
}

export default function AdminSettingsPage() {
  const { user } = useOutletContext()
  const { cycles, refresh } = useDashboardData(user)
  const [activeTab, setActiveTab] = useState(adminSettingsTabs[0])
  const [message, setMessage] = useState('')
  const [cycleForm, setCycleForm] = useState(defaultCycleForm)
  const [importFile, setImportFile] = useState(null)
  const [importCycleId, setImportCycleId] = useState('')
  const [importResult, setImportResult] = useState(null)
  const [importBusy, setImportBusy] = useState(false)

  const request = async (path, options = {}) => {
    const response = await fetch(`${BACKEND_URL}${path}`, options)
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`)
    return payload
  }

  const updateCycleStatus = async (cycleId, status) => {
    const destructive = ['closed', 'archived', 'draft'].includes(status)
    if (destructive && !window.confirm(`Confirm changing this reporting cycle to ${status}?`)) return
    setMessage('Updating cycle status...')
    try {
      await request(`/cycles/${cycleId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })
      setMessage(`Cycle updated to ${status}.`)
      refresh('cycles')
    } catch (error) {
      setMessage(error.message)
    }
  }

  const createCycle = async (event) => {
    event.preventDefault()
    setMessage('Creating cycle...')
    try {
      await request('/cycles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...cycleForm,
          cycle_year: Number(cycleForm.cycle_year),
          extension_date: cycleForm.extension_date || null,
          reminder_days_before_deadline: [30, 14, 7, 1],
          private_equity_template: 'Standard ESG template',
          real_estate_template: 'Real estate ESG template',
          debt_template: 'Debt ESG template',
          carry_forward_prefill: true,
        }),
      })
      setMessage(`FY${cycleForm.cycle_year} created.`)
      setCycleForm(defaultCycleForm())
      refresh('cycles')
    } catch (error) {
      setMessage(error.message)
    }
  }

  const deleteCycle = async (row) => {
    if (!window.confirm(`Permanently delete ${row.cycle}? This only succeeds when it has no submissions or dependent records.`)) return
    setMessage('Checking and deleting empty cycle...')
    try {
      const payload = await request(`/cycles/${row.id}`, { method: 'DELETE' })
      setMessage(payload.message)
      refresh('cycles')
    } catch (error) {
      setMessage(error.message)
    }
  }

  const runImport = async (mode) => {
    if (!importFile) {
      setMessage('Choose a CSV file first.')
      return
    }
    if (mode === 'commit' && !importResult) {
      setMessage('Preview and validate the CSV before importing.')
      return
    }
    if (mode === 'commit' && !window.confirm(`Import ${importResult?.summary?.accepted || 0} accepted rows? Rejected rows will not be imported.`)) return
    const formData = new FormData()
    formData.append('file', importFile)
    formData.append('mode', mode)
    formData.append('mapping_json', JSON.stringify({}))
    if (importCycleId) formData.append('cycle_id', importCycleId)
    setImportBusy(true)
    setMessage(mode === 'preview' ? 'Validating every CSV row...' : 'Importing accepted rows...')
    try {
      const payload = await request('/admin/import/submissions', { method: 'POST', body: formData })
      setImportResult(payload)
      setMessage(mode === 'preview'
        ? `Preview complete: ${payload.summary.accepted} accepted, ${payload.summary.rejected} rejected.`
        : `Import complete: ${payload.summary.imported} imported, ${payload.summary.rejected} rejected.`)
      if (mode === 'commit') refresh()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setImportBusy(false)
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
        ],
      }
    }
    const rows = cycles.map((cycle) => ({
      id: cycle.id,
      cycle: `FY${cycle.cycle_year}`,
      openDate: cycle.submission_open_date,
      deadline: cycle.submission_deadline,
      submissions: cycle.submission_count || 0,
      status: cycle.status,
    }))
    return {
      rows,
      columns: [
        { key: 'cycle', label: 'Cycle', sortable: true },
        { key: 'openDate', label: 'Open Date', sortable: true },
        { key: 'deadline', label: 'Deadline', sortable: true },
        { key: 'submissions', label: 'Submissions', sortable: true },
        { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
        {
          key: 'actions',
          label: 'Actions',
          render: (row) => (
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className="text-xs text-green-700 font-bold uppercase" onClick={() => updateCycleStatus(row.id, 'active')}>Activate</button>
              <button type="button" className="text-xs text-red-700 font-bold uppercase" onClick={() => updateCycleStatus(row.id, 'closed')}>Close</button>
              <button type="button" className="text-xs text-blue-700 font-bold uppercase" onClick={() => updateCycleStatus(row.id, 'draft')}>Reopen</button>
              <button type="button" className="text-xs text-amber-700 font-bold uppercase" onClick={() => updateCycleStatus(row.id, 'archived')}>Archive</button>
              <button type="button" className="text-xs text-slate-700 font-bold uppercase" onClick={() => deleteCycle(row)}>Delete</button>
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
        subtitle="Manage secure reporting cycles, imports, access, and data governance controls"
        actions={(
          <div className="tab-row">
            {adminSettingsTabs.map((tab) => (
              <button key={tab} type="button" className={`tab-button ${tab === activeTab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>{tab}</button>
            ))}
          </div>
        )}
      >
        {activeTab === 'Data Collection Cycles' ? (
          <>
            <form className="filter-bar" onSubmit={createCycle}>
              <label><span>Reporting year</span><input type="number" min="2000" max={new Date().getFullYear() + 5} value={cycleForm.cycle_year} onChange={(event) => setCycleForm((value) => ({ ...value, cycle_year: event.target.value }))} required /></label>
              <label><span>Open date</span><input type="date" value={cycleForm.submission_open_date} onChange={(event) => setCycleForm((value) => ({ ...value, submission_open_date: event.target.value }))} required /></label>
              <label><span>Deadline</span><input type="date" value={cycleForm.submission_deadline} onChange={(event) => setCycleForm((value) => ({ ...value, submission_deadline: event.target.value }))} required /></label>
              <label><span>Extension</span><input type="date" value={cycleForm.extension_date} onChange={(event) => setCycleForm((value) => ({ ...value, extension_date: event.target.value }))} /></label>
              <label><span>Activate now</span><input type="checkbox" checked={cycleForm.activate_on_create} onChange={(event) => setCycleForm((value) => ({ ...value, activate_on_create: event.target.checked }))} /></label>
              <button className="button" type="submit">Create cycle</button>
            </form>
            <DataTable columns={current.columns} rows={current.rows} pageSize={8} />
          </>
        ) : null}

        {activeTab === 'Safe CSV Import' ? (
          <div className="space-y-4">
            <div className="filter-bar">
              <label><span>CSV file</span><input type="file" accept=".csv,text/csv" onChange={(event) => { setImportFile(event.target.files?.[0] || null); setImportResult(null) }} /></label>
              <label><span>Reporting cycle</span><select value={importCycleId} onChange={(event) => { setImportCycleId(event.target.value); setImportResult(null) }}><option value="">Latest valid cycle</option>{cycles.map((cycle) => <option key={cycle.id} value={cycle.id}>FY{cycle.cycle_year}</option>)}</select></label>
              <button className="button" type="button" disabled={importBusy} onClick={() => runImport('preview')}>Preview & validate</button>
              <button className="button" type="button" disabled={importBusy || !importResult || !importResult.summary?.accepted} onClick={() => runImport('commit')}>Import accepted rows</button>
            </div>
            {importResult ? (
              <>
                <div className="executive-kpi-grid">
                  <div><strong>{importResult.summary.total}</strong><span>Total rows</span></div>
                  <div><strong>{importResult.summary.accepted}</strong><span>Accepted</span></div>
                  <div><strong>{importResult.summary.rejected}</strong><span>Rejected</span></div>
                  <div><strong>{importResult.summary.corrected}</strong><span>Normalized</span></div>
                </div>
                <SectionCard title="Column mapping preview" subtitle="Unmapped columns are ignored; mapped fields are validated before import.">
                  <DataTable rows={importResult.columns.map((item, index) => ({ id: index + 1, ...item }))} columns={[{ key: 'source', label: 'CSV column' }, { key: 'target', label: 'Mapped ESG field' }, { key: 'status', label: 'Status' }]} pageSize={12} />
                </SectionCard>
                <SectionCard title="Row-level validation" subtitle="Rejected rows remain outside the database.">
                  <DataTable rows={importResult.rows.map((item) => ({ ...item, id: item.row, errorsText: item.errors.join('; ') || 'Ready to import' }))} columns={[{ key: 'row', label: 'Row' }, { key: 'company', label: 'Company' }, { key: 'status', label: 'Result' }, { key: 'corrected', label: 'Normalized', render: (row) => (row.corrected ? 'Yes' : 'No') }, { key: 'errorsText', label: 'Validation details' }]} pageSize={12} />
                </SectionCard>
              </>
            ) : null}
          </div>
        ) : null}

        {activeTab === 'Users' ? <DataTable columns={current.columns} rows={current.rows} pageSize={8} /> : null}
        {message ? <p className="action-message" role="status">{message}</p> : null}
      </SectionCard>
    </div>
  )
}
