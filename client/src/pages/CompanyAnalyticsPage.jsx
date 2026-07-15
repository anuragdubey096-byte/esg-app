import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import DataTable from '../components/DataTable'
import ExecutivePageHeader from '../components/ExecutivePageHeader'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import SectionLoadState from '../components/SectionLoadState'
import useDashboardData, {
  calculateESGPillarScores, getAvailableReportingYears, getSortedSubmissions, getSubmissionForReportingYear,
  getSubmissionReportingYear, normalizeStatus, parseSubmissionPayload,
} from '../hooks/useDashboardData'
import { API_BASE_URL } from '../lib/api'

const REQUIRED_FIELDS = [
  'scope_1_emissions', 'scope_2_location_based', 'scope_3_emissions', 'total_ghg_emissions',
  'total_energy_consumption', 'total_water_withdrawal', 'total_waste_generated',
  'female_representation_percent', 'trifr', 'independent_board_members_percent',
]

const GOVERNANCE_FIELDS = [
  'esg_policy_in_place', 'board_level_esg_oversight', 'esg_kpis_linked_to_remuneration',
  'cybersecurity_policy_in_place', 'anti_bribery_corruption_policy',
]

function numberValue(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function yesValue(value) {
  return String(value || '').trim().toLowerCase() === 'yes'
}

export default function CompanyAnalyticsPage() {
  const { user } = useOutletContext()
  const { companies, loading, error, retrySection, sections, isRefreshing } = useDashboardData(user)
  const company = companies[0] || null
  const submissions = useMemo(() => getSortedSubmissions(company), [company])
  const years = useMemo(() => getAvailableReportingYears(submissions), [submissions])
  const [selectedYear, setSelectedYear] = useState('Latest')
  const [targets, setTargets] = useState([])
  const [evidence, setEvidence] = useState([])

  const selectedSubmission = useMemo(
    () => getSubmissionForReportingYear(submissions, selectedYear),
    [selectedYear, submissions],
  )
  const payload = useMemo(() => parseSubmissionPayload(selectedSubmission) || {}, [selectedSubmission])
  const scores = useMemo(() => (selectedSubmission ? calculateESGPillarScores(payload) : null) || {
    environmental: 0, social: 0, governance: 0, composite: 0,
  }, [payload, selectedSubmission])

  useEffect(() => {
    if (!company?.id) return undefined
    const controller = new AbortController()
    const headers = { 'x-user-role': user?.role || '', 'x-user-email': user?.email || '' }
    Promise.all([
      fetch(`${API_BASE_URL}/targets`, { headers, signal: controller.signal }).then((response) => response.ok ? response.json() : []),
      fetch(`${API_BASE_URL}/company/${company.id}/draft`, { headers, signal: controller.signal }).then((response) => response.ok ? response.json() : {}),
    ]).then(([targetRows, draft]) => {
      setTargets(Array.isArray(targetRows) ? targetRows : [])
      setEvidence(Array.isArray(draft?.evidence) ? draft.evidence : [])
    }).catch((requestError) => {
      if (requestError.name !== 'AbortError') {
        setTargets([])
        setEvidence([])
      }
    })
    return () => controller.abort()
  }, [company?.id, user?.email, user?.role])

  const trendRows = useMemo(() => submissions.map((submission) => {
    const values = parseSubmissionPayload(submission) || {}
    const pillarScores = calculateESGPillarScores(values) || {}
    const emissions = numberValue(values.total_ghg_emissions) || (
      numberValue(values.scope_1_emissions) + numberValue(values.scope_2_location_based) + numberValue(values.scope_3_emissions)
    )
    return {
      year: getSubmissionReportingYear(submission) || `Submission ${submission.id}`,
      emissions,
      environmental: Number(pillarScores.environmental || 0).toFixed(1),
      social: Number(pillarScores.social || 0).toFixed(1),
      governance: Number(pillarScores.governance || 0).toFixed(1),
      composite: Number(pillarScores.composite || 0).toFixed(1),
    }
  }), [submissions])

  const completeness = REQUIRED_FIELDS.length
    ? ((REQUIRED_FIELDS.filter((field) => payload[field] !== null && payload[field] !== undefined && payload[field] !== '').length / REQUIRED_FIELDS.length) * 100)
    : 0
  const confidenceValues = Object.entries(payload).filter(([key]) => key.endsWith('_confidence')).map(([, value]) => String(value || '').toLowerCase())
  const measuredConfidence = confidenceValues.length
    ? (confidenceValues.filter((value) => value === 'measured').length / confidenceValues.length) * 100
    : 0
  const reportingYear = getSubmissionReportingYear(selectedSubmission)
  const validationFlags = (company?.validation_flags || []).filter((flag) => !reportingYear || Number(flag.reporting_year) === Number(reportingYear))
  const governanceAdoption = (GOVERNANCE_FIELDS.filter((field) => yesValue(payload[field])).length / GOVERNANCE_FIELDS.length) * 100
  const resourceRows = [
    { metric: 'Energy (MWh)', value: numberValue(payload.total_energy_consumption) },
    { metric: 'Water (m³)', value: numberValue(payload.total_water_withdrawal) },
    { metric: 'Waste (t)', value: numberValue(payload.total_waste_generated) },
  ]

  if (loading) return <div className="page-grid"><SectionCard title="Company Analytics" subtitle="Loading company performance…"><p>Loading reporting data.</p></SectionCard></div>
  if (error) return <div className="page-grid"><SectionCard title="Company Analytics" subtitle="Live data unavailable"><SectionLoadState error={error} onRetry={() => retrySection('dashboard')} /></SectionCard></div>

  return (
    <div className="page-grid">
      <ExecutivePageHeader
        eyebrow="Company analytics"
        title={`${company?.name || 'Company'} ESG performance`}
        description="Track reporting quality, ESG performance, historical movement, evidence, targets, and open actions from your company data."
        meta={[
          { label: 'Reporting year', value: reportingYear || 'No submission' },
          { label: 'Status', value: normalizeStatus(selectedSubmission?.status || 'Not Started') },
          { label: 'Historical periods', value: submissions.length },
        ]}
        actions={years.length ? (
          <label className="analytics-filter-field"><span>Reporting cycle</span><select value={selectedYear} onChange={(event) => setSelectedYear(event.target.value)}><option value="Latest">Latest</option>{years.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
        ) : null}
      />

      <SectionLoadState loading={isRefreshing} error={sections.dashboard.error} cached={Boolean(company)} onRetry={() => retrySection('dashboard')} />

      <section className="executive-kpi-grid">
        <KpiCard title="ESG Score" value={selectedSubmission ? `${Number(scores.composite).toFixed(1)}/100` : 'N/A'} trendLabel={selectedSubmission ? 'current composite' : 'submit data to calculate'} icon="analytics" />
        <KpiCard title="Completeness" value={`${completeness.toFixed(1)}%`} trendLabel="required metrics" icon="submissions" />
        <KpiCard title="Measured Confidence" value={`${measuredConfidence.toFixed(1)}%`} trendLabel="confidence-tagged values" icon="review" />
        <KpiCard title="Validation Flags" value={validationFlags.length} trendLabel="selected reporting cycle" icon="risks" tone={validationFlags.length ? 'amber' : undefined} />
        <KpiCard title="Evidence Files" value={evidence.length} trendLabel="active-cycle attachments" icon="reports" />
        <KpiCard title="Open Targets" value={targets.filter((target) => target.status !== 'achieved').length} trendLabel={`${targets.length} total targets`} icon="actions" />
      </section>

      {!selectedSubmission ? <div className="analytics-empty-scope"><strong>No submission data yet</strong><p>Start the submission form to populate company analytics.</p></div> : null}

      <section className="two-col-grid">
        <SectionCard title="ESG pillar scores" subtitle="Environmental, social, governance and composite performance">
          <div className="chart-wrap"><ResponsiveContainer width="100%" height={300}><BarChart data={[
            { pillar: 'Environmental', score: Number(scores.environmental.toFixed(1)) },
            { pillar: 'Social', score: Number(scores.social.toFixed(1)) },
            { pillar: 'Governance', score: Number(scores.governance.toFixed(1)) },
          ]}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="pillar" /><YAxis domain={[0, 100]} /><Tooltip /><Bar dataKey="score" fill="#0f766e" radius={[8, 8, 0, 0]} /></BarChart></ResponsiveContainer></div>
        </SectionCard>
        <SectionCard title="Historical ESG score" subtitle="Composite performance by reporting year">
          <div className="chart-wrap"><ResponsiveContainer width="100%" height={300}><LineChart data={trendRows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="year" /><YAxis domain={[0, 100]} /><Tooltip /><Line type="monotone" dataKey="composite" stroke="#2563eb" strokeWidth={3} /></LineChart></ResponsiveContainer></div>
        </SectionCard>
      </section>

      <section className="two-col-grid">
        <SectionCard title="Emissions trend" subtitle="Total Scope 1, 2 and 3 emissions by year">
          <div className="chart-wrap"><ResponsiveContainer width="100%" height={300}><LineChart data={trendRows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="year" /><YAxis /><Tooltip /><Line type="monotone" dataKey="emissions" stroke="#f97316" strokeWidth={3} name="tCO2e" /></LineChart></ResponsiveContainer></div>
        </SectionCard>
        <SectionCard title="Resource use" subtitle="Selected reporting cycle">
          <div className="chart-wrap"><ResponsiveContainer width="100%" height={300}><BarChart data={resourceRows} layout="vertical"><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis type="number" /><YAxis dataKey="metric" type="category" width={95} /><Tooltip /><Bar dataKey="value" fill="#0284c7" radius={[0, 8, 8, 0]} /></BarChart></ResponsiveContainer></div>
        </SectionCard>
      </section>

      <section className="executive-kpi-grid">
        <KpiCard title="Female Representation" value={`${numberValue(payload.female_representation_percent).toFixed(1)}%`} trendLabel="workforce" />
        <KpiCard title="Female Leadership" value={`${numberValue(payload.female_leadership_representation_percent).toFixed(1)}%`} trendLabel="leadership" />
        <KpiCard title="TRIFR" value={numberValue(payload.trifr).toFixed(2)} trendLabel="safety frequency rate" />
        <KpiCard title="Governance Adoption" value={`${governanceAdoption.toFixed(1)}%`} trendLabel="key policies and oversight" />
      </section>

      <SectionCard title="Targets and actions" subtitle="Execution items tied to company performance">
        <DataTable
          columns={[
            { key: 'type', label: 'Type', sortable: true }, { key: 'name', label: 'Target / action', sortable: true },
            { key: 'owner', label: 'Owner', sortable: true }, { key: 'due', label: 'Due', sortable: true },
            { key: 'progress', label: 'Progress', sortable: true }, { key: 'status', label: 'Status', sortable: true },
          ]}
          rows={[
            ...targets.map((target) => ({ id: `target-${target.id}`, type: 'Target', name: target.target_name, owner: target.owner, due: target.target_date, progress: `${target.progress_percent}%`, status: target.status })),
            ...(company?.action_plans || []).map((action) => ({ id: `action-${action.id}`, type: 'Action', name: action.initiative_name, owner: action.assigned_owner, due: action.target_completion_date, progress: '—', status: action.status })),
          ]}
          pageSize={8}
          emptyMessage="No targets or action plans are recorded."
        />
      </SectionCard>
    </div>
  )
}
