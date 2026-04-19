import { useEffect, useMemo, useState, useRef } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import { Button } from '../components/ui'
import { CONFIDENCE_OPTIONS, ESG_FORM_SECTIONS, createInitialFormValues } from '../esgFormConfig'
import { validateSubmissionData } from '../esgValidation'
import useDashboardData, {
  calculateESGScore,
  getLatestSubmission,
  getPreferredCycle,
  getProgressFromStatus,
  getRiskLevel,
  normalizeStatus,
  parseSubmissionPayload,
} from '../hooks/useDashboardData'
import { API_BASE_URL } from '../lib/api'
import { CHART_COLORS } from '../lib/foundation'
import { REPORT_FRAMEWORK_OPTIONS } from '../lib/portalOptions'
import {
  createFilterPresetId,
  loadLastFilterState,
  loadSavedFilterPresets,
  removeSavedFilterPreset,
  sanitizeFilterPresetName,
  saveLastFilterState,
  upsertSavedFilterPreset,
} from '../lib/experience'

const numericFields = new Set(
  ESG_FORM_SECTIONS.flatMap((section) =>
    section.fields.filter((field) => field.type === 'number').map((field) => field.name)
  )
)

const metricFields = ESG_FORM_SECTIONS.flatMap((section) =>
  section.fields.filter((field) => field.type !== 'text' && field.type !== 'textarea').map((field) => field.name)
)

function getDeadlineState(row) {
  if (row.status === 'Approved') return 'complete'
  if (!row.deadline || row.deadline === '--') {
    return row.risk === 'High' ? 'at-risk' : 'on-track'
  }

  const today = new Date()
  const deadline = new Date(`${row.deadline}T00:00:00`)
  const dayDiff = Math.ceil((deadline.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))

  if (dayDiff < 0) return 'overdue'
  if (dayDiff <= 7 || row.risk === 'High') return 'at-risk'
  return 'on-track'
}

function buildSubmissionPayload(formValues) {
  const payload = {}
  Object.entries(formValues).forEach(([key, value]) => {
    if (numericFields.has(key)) {
      payload[key] = value === '' ? null : Number(value)
      return
    }
    payload[key] = value === '' ? null : value
  })
  return payload
}

function validatePortfolioForm(formValues) {
  const errors = []
  metricFields.forEach((fieldName) => {
    const value = formValues[fieldName]
    const confidence = formValues[`${fieldName}_confidence`]
    if ((value ?? '') === '') {
      errors.push(`${fieldName.replace(/_/g, ' ')} is required.`)
    }
    if (!confidence) {
      errors.push(`${fieldName.replace(/_/g, ' ')} confidence is required.`)
    }
  })

  const validation = validateSubmissionData(formValues)
  validation.checks.forEach((check) => {
    if (check.status === 'fail') errors.push(check.message)
  })

  return [...new Set(errors)]
}

function createPrefilledFormValues(company) {
  const base = createInitialFormValues()
  const latestSubmission = getLatestSubmission(company)
  const parsed = parseSubmissionPayload(latestSubmission)
  if (!parsed || typeof parsed !== 'object') return base

  Object.keys(base).forEach((key) => {
    if (parsed[key] === null || parsed[key] === undefined) return
    base[key] = String(parsed[key])
  })

  return base
}

