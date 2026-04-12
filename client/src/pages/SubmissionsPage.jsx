import { useEffect, useMemo, useState, useRef } from 'react'
import { useOutletContext } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
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

const BACKEND_URL = 'http://127.0.0.1:8000'

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
  const { companies, cycles, loading, error, refresh } = useDashboardData(user)
  const [status, setStatus] = useState('All')
  const [sector, setSector] = useState('All')
  const [geography, setGeography] = useState('All')
  const [search, setSearch] = useState('')
  const [selectedCompanyId, setSelectedCompanyId] = useState(null)
  const [formValues, setFormValues] = useState(createInitialFormValues)
  const [formMessage, setFormMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const formValuesRef = useRef(formValues)
  const [activeTab, setActiveTab] = useState(ESG_FORM_SECTIONS.length ? ESG_FORM_SECTIONS[0].key : '')

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

  const handleValidate = async (submissionId) => {
    try {
      const res = await fetch(`${BACKEND_URL}/submissions/${submissionId}/validate`, { method: 'POST' })
      if (!res.ok) throw new Error('Validation failed')
      alert('Validation complete. Anomalies flagged.')
      refresh()
    } catch(e) { alert(e.message) }
  }

  const handleReview = async (submissionId, status) => {
    try {
      const res = await fetch(`${BACKEND_URL}/submissions/${submissionId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer_role: 'Manager', review_status: status, review_comment: 'Reviewed via dashboard' })
      })
      if (!res.ok) throw new Error('Review failed')
      alert(`Submission marked as ${status}`)
      refresh()
    } catch(e) { alert(e.message) }
  }

  const handleDownloadReport = async (type) => {
    try {
      const res = await fetch(`${BACKEND_URL}/reports/${type}`)
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
      const searchMatch = !search.trim() || row.companyName.toLowerCase().includes(search.toLowerCase())
      return statusMatch && sectorMatch && geoMatch && searchMatch
    })
  }, [geography, rows, search, sector, status])

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
        row.flags > 0 ? <span className="text-red-600 font-bold">{row.flags} Flag(s)</span> : <span className="text-slate-400">None</span>
      )
    })
    columns.push({
      key: 'actions', label: 'Actions', render: (row) => (
        <div className="flex items-center gap-3">
          {row.currentStatus === 'pre-acquisition' && (
            <button className="text-xs text-indigo-600 font-bold uppercase tracking-wide hover:underline" onClick={async () => {
              try {
                const res = await fetch(`${BACKEND_URL}/company/${row.id}/onboarding/complete`, { method: 'POST' });
                if (!res.ok) throw new Error('Failed to complete onboarding');
                alert('Company onboarded successfully!');
                refresh();
              } catch(e) { alert(e.message) }
            }}>Onboard</button>
          )}
          {row.submissionId ? (
            <>
              <button className="text-xs text-blue-600 font-bold uppercase tracking-wide hover:underline" onClick={() => handleValidate(row.submissionId)}>Validate</button>
              <button className="text-xs text-green-600 font-bold uppercase tracking-wide hover:underline" onClick={() => handleReview(row.submissionId, 'approved')}>Approve</button>
              <button className="text-xs text-orange-600 font-bold uppercase tracking-wide hover:underline" onClick={() => handleReview(row.submissionId, 'resubmission requested')}>Resubmit</button>
              <button className="text-xs text-red-600 font-bold uppercase tracking-wide hover:underline" onClick={() => handleReview(row.submissionId, 'rejected')}>Reject</button>
            </>
          ) : (
            <span className="text-xs text-slate-400">No Submission</span>
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
      const response = await fetch(`${BACKEND_URL}/company/${selectedCompany.id}/submissions`, {
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
        await fetch(`${BACKEND_URL}/company/${selectedCompany.id}/submissions`, {
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
              <p className="pt-2 text-sm font-semibold text-slate-700">{selectedCompanyRow?.esgScore ?? '--'}</p>
            </label>
            <label>
              <span>Deadline</span>
              <p className="pt-2 text-sm font-semibold text-slate-700">{selectedCompanyRow?.deadline || '--'}</p>
            </label>
          </div>

          {selectedCompany ? (
            <form onSubmit={submitPortfolioESG} className="space-y-4">

              {selectedCompany.current_status === 'pre-acquisition' && (
                <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4">
                  <h4 className="mb-2 text-base font-semibold text-indigo-800">Target Onboarding Workflow</h4>
                  <ul className="list-disc pl-5 text-sm text-indigo-700 space-y-1">
                    <li>Complete the lightweight Pre-Acquisition ESG Questionnaire below.</li>
                    <li>Upload initial compliance evidence (Policies & Certificates).</li>
                    <li>Submit for ESG Manager review to finalize acquisition onboarding.</li>
                  </ul>
                </div>
              )}

              <div className="rounded-xl border border-slate-200 bg-blue-50/50 p-4">
                <h4 className="mb-2 text-base font-semibold text-slate-800">Built-in GHG Calculator</h4>
                <div className="flex flex-wrap items-end gap-4">
                  <label className="flex-1 min-w-[150px]">
                    <span className="block text-sm font-medium text-slate-700">Fuel (Liters)</span>
                    <input type="number" id="calc_fuel" className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm mt-1" />
                  </label>
                  <label className="flex-1 min-w-[150px]">
                    <span className="block text-sm font-medium text-slate-700">Electricity (kWh)</span>
                    <input type="number" id="calc_elec" className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm mt-1" />
                  </label>
                  <button type="button" className="button bg-blue-600 text-white" onClick={async () => {
                    const fuel = parseFloat(document.getElementById('calc_fuel').value) || 0;
                    const elec = parseFloat(document.getElementById('calc_elec').value) || 0;
                    try {
                      const res = await fetch(`${BACKEND_URL}/calculator/ghg`, {
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
                  }}>Calculate & Apply</button>
                </div>
              </div>

              <div className="flex overflow-x-auto border-b border-slate-200 mb-6 pb-2 gap-2">
                {ESG_FORM_SECTIONS.map((section) => (
                  <button
                    key={section.key}
                    type="button"
                    className={`whitespace-nowrap py-2 px-4 rounded-lg font-semibold text-sm transition-colors ${activeTab === section.key ? 'bg-blue-600 text-white shadow-md' : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'}`}
                    onClick={() => setActiveTab(section.key)}
                  >
                    {section.title}
                  </button>
                ))}
              </div>

              {ESG_FORM_SECTIONS.filter(s => s.key === activeTab).map((section) => (
                <div key={section.key} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
                  <h4 className="mb-1 text-base font-semibold text-slate-800">{section.title}</h4>
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
                            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor={`${field.name}_confidence`}>
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
                    <button type="button" className="button" onClick={async () => {
                      const fileInput = document.getElementById('evidence_file');
                      if (!fileInput?.files?.[0]) return alert('Select a file first');
                      const formData = new FormData();
                      formData.append('file', fileInput.files[0]);
                      try {
                        const res = await fetch(`${BACKEND_URL}/company/${selectedCompany.id}/upload-evidence`, {
                          method: 'POST', body: formData
                        });
                        if (res.ok) alert('Evidence uploaded successfully');
                        else alert('Upload failed');
                      } catch(e) { alert(e.message) }
                    }}>Upload File</button>
                  </div>
                </div>
              )}

              <div className="rounded-xl border border-slate-200 bg-white p-4 mt-4">
                <h4 className="mb-4 text-base font-semibold text-slate-800">Action Plans & Improvement Initiatives</h4>
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
                  <button type="button" className="button bg-indigo-600 text-white whitespace-nowrap md:self-end" onClick={async () => {
                    const name = document.getElementById('ap_name').value;
                    const owner = document.getElementById('ap_owner').value;
                    const date = document.getElementById('ap_date').value;
                    if (!name || !owner || !date) return alert('Fill all fields');
                    try {
                      const res = await fetch(`${BACKEND_URL}/company/${selectedCompany.id}/action-plans`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ initiative_name: name, assigned_owner: owner, target_completion_date: date })
                      });
                      if (res.ok) { alert('Action Plan created'); refresh(); }
                    } catch (e) { alert(e.message) }
                  }}>Add Plan</button>
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
                <button className="button" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Submitting...' : 'Submit ESG Form'}
                </button>
                <button
                  className="button"
                  type="button"
                  onClick={() => selectedCompany && setFormValues(createPrefilledFormValues(selectedCompany))}
                >
                  Reset to latest saved
                </button>
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
             <button className="button bg-emerald-600 text-white" onClick={() => handleDownloadReport('edci')}>Generate EDCI Report</button>
             <button className="button bg-blue-600 text-white" onClick={() => handleDownloadReport('sfdr')}>Generate SFDR Report</button>
          </div>
        )}

        {user?.role === 'investor' && investorChartData.length > 0 && (
          <div className="mb-8 grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="rounded-xl border border-slate-200 bg-white p-4 h-80">
              <h4 className="text-sm font-semibold mb-4 text-slate-700">Portfolio Emissions (tCO2e)</h4>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={investorChartData} margin={{ top: 10, right: 30, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={60} tick={{fontSize: 12}} />
                  <YAxis tick={{fontSize: 12}} />
                  <Tooltip />
                  <Legend verticalAlign="top" height={36} />
                  <Bar dataKey="scope1" stackId="a" fill="#3b82f6" name="Scope 1" />
                  <Bar dataKey="scope2" stackId="a" fill="#10b981" name="Scope 2" />
                  <Bar dataKey="scope3" stackId="a" fill="#6366f1" name="Scope 3" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4 h-80">
              <h4 className="text-sm font-semibold mb-4 text-slate-700">Female Leadership Representation (%)</h4>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={investorChartData} margin={{ top: 10, right: 30, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={60} tick={{fontSize: 12}} />
                  <YAxis tick={{fontSize: 12}} domain={[0, 100]} />
                  <Tooltip />
                  <Legend verticalAlign="top" height={36} />
                  <Bar dataKey="femaleLeadership" fill="#ec4899" name="% Female Leadership" />
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
