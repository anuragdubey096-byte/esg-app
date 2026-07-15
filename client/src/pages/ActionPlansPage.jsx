import { useCallback, useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import ExecutivePageHeader from '../components/ExecutivePageHeader'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData from '../hooks/useDashboardData'
import { API_BASE_URL } from '../lib/api'

const emptyTarget = {
  company_id: '',
  pillar: 'Environmental',
  metric_key: 'total_ghg_emissions',
  target_name: '',
  baseline_value: '',
  target_value: '',
  current_value: '',
  unit: 'tCO2e',
  target_date: '',
  owner: '',
  status: 'on track',
  notes: '',
}

export default function ActionPlansPage() {
  const { user } = useOutletContext()
  const { companies, refresh } = useDashboardData(user)
  const [status, setStatus] = useState('All')
  const [pillar, setPillar] = useState('All')
  const [company, setCompany] = useState('All')
  const [targets, setTargets] = useState([])
  const [targetForm, setTargetForm] = useState(emptyTarget)
  const [message, setMessage] = useState('')
  const [loadingTargets, setLoadingTargets] = useState(true)

  const loadTargets = useCallback(async () => {
    setLoadingTargets(true)
    try {
      const response = await fetch(`${API_BASE_URL}/targets`)
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Unable to load ESG targets.')
      setTargets(await response.json())
    } catch (error) {
      setMessage(error.message)
    } finally {
      setLoadingTargets(false)
    }
  }, [])

  useEffect(() => { loadTargets() }, [loadTargets])

  useEffect(() => {
    if (!targetForm.company_id && companies.length === 1) {
      setTargetForm((current) => ({ ...current, company_id: String(companies[0].id) }))
    }
  }, [companies, targetForm.company_id])

  const actionPlanRows = useMemo(() => companies.flatMap((item) =>
    (item.action_plans || []).map((plan) => ({
      id: plan.id,
      company: item.name,
      action: plan.initiative_name,
      owner: plan.assigned_owner,
      deadline: plan.target_completion_date,
      status: plan.status,
    }))), [companies])

  const options = useMemo(() => ({
    status: ['All', ...new Set([...targets.map((row) => row.status), ...actionPlanRows.map((row) => row.status)])],
    pillars: ['All', 'Environmental', 'Social', 'Governance'],
    companies: ['All', ...new Set([...targets.map((row) => row.company_name), ...actionPlanRows.map((row) => row.company)])],
  }), [actionPlanRows, targets])

  const filteredTargets = useMemo(() => targets.filter((row) => (
    (status === 'All' || row.status === status)
    && (pillar === 'All' || row.pillar === pillar)
    && (company === 'All' || row.company_name === company)
  )), [company, pillar, status, targets])

  const filteredActions = useMemo(() => actionPlanRows.filter((row) => (
    (status === 'All' || row.status === status)
    && (company === 'All' || row.company === company)
  )), [actionPlanRows, company, status])

  const summary = useMemo(() => ({
    total: filteredTargets.length,
    achieved: filteredTargets.filter((row) => row.status === 'achieved').length,
    atRisk: filteredTargets.filter((row) => row.status === 'at risk').length,
    averageProgress: filteredTargets.length
      ? filteredTargets.reduce((sum, row) => sum + Number(row.progress_percent || 0), 0) / filteredTargets.length
      : 0,
    openActions: filteredActions.filter((row) => !['completed', 'done'].includes(String(row.status).toLowerCase())).length,
  }), [filteredActions, filteredTargets])

  const updateTarget = async (targetId, updates) => {
    setMessage('Saving target update...')
    const response = await fetch(`${API_BASE_URL}/targets/${targetId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      setMessage(payload.detail || 'Unable to update target.')
      return
    }
    await loadTargets()
    setMessage('Target updated.')
  }

  const updateActionStatus = async (planId, nextStatus) => {
    const response = await fetch(`${API_BASE_URL}/action-plans/${planId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: nextStatus }),
    })
    if (!response.ok) {
      setMessage((await response.json().catch(() => ({}))).detail || 'Unable to update action plan.')
      return
    }
    await refresh()
    setMessage('Action plan updated.')
  }

  const createTarget = async (event) => {
    event.preventDefault()
    if (!targetForm.company_id) {
      setMessage('Select a company before creating a target.')
      return
    }
    const payload = {
      ...targetForm,
      baseline_value: Number(targetForm.baseline_value),
      target_value: Number(targetForm.target_value),
      current_value: Number(targetForm.current_value),
    }
    const response = await fetch(`${API_BASE_URL}/company/${targetForm.company_id}/targets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}))
      setMessage(errorPayload.detail || 'Unable to create target.')
      return
    }
    setTargetForm({ ...emptyTarget, company_id: targetForm.company_id })
    await loadTargets()
    setMessage('ESG target created.')
  }

  const targetColumns = [
    { key: 'company_name', label: 'Company', sortable: true },
    { key: 'pillar', label: 'Pillar', sortable: true },
    { key: 'target_name', label: 'Target', sortable: true },
    { key: 'current_value', label: 'Current', sortable: true, render: (row) => `${row.current_value.toLocaleString()} ${row.unit}` },
    { key: 'target_value', label: 'Goal', sortable: true, render: (row) => `${row.target_value.toLocaleString()} ${row.unit}` },
    { key: 'progress_percent', label: 'Progress', sortable: true, render: (row) => <div className="target-progress"><span style={{ width: `${row.progress_percent}%` }} /><strong>{row.progress_percent}%</strong></div> },
    { key: 'target_date', label: 'Due', sortable: true },
    { key: 'owner', label: 'Owner', sortable: true },
    { key: 'status', label: 'Status', sortable: true, render: (row) => (
      <select value={row.status} onChange={(event) => updateTarget(row.id, { status: event.target.value })}>
        {['not started', 'on track', 'at risk', 'achieved'].map((value) => <option key={value}>{value}</option>)}
      </select>
    ) },
    { key: 'update', label: 'Update', render: (row) => <button type="button" className="table-action" onClick={() => { const value = window.prompt(`Current value (${row.unit})`, row.current_value); if (value !== null && Number.isFinite(Number(value))) updateTarget(row.id, { current_value: Number(value) }) }}>Update actual</button> },
  ]

  const actionColumns = [
    { key: 'company', label: 'Company', sortable: true },
    { key: 'action', label: 'Action', sortable: true },
    { key: 'owner', label: 'Owner', sortable: true },
    { key: 'deadline', label: 'Deadline', sortable: true },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
    { key: 'update', label: 'Update', render: (row) => (
      <select value={row.status} onChange={(event) => updateActionStatus(row.id, event.target.value)}>
        {['planned', 'in progress', 'blocked', 'completed'].map((value) => <option key={value}>{value}</option>)}
      </select>
    ) },
  ]

  return (
    <div className="page-grid">
      <ExecutivePageHeader
        eyebrow="Performance management"
        title="ESG targets and action tracking"
        description="Turn portfolio commitments into measurable targets, accountable owners, deadlines, and tracked remediation actions."
        meta={[{ label: 'Targets', value: summary.total }, { label: 'Average progress', value: `${summary.averageProgress.toFixed(1)}%` }, { label: 'At risk', value: summary.atRisk }]}
      />

      <section className="executive-kpi-grid">
        <KpiCard title="Active Targets" value={summary.total} icon="actions" />
        <KpiCard title="Average Progress" value={`${summary.averageProgress.toFixed(1)}%`} icon="analytics" />
        <KpiCard title="Achieved" value={summary.achieved} icon="review" />
        <KpiCard title="At Risk" value={summary.atRisk} tone="rose" icon="risks" />
        <KpiCard title="Open Actions" value={summary.openActions} tone="amber" icon="submissions" />
      </section>

      <SectionCard title="Scope and status" subtitle="Filter targets and actions using the same management view">
        <div className="filter-bar sticky">
          <label><span>Status</span><select value={status} onChange={(event) => setStatus(event.target.value)}>{options.status.map((option) => <option key={option}>{option}</option>)}</select></label>
          <label><span>ESG Pillar</span><select value={pillar} onChange={(event) => setPillar(event.target.value)}>{options.pillars.map((option) => <option key={option}>{option}</option>)}</select></label>
          <label><span>Company</span><select value={company} onChange={(event) => setCompany(event.target.value)}>{options.companies.map((option) => <option key={option}>{option}</option>)}</select></label>
        </div>
      </SectionCard>

      <SectionCard title="ESG target register" subtitle="Baseline, actual, goal, owner, deadline, and delivery status">
        {loadingTargets ? <p>Loading targets...</p> : <DataTable columns={targetColumns} rows={filteredTargets} pageSize={10} emptyMessage="No ESG targets match this scope." />}
      </SectionCard>

      {user?.role !== 'investor' ? (
        <SectionCard title="Create measurable target" subtitle="Define an environmental, social, or governance outcome">
          <form className="target-form" onSubmit={createTarget}>
            <label><span>Company</span><select required value={targetForm.company_id} onChange={(event) => setTargetForm({ ...targetForm, company_id: event.target.value })}><option value="">Select company</option>{companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label><span>Pillar</span><select value={targetForm.pillar} onChange={(event) => setTargetForm({ ...targetForm, pillar: event.target.value })}>{['Environmental', 'Social', 'Governance'].map((value) => <option key={value}>{value}</option>)}</select></label>
            <label><span>Target name</span><input required value={targetForm.target_name} onChange={(event) => setTargetForm({ ...targetForm, target_name: event.target.value })} placeholder="Reduce total GHG emissions" /></label>
            <label><span>Metric key</span><input required value={targetForm.metric_key} onChange={(event) => setTargetForm({ ...targetForm, metric_key: event.target.value })} /></label>
            <label><span>Baseline</span><input required type="number" step="any" value={targetForm.baseline_value} onChange={(event) => setTargetForm({ ...targetForm, baseline_value: event.target.value })} /></label>
            <label><span>Current</span><input required type="number" step="any" value={targetForm.current_value} onChange={(event) => setTargetForm({ ...targetForm, current_value: event.target.value })} /></label>
            <label><span>Goal</span><input required type="number" step="any" value={targetForm.target_value} onChange={(event) => setTargetForm({ ...targetForm, target_value: event.target.value })} /></label>
            <label><span>Unit</span><input value={targetForm.unit} onChange={(event) => setTargetForm({ ...targetForm, unit: event.target.value })} /></label>
            <label><span>Target date</span><input required type="date" value={targetForm.target_date} onChange={(event) => setTargetForm({ ...targetForm, target_date: event.target.value })} /></label>
            <label><span>Owner</span><input required value={targetForm.owner} onChange={(event) => setTargetForm({ ...targetForm, owner: event.target.value })} /></label>
            <label className="target-form-notes"><span>Notes</span><textarea value={targetForm.notes} onChange={(event) => setTargetForm({ ...targetForm, notes: event.target.value })} /></label>
            <button className="button" type="submit">Create target</button>
          </form>
        </SectionCard>
      ) : null}

      <SectionCard title="Action plan tracker" subtitle="Operational initiatives supporting target delivery">
        <DataTable columns={actionColumns} rows={filteredActions} pageSize={10} emptyMessage="No action plans match this scope." />
      </SectionCard>
      {message ? <p className="action-message" role="status">{message}</p> : null}
    </div>
  )
}