export default function SubmissionsPage() {
  const { user } = useOutletContext()
  const [searchParams] = useSearchParams()
  const { companies, cycles, loading, error, refresh } = useDashboardData(user)
  const [status, setStatus] = useState('All')
  const [sector, setSector] = useState('All')
  const [geography, setGeography] = useState('All')
  const [search, setSearch] = useState('')
  const [focusedCompanyId, setFocusedCompanyId] = useState(null)
  const [savedFilterSets, setSavedFilterSets] = useState([])
  const [activeFilterSetId, setActiveFilterSetId] = useState('')
  const [selectedCompanyId, setSelectedCompanyId] = useState(null)
  const [formValues, setFormValues] = useState(createInitialFormValues)
  const [formMessage, setFormMessage] = useState('')
  const [evidenceExtraction, setEvidenceExtraction] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const formValuesRef = useRef(formValues)
  const hydratedFiltersRef = useRef(false)
  const [activeTab, setActiveTab] = useState(ESG_FORM_SECTIONS.length ? ESG_FORM_SECTIONS[0].key : '')
  const filterScope = useMemo(() => `submissions:${user?.role || 'guest'}:${user?.email || 'guest'}`, [user?.email, user?.role])
  const queryFilters = useMemo(() => ({
    status: searchParams.get('status') || '',
    sector: searchParams.get('sector') || '',
    geography: searchParams.get('geography') || '',
    search: searchParams.get('search') || searchParams.get('company') || '',
    companyId: searchParams.get('companyId') || '',
  }), [searchParams.toString()])

  useEffect(() => {
    const persisted = loadLastFilterState(filterScope) || {}
    const nextStatus = queryFilters.status || persisted.status || 'All'
    const nextSector = queryFilters.sector || persisted.sector || 'All'
    const nextGeography = queryFilters.geography || persisted.geography || 'All'
    const nextSearch = queryFilters.search || persisted.search || ''
    const nextFocusedCompanyId = queryFilters.companyId
      ? Number(queryFilters.companyId)
      : Number(persisted.focusedCompanyId)

    setStatus(nextStatus)
    setSector(nextSector)
    setGeography(nextGeography)
    setSearch(nextSearch)
    setFocusedCompanyId(Number.isFinite(nextFocusedCompanyId) ? nextFocusedCompanyId : null)
    setSavedFilterSets(loadSavedFilterPresets(filterScope))
    setActiveFilterSetId('')
    hydratedFiltersRef.current = true
  }, [filterScope, queryFilters.companyId, queryFilters.geography, queryFilters.search, queryFilters.sector, queryFilters.status])

  useEffect(() => {
    if (!hydratedFiltersRef.current) return
    saveLastFilterState(filterScope, {
      status,
      sector,
      geography,
      search,
      focusedCompanyId,
    })
  }, [filterScope, focusedCompanyId, geography, search, sector, status])

  const investorChartData = useMemo(() => {
    if (user?.role !== 'investor') return [];
    return companies.map(c => {
      const payload = parseSubmissionPayload(getLatestSubmission(c));
      return {
        name: c.name,
        scope1: payload?.scope_1_emissions || 0,
        scope2: payload?.scope_2_location_based || 0,
        scope3: payload?.scope_3_emissions || 0,
        femaleLeadership: payload?.female_leadership_representation_percent || 0,
      }
    }).filter(d => d.scope1 > 0 || d.femaleLeadership > 0);
  }, [companies, user?.role]);

  const managerHeaders = useMemo(() => ({
    'Content-Type': 'application/json',
    'x-user-role': user?.role || '',
    'x-user-email': user?.email || '',
  }), [user?.email, user?.role])

  const managerPost = async (path, method = 'POST', body = null) => {
      const response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: body ? managerHeaders : {
        'x-user-role': user?.role || '',
        'x-user-email': user?.email || '',
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}))
      throw new Error(errorPayload.detail || `Request failed (${response.status})`)
    }
    return response.json().catch(() => ({}))
  }

  const handleValidate = async (submissionId) => {
    try {
      await managerPost(`/submissions/${submissionId}/validate`, 'POST')
      alert('Validation complete. Anomalies flagged.')
      refresh()
    } catch(e) { alert(e.message) }
  }

  const handleReview = async (submissionId, status, currentStatus) => {
    try {
      if (
        ['approved', 'rejected', 'resubmission requested'].includes(status)
        && currentStatus === 'Submitted'
      ) {
        await managerPost(`/submissions/${submissionId}/status`, 'PATCH', { status: 'under review' })
      }
      await managerPost(`/submissions/${submissionId}/review`, 'POST', {
        reviewer_role: 'Manager',
        review_status: status,
        review_comment: 'Reviewed via dashboard',
      })
      alert(`Submission marked as ${status}`)
      refresh()
    } catch(e) { alert(e.message) }
  }

  const handleUnlock = async (companyId) => {
    const reason = window.prompt('Enter unlock reason', 'Allow targeted correction after cycle close')
    if (!reason) return
    try {
      await managerPost(`/companies/${companyId}/unlock`, 'POST', {
        reason,
        expiry_hours: 24,
      })
      alert('Submission unlocked for 24 hours.')
      refresh()
    } catch (e) {
      alert(e.message)
    }
  }

  const handleReminder = async (companyId) => {
    const message = window.prompt('Reminder message', 'Please submit updated ESG data before the deadline.')
    if (!message) return
    try {
      await managerPost(`/companies/${companyId}/reminders`, 'POST', {
        channel: 'email',
        message,
      })
      alert('Reminder logged successfully.')
      refresh()
    } catch (e) {
      alert(e.message)
    }
  }

  const handleDownloadReport = async (type) => {
    try {
    const res = await fetch(`${API_BASE_URL}/reports/${type}`)
      const data = await res.json()
      alert(`Report generated! Download URL: ${data.download_url}`)
    } catch(e) { alert(e.message) }
  }

  const rows = useMemo(() => {
    const preferredCycle = getPreferredCycle(cycles)
    const deadline = preferredCycle?.submission_deadline || '--'

    return companies.map((company) => {
      const latest = getLatestSubmission(company)
      const statusLabel = normalizeStatus(latest?.status || company?.current_status || 'Not Started')
      const payload = parseSubmissionPayload(latest)
      const esgScore = calculateESGScore(statusLabel, payload)
      const progress = getProgressFromStatus(statusLabel)
      const risk = getRiskLevel({ status: statusLabel, esgScore, deadline })

      return {
        id: company.id,
        companyName: company.name,
        status: statusLabel,
        currentStatus: company.current_status,
        progress,
        deadline,
        esgScore,
        risk,
        sector: company.sector || 'Unassigned',
        geography: company.geography || 'Unknown',
        submissionId: latest?.id,
        flags: company.validation_flags?.length || 0,
      }
    })
  }, [companies, cycles])

  const options = useMemo(() => ({
    statuses: ['All', ...new Set(rows.map((row) => row.status))],
    sectors: ['All', ...new Set(rows.map((row) => row.sector))],
    geographies: ['All', ...new Set(rows.map((row) => row.geography))],
  }), [rows])

  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      const statusMatch = status === 'All' || row.status === status
      const sectorMatch = sector === 'All' || row.sector === sector
      const geoMatch = geography === 'All' || row.geography === geography
      const searchTerm = search.trim().toLowerCase()
      const searchMatch =
        !searchTerm ||
        [row.companyName, row.sector, row.geography, row.status, String(row.esgScore)]
          .join(' ')
          .toLowerCase()
          .includes(searchTerm)
      const focusedCompanyMatch = !focusedCompanyId || row.id === focusedCompanyId
      return statusMatch && sectorMatch && geoMatch && searchMatch && focusedCompanyMatch
    })
  }, [focusedCompanyId, geography, rows, search, sector, status])

  const columns = [
    { key: 'companyName', label: 'Company Name', sortable: true },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
    { key: 'progress', label: 'Progress %', sortable: true, render: (row) => `${row.progress}%` },
    { key: 'deadline', label: 'Deadline', sortable: true },
    { key: 'esgScore', label: 'ESG Score', sortable: true },
    { key: 'risk', label: 'Risk Indicator', sortable: true, render: (row) => <StatusBadge value={row.risk} /> },
  ]

  if (user?.role === 'manager') {
    columns.push({
      key: 'flags', label: 'Anomalies', sortable: true, render: (row) => (
        row.flags > 0 ? <span className="text-red-600 ui-text-strong">{row.flags} Flag(s)</span> : <span className="text-slate-400">None</span>
      )
    })
    columns.push({
      key: 'actions', label: 'Actions', render: (row) => (
        <div className="flex items-center gap-3">
          {row.currentStatus === 'pre-acquisition' && (
            <Button className="text-xs text-indigo-600 ui-text-strong uppercase tracking-wide hover:underline" onClick={async () => {
              try {
      const res = await fetch(`${API_BASE_URL}/company/${row.id}/onboarding/complete`, {
                  method: 'POST',
                  headers: {
                    'x-user-role': user?.role || '',
                    'x-user-email': user?.email || '',
                  }
                });
                if (!res.ok) throw new Error('Failed to complete onboarding');
                alert('Company onboarded successfully!');
                refresh();
              } catch(e) { alert(e.message) }
            }}>Onboard</Button>
          )}
          {row.submissionId ? (
            <>
              <Button className="text-xs text-blue-600 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => handleValidate(row.submissionId)}>Validate</Button>
              <Button className="text-xs text-sky-700 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => handleReview(row.submissionId, 'under review', row.status)}>Under Review</Button>
              <Button className="text-xs text-green-600 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => handleReview(row.submissionId, 'approved', row.status)}>Approve</Button>
              <Button className="text-xs text-orange-600 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => handleReview(row.submissionId, 'resubmission requested', row.status)}>Resubmit</Button>
              <Button className="text-xs text-red-600 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => handleReview(row.submissionId, 'rejected', row.status)}>Reject</Button>
              <Button className="text-xs text-amber-700 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => handleUnlock(row.id)}>Unlock</Button>
              <Button className="text-xs text-violet-700 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => handleReminder(row.id)}>Reminder</Button>
            </>
          ) : (
            <Button className="text-xs text-violet-700 ui-text-strong uppercase tracking-wide hover:underline" onClick={() => handleReminder(row.id)}>Send Reminder</Button>
          )}
        </div>
      )
    })
  }

  const rowClassName = (row) => {
    const state = getDeadlineState(row)
    if (state === 'overdue') return 'row-overdue'
    if (state === 'at-risk') return 'row-at-risk'
    if (state === 'complete') return 'row-complete'
    return ''
  }

  const activeSavedFilter = useMemo(
    () => savedFilterSets.find((item) => item.id === activeFilterSetId) || null,
    [activeFilterSetId, savedFilterSets],
  )

  const applySavedFilterSet = (preset) => {
    if (!preset?.filters) return
    setStatus(preset.filters.status || 'All')
    setSector(preset.filters.sector || 'All')
    setGeography(preset.filters.geography || 'All')
    setSearch(preset.filters.search || '')
    setFocusedCompanyId(preset.filters.focusedCompanyId ? Number(preset.filters.focusedCompanyId) : null)
    setActiveFilterSetId(preset.id)
  }

  const handleSaveCurrentFilters = () => {
    const suggestedName = activeSavedFilter?.name || 'Saved submission view'
    const name = sanitizeFilterPresetName(window.prompt('Name this saved view', suggestedName))
    if (!name) return

    const preset = {
      id: activeSavedFilter?.id || createFilterPresetId('submissions'),
      name,
      filters: {
        status,
        sector,
        geography,
        search,
        focusedCompanyId,
      },
      createdAt: activeSavedFilter?.createdAt || new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }
    const nextPresets = upsertSavedFilterPreset(filterScope, preset)
    setSavedFilterSets(nextPresets)
    setActiveFilterSetId(preset.id)
  }

  const handleDeleteSavedFilter = () => {
    if (!activeSavedFilter) return
    const confirmed = window.confirm(`Delete saved view "${activeSavedFilter.name}"?`)
    if (!confirmed) return
    const nextPresets = removeSavedFilterPreset(filterScope, activeSavedFilter.id)
    setSavedFilterSets(nextPresets)
    setActiveFilterSetId('')
  }

  const clearFilters = () => {
    setStatus('All')
    setSector('All')
    setGeography('All')
    setSearch('')
    setFocusedCompanyId(null)
    setActiveFilterSetId('')
  }

  useEffect(() => {
    if (user?.role !== 'company') return
    if (!companies.length) return
    if (!selectedCompanyId) {
      setSelectedCompanyId(companies[0].id)
    }
  }, [companies, selectedCompanyId, user?.role])

  useEffect(() => {
    if (user?.role !== 'company') return
    if (!selectedCompanyId) return
    const company = companies.find((item) => item.id === selectedCompanyId)
    if (!company) return
    setFormValues(createPrefilledFormValues(company))
  }, [companies, selectedCompanyId, user?.role])

  const selectedCompany = companies.find((item) => item.id === selectedCompanyId) || null
  const selectedCompanyRow = rows.find((item) => item.id === selectedCompanyId) || null

  useEffect(() => {
    formValuesRef.current = formValues
  }, [formValues])

  const handleFieldChange = (event) => {
    const { name, value } = event.target
    setFormValues((current) => ({ ...current, [name]: value }))
  }

  const submitPortfolioESG = async (event) => {
    event.preventDefault()
    if (!selectedCompany) return

    const errors = validatePortfolioForm(formValues)
    if (errors.length) {
      setFormMessage(errors[0])
      return
    }

    setIsSubmitting(true)
    setFormMessage('Submitting ESG data...')
    try {
      const response = await fetch(`${API_BASE_URL}/company/${selectedCompany.id}/submissions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildSubmissionPayload(formValues)),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Submission failed')
      }

      setFormMessage(`ESG submission saved for ${selectedCompany.name}.`)
      await refresh()
    } catch (submitError) {
      setFormMessage(submitError.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  useEffect(() => {
    if (user?.role !== 'company' || !selectedCompany) return
    
    const autoSaveInterval = setInterval(async () => {
      try {
      await fetch(`${API_BASE_URL}/company/${selectedCompany.id}/submissions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(buildSubmissionPayload(formValuesRef.current)),
        })
        console.log('Auto-saved at', new Date().toLocaleTimeString())
      } catch (e) { console.error('Auto-save failed', e) }
    }, 300000) // 5 minutes in milliseconds

    return () => clearInterval(autoSaveInterval)
  }, [selectedCompany, user?.role])

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="Submission Tracking" subtitle="Loading submission records from database...">
          <p>Loading data from backend.</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="Submission Tracking" subtitle="Live data unavailable">
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  if (user?.role === 'company') {
    return (
      <div className="page-grid">
        <SectionCard title="Submission Workspace" subtitle="Prepare and submit your ESG form with confidence and validation checks.">
          <div className="filter-bar">
            <label>
              <span>Company</span>
              <select
                value={selectedCompanyId || ''}
                onChange={(event) => setSelectedCompanyId(Number(event.target.value))}
              >
                {companies.map((company) => (
                  <option key={company.id} value={company.id}>{company.name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Current status</span>
              <div className="pt-2">
                <StatusBadge value={selectedCompanyRow?.status || 'Not Started'} />
              </div>
            </label>
            <label>
              <span>Latest ESG score</span>
              <p className="pt-2 text-sm ui-text-strong text-slate-700">{selectedCompanyRow?.esgScore ?? '--'}</p>
            </label>
            <label>
              <span>Deadline</span>
              <p className="pt-2 text-sm ui-text-strong text-slate-700">{selectedCompanyRow?.deadline || '--'}</p>
            </label>
          </div>

          {selectedCompany ? (
            <form onSubmit={submitPortfolioESG} className="space-y-4">

              {selectedCompany.current_status === 'pre-acquisition' && (
                <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4">
                  <h4 className="mb-2 text-base ui-text-strong text-indigo-800">Target Onboarding Workflow</h4>
                  <ul className="list-disc pl-5 text-sm text-indigo-700 space-y-1">
                    <li>Complete the lightweight Pre-Acquisition ESG Questionnaire below.</li>
                    <li>Upload initial compliance evidence (Policies & Certificates).</li>
                    <li>Submit for ESG Manager review to finalize acquisition onboarding.</li>
                  </ul>
                </div>
              )}

              <div className="rounded-xl border border-slate-200 bg-blue-50/50 p-4">
                <h4 className="mb-2 text-base ui-text-strong text-slate-800">Built-in GHG Calculator</h4>
                <div className="flex flex-wrap items-end gap-4">
                  <label className="flex-1 min-w-[150px]">
                    <span className="block text-sm font-medium text-slate-700">Fuel (Liters)</span>
                    <input type="number" id="calc_fuel" className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm mt-1" />
                  </label>
                  <label className="flex-1 min-w-[150px]">
                    <span className="block text-sm font-medium text-slate-700">Electricity (kWh)</span>
                    <input type="number" id="calc_elec" className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm mt-1" />
                  </label>
                  <Button type="button" className="button bg-blue-600 text-white" onClick={async () => {
                    const fuel = parseFloat(document.getElementById('calc_fuel').value) || 0;
                    const elec = parseFloat(document.getElementById('calc_elec').value) || 0;
                    try {
      const res = await fetch(`${API_BASE_URL}/calculator/ghg`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ fuel_liters: fuel, electricity_kwh: elec })
                      });
                      const data = await res.json();
                      setFormValues(prev => ({
                        ...prev,
                        scope_1_emissions: data.scope_1_tco2e.toString(),
                        scope_2_location_based: data.scope_2_tco2e.toString(),
                        total_ghg_emissions: data.total_tco2e.toString(),
                      }));
                      alert(`Calculated Total: ${data.total_tco2e} tCO2e`);
                    } catch(e) { alert("Calculator error") }
                  }}>Calculate & Apply</Button>
                </div>
              </div>

              <div className="flex overflow-x-auto border-b border-slate-200 mb-6 pb-2 gap-2">
                {ESG_FORM_SECTIONS.map((section) => (
                  <Button
                    key={section.key}
                    type="button"
                    className={`whitespace-nowrap py-2 px-4 rounded-lg ui-text-strong text-sm transition-colors ${activeTab === section.key ? 'bg-blue-600 text-white shadow-md' : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
                    onClick={() => setActiveTab(section.key)}
                  >
                    {section.title}
                  </Button>
                ))}
              </div>

              {ESG_FORM_SECTIONS.filter(s => s.key === activeTab).map((section) => (
                <div key={section.key} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
                  <h4 className="mb-1 text-base ui-text-strong text-slate-800">{section.title}</h4>
                  <p className="mb-4 text-sm text-slate-500">{section.description}</p>
                  <div className="grid gap-3 md:grid-cols-2">
                    {section.fields.map((field) => (
                      <div key={field.name} className="rounded-lg border border-slate-200 bg-white p-3">
                        <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor={field.name}>
                          {field.label}
                        </label>
                        <p className="mb-2 text-xs text-slate-500">{field.help}</p>

                        {field.type === 'textarea' ? (
                          <textarea
                            id={field.name}
                            name={field.name}
                            value={formValues[field.name]}
                            onChange={handleFieldChange}
                            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                          />
                        ) : field.type === 'select' ? (
                          <select
                            id={field.name}
                            name={field.name}
                            value={formValues[field.name]}
                            onChange={handleFieldChange}
                            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                          >
                            <option value="">Select</option>
                            {field.options.map((option) => (
                              <option key={option} value={option}>{option}</option>
                            ))}
                          </select>
                        ) : (
                          <input
                            id={field.name}
                            type={field.type}
                            name={field.name}
                            value={formValues[field.name]}
                            onChange={handleFieldChange}
                            min={field.min}
                            max={field.max}
                            step={field.step}
                            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                          />
                        )}

                        {field.type !== 'text' && field.type !== 'textarea' ? (
                          <div className="mt-2">
                            <label className="mb-1 block text-xs ui-text-strong uppercase tracking-wide text-slate-500" htmlFor={`${field.name}_confidence`}>
                              Data confidence
                            </label>
                            <select
                              id={`${field.name}_confidence`}
                              name={`${field.name}_confidence`}
                              value={formValues[`${field.name}_confidence`]}
                              onChange={handleFieldChange}
                              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                            >
                              <option value="">Select confidence</option>
                              {CONFIDENCE_OPTIONS.map((option) => (
                                <option key={option} value={option}>{option}</option>
                              ))}
                            </select>
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              {(formValues.whs_policy_in_place === 'Yes' || formValues.esg_policy_in_place === 'Yes' || formValues.cybersecurity_policy_in_place === 'Yes' || formValues.anti_bribery_corruption_policy === 'Yes') && (
                <div className="rounded-xl border border-slate-200 bg-white p-4 mt-4">
                  <label className="mb-1 block text-sm font-medium text-slate-700">Upload Evidence (Policies/Certificates)</label>
                  <div className="grid gap-3 mt-2 md:grid-cols-[1fr_auto]">
                    <input type="file" id="evidence_file" className="text-sm border border-slate-300 rounded-md p-1 w-full bg-slate-50" />
                    <Button type="button" className="button" onClick={async () => {
                      const fileInput = document.getElementById('evidence_file');
                      if (!fileInput?.files?.[0]) return alert('Select a file first');
                      const formData = new FormData();
                      formData.append('file', fileInput.files[0]);
                      try {
                        const res = await fetch(`${API_BASE_URL}/company/${selectedCompany.id}/upload-evidence`, {
                          method: 'POST', body: formData
                        });
                        const payload = await res.json().catch(() => ({}));
                        if (res.ok) {
                          setEvidenceExtraction(payload);
                          setFormMessage(payload?.message || 'Evidence uploaded successfully');
                          alert('Evidence uploaded successfully');
                        } else {
                          alert(payload?.detail || 'Upload failed');
                        }
                      } catch(e) { alert(e.message) }
                    }}>Upload File</Button>
                  </div>
                  {evidenceExtraction?.extraction_suggestions?.length > 0 ? (
                    <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <h5 className="mb-2 text-sm ui-text-strong text-slate-800">Document extraction suggestions</h5>
                      <div className="space-y-3">
                        {evidenceExtraction.extraction_suggestions.map((suggestion) => (
                          <div key={`${suggestion.field_key}-${suggestion.suggested_value}`} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <strong className="text-slate-800">{suggestion.field_key}</strong>
                              <span className="text-xs uppercase tracking-wide text-slate-500">{suggestion.confidence_level}</span>
                            </div>
                            <p className="mt-1 text-slate-600">{suggestion.explanation}</p>
                            {suggestion.source_excerpt ? <p className="mt-1 text-xs text-slate-500">Source: {suggestion.source_excerpt}</p> : null}
                            <div className="mt-3 flex flex-wrap items-center gap-2">
                              <Button
                                type="button"
                                className="button"
                                onClick={() => {
                                  setFormValues((current) => ({
                                    ...current,
                                    [suggestion.field_key]: suggestion.suggested_value || '',
                                  }))
                                  setFormMessage(`Applied suggestion for ${suggestion.field_key}.`)
                                }}
                              >
                                Apply suggestion
                              </Button>
                              <span className="text-xs text-slate-500">
                                Suggested value: {suggestion.suggested_value || 'Review manually'}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              )}

              <div className="rounded-xl border border-slate-200 bg-white p-4 mt-4">
                <h4 className="mb-4 text-base ui-text-strong text-slate-800">Action Plans & Improvement Initiatives</h4>
                <div className="mb-4">
                  {selectedCompany?.action_plans?.length > 0 ? (
                    <ul className="space-y-2">
                      {selectedCompany.action_plans.map(plan => (
                        <li key={plan.id} className="flex justify-between items-center text-sm p-2 bg-slate-50 rounded">
                          <span><strong>{plan.initiative_name}</strong> (Owner: {plan.assigned_owner})</span>
                          <span className="text-slate-500">Target: {plan.target_completion_date}</span>
                        </li>
                      ))}
                    </ul>
                  ) : <p className="text-sm text-slate-500">No action plans logged yet.</p>}
                </div>
                <div className="grid gap-2 md:grid-cols-4">
                  <input type="text" id="ap_name" placeholder="Initiative Name" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
                  <input type="text" id="ap_owner" placeholder="Owner" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
                  <input type="date" id="ap_date" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
                  <Button type="button" className="button bg-indigo-600 text-white whitespace-nowrap md:self-end" onClick={async () => {
                    const name = document.getElementById('ap_name').value;
                    const owner = document.getElementById('ap_owner').value;
                    const date = document.getElementById('ap_date').value;
                    if (!name || !owner || !date) return alert('Fill all fields');
                    try {
      const res = await fetch(`${API_BASE_URL}/company/${selectedCompany.id}/action-plans`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ initiative_name: name, assigned_owner: owner, target_completion_date: date })
                      });
                      if (res.ok) { alert('Action Plan created'); refresh(); }
                    } catch (e) { alert(e.message) }
                  }}>Add Plan</Button>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="submission_notes">
                  Variance Explanation & Submission Notes
                </label>
                <textarea
                  id="submission_notes"
                  name="submission_notes"
                  value={formValues.submission_notes}
                  onChange={handleFieldChange}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                  placeholder="Required if any metric varies by >30% year-on-year. Add any additional assumptions here."
                />
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button className="button" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Submitting...' : 'Submit ESG Form'}
                </Button>
                <Button
                  className="button"
                  type="button"
                  onClick={() => selectedCompany && setFormValues(createPrefilledFormValues(selectedCompany))}
                >
                  Reset to latest saved
                </Button>
                {formMessage ? <p className="action-message">{formMessage}</p> : null}
              </div>
            </form>
          ) : (
            <p>No company linked to this account yet.</p>
          )}
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <SectionCard title="Submission Tracking" subtitle="Filter and review submission progress by company">
        <div className="saved-filter-toolbar">
          <label>
            <span>Saved views</span>
            <select
              value={activeFilterSetId}
              onChange={(event) => {
                const nextId = event.target.value
                setActiveFilterSetId(nextId)
                if (!nextId) return
                const preset = savedFilterSets.find((item) => item.id === nextId)
                applySavedFilterSet(preset)
              }}
            >
              <option value="">Last used</option>
              {savedFilterSets.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.name}
                </option>
              ))}
            </select>
          </label>

          <div className="action-row">
            <Button type="button" variant="secondary" onClick={handleSaveCurrentFilters}>
              Save current view
            </Button>
            <Button type="button" variant="secondary" onClick={handleDeleteSavedFilter} disabled={!activeSavedFilter}>
              Delete saved view
            </Button>
            <Button type="button" variant="ghost" onClick={clearFilters}>
              Clear filters
            </Button>
          </div>
        </div>

        {focusedCompanyId ? (
          <div className="saved-filter-note">
            Focusing search on company ID {focusedCompanyId}. Clear filters to see the full submission table.
          </div>
        ) : null}

        <div className="filter-bar sticky">
          <label>
            <span>Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              {options.statuses.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>

          <label>
            <span>Sector</span>
            <select value={sector} onChange={(event) => setSector(event.target.value)}>
              {options.sectors.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>

          <label>
            <span>Geography</span>
            <select value={geography} onChange={(event) => setGeography(event.target.value)}>
              {options.geographies.map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
          </label>

          <label>
            <span>Search</span>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search company"
            />
          </label>
        </div>

        {user?.role === 'investor' && (
          <div className="flex gap-4 mb-6">
             {REPORT_FRAMEWORK_OPTIONS.map((framework) => (
               <Button
                 key={framework.id}
                 className="button"
                 onClick={() => handleDownloadReport(framework.id)}
               >
                 Generate {framework.label} Report
               </Button>
             ))}
          </div>
        )}

        {user?.role === 'investor' && investorChartData.length > 0 && (
          <div className="mb-8 grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="rounded-xl border border-slate-200 bg-white p-4 h-80">
              <h4 className="text-sm ui-text-strong mb-4 text-slate-700">Portfolio Emissions (tCO2e)</h4>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={investorChartData} margin={{ top: 10, right: 30, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={60} tick={{fontSize: 12}} />
                  <YAxis tick={{fontSize: 12}} />
                  <Tooltip />
                  <Legend verticalAlign="top" height={36} />
                  <Bar dataKey="scope1" stackId="a" fill={CHART_COLORS.scope1} name="Scope 1" />
                  <Bar dataKey="scope2" stackId="a" fill={CHART_COLORS.scope2} name="Scope 2" />
                  <Bar dataKey="scope3" stackId="a" fill={CHART_COLORS.scope3} name="Scope 3" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 h-80">
              <h4 className="text-sm ui-text-strong mb-4 text-slate-700">Female Leadership Representation (%)</h4>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={investorChartData} margin={{ top: 10, right: 30, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={60} tick={{fontSize: 12}} />
                  <YAxis tick={{fontSize: 12}} domain={[0, 100]} />
                  <Tooltip />
                  <Legend verticalAlign="top" height={36} />
                  <Bar dataKey="femaleLeadership" fill={CHART_COLORS.pink} name="% Female Leadership" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        <DataTable columns={columns} rows={filteredRows} pageSize={12} rowClassName={rowClassName} />
      </SectionCard>
    </div>
  )
}


