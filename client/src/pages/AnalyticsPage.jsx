import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import DataTable from '../components/DataTable'
import ExecutivePageHeader from '../components/ExecutivePageHeader'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import useDashboardData, { calculateESGPillarScores, getLatestSubmission, getSortedSubmissions, getSubmissionReportingYear, parseSubmissionPayload } from '../hooks/useDashboardData'
import { API_BASE_URL } from '../lib/api'

const analyticsTabs = ['Environmental', 'Social', 'Governance', 'Data Quality', 'Benchmarking']

function toNumber(value) {
  if (value === null || value === undefined || value === '') return 0
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function toAverage(total, count) {
  if (!count) return 0
  return total / count
}

function toPct(value) {
  return Math.max(0, Math.min(100, Number(value || 0)))
}

function isYes(value) {
  return String(value || '').trim().toLowerCase() === 'yes'
}

function firstMeaningfulNumber(...values) {
  for (const value of values) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return 0
}

export default function AnalyticsPage() {
  const { user } = useOutletContext()
  const { companies, cycles, loading, error } = useDashboardData(user)
  const [activeTab, setActiveTab] = useState(analyticsTabs[0])
  const [selectedSector, setSelectedSector] = useState('All')
  const [selectedCompany, setSelectedCompany] = useState('All')
  const [selectedCycle, setSelectedCycle] = useState('Latest')
  const [qualityData, setQualityData] = useState(null)
  const [qualityLoading, setQualityLoading] = useState(true)
  const [qualityError, setQualityError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const query = selectedCycle === 'Latest' ? '' : `?cycle_year=${encodeURIComponent(selectedCycle)}`
    setQualityLoading(true)
    setQualityError('')
    fetch(`${API_BASE_URL}/analytics/data-quality${query}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}))
          throw new Error(payload.detail || 'Unable to load data-quality analytics.')
        }
        return response.json()
      })
      .then(setQualityData)
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') setQualityError(requestError.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setQualityLoading(false)
      })
    return () => controller.abort()
  }, [selectedCycle])

  const sectorOptions = useMemo(() => (
    ['All', ...new Set(companies.map((company) => company.sector || 'Unassigned'))]
  ), [companies])
  const companyOptions = useMemo(() => companies.filter((company) => (
    selectedSector === 'All' || (company.sector || 'Unassigned') === selectedSector
  )), [companies, selectedSector])
  const scopedCompanies = useMemo(() => companies.filter((company) => {
    const sectorMatch = selectedSector === 'All' || (company.sector || 'Unassigned') === selectedSector
    const companyMatch = selectedCompany === 'All' || String(company.id) === selectedCompany
    return sectorMatch && companyMatch
  }), [companies, selectedCompany, selectedSector])

  const analytics = useMemo(() => {
    const records = scopedCompanies
      .map((company) => {
        const submissions = getSortedSubmissions(company)
        const latestSubmission = selectedCycle === 'Latest'
          ? getLatestSubmission(company)
          : [...submissions].reverse().find((submission) => String(getSubmissionReportingYear(submission)) === selectedCycle)
        const payload = parseSubmissionPayload(latestSubmission)
        if (!payload || typeof payload !== 'object') return null
        const currentIndex = submissions.findIndex((submission) => submission.id === latestSubmission?.id)
        const previousPayload = currentIndex > 0 ? parseSubmissionPayload(submissions[currentIndex - 1]) : null
        return {
          companyId: company.id,
          companyName: company.name,
          sector: company.sector || 'Unassigned',
          payload,
          previousPayload,
          validationFlagCount: (company.validation_flags || []).length,
        }
      })
      .filter(Boolean)

    const sectorMap = new Map()
    const emissionsScopeTotals = { scope1: 0, scope2: 0, scope3: 0 }
    let totalEnergy = 0
    let renewableEnergy = 0
    let totalFemaleRep = 0
    let totalFemaleLeadership = 0
    let totalTRIFR = 0
    let totalIndependentBoard = 0
    let policyChecks = 0
    let policyYes = 0
    let measuredConfidence = 0
    let totalConfidence = 0

    const benchmarkRows = records.map((record) => {
      const payload = record.payload
      const scope1 = toNumber(payload.scope_1_emissions)
      const scope2 = firstMeaningfulNumber(payload.scope_2_location_based, payload.scope_2_market_based)
      const scope3 = toNumber(payload.scope_3_emissions)
      const emissions = firstMeaningfulNumber(payload.total_ghg_emissions, scope1 + scope2 + scope3)
      const energy = toNumber(payload.total_energy_consumption)
      const renewable = toNumber(payload.renewable_energy_consumption)
      const water = toNumber(payload.total_water_withdrawal)
      const waste = toNumber(payload.total_waste_generated)
      const trifr = toNumber(payload.trifr)
      const femaleRep = toPct(payload.female_representation_percent)
      const femaleLeadership = toPct(payload.female_leadership_representation_percent)
      const independentBoard = toPct(payload.independent_board_members_percent)
      const employees = toNumber(payload.total_employees_fte)

      const policyFields = [
        payload.esg_policy_in_place,
        payload.whs_policy_in_place,
        payload.cybersecurity_policy_in_place,
        payload.board_level_esg_oversight,
      ]
      const policyYesCount = policyFields.filter((value) => isYes(value)).length
      const renewableShare = energy > 0 ? (renewable / energy) * 100 : 0
      const emissionsIntensity = employees > 0 ? emissions / employees : 0
      const pillarScores = calculateESGPillarScores(payload)
      const environmentScore = pillarScores?.environmental || 0
      const socialScore = pillarScores?.social || 0
      const governanceScore = pillarScores?.governance || 0
      const compositeScore = pillarScores?.composite || 0
      const previousScores = calculateESGPillarScores(record.previousPayload)
      const previousEmissions = toNumber(record.previousPayload?.total_ghg_emissions)
      const actualReduction = previousEmissions > 0 ? ((previousEmissions - emissions) / previousEmissions) * 100 : 0
      const missingCount = Object.values(payload).filter((value) => value === '' || value === null || value === undefined).length
      const estimatedCount = Object.entries(payload).filter(([key, value]) => key.endsWith('_confidence') && value !== 'Measured').length

      emissionsScopeTotals.scope1 += scope1
      emissionsScopeTotals.scope2 += scope2
      emissionsScopeTotals.scope3 += scope3
      totalEnergy += energy
      renewableEnergy += renewable
      totalFemaleRep += femaleRep
      totalFemaleLeadership += femaleLeadership
      totalTRIFR += trifr
      totalIndependentBoard += independentBoard
      policyChecks += policyFields.length
      policyYes += policyYesCount

      Object.keys(payload).forEach((key) => {
        if (!key.endsWith('_confidence')) return
        totalConfidence += 1
        if (String(payload[key] || '').trim().toLowerCase() === 'measured') measuredConfidence += 1
      })

      const sectorKey = record.sector
      if (!sectorMap.has(sectorKey)) {
        sectorMap.set(sectorKey, {
          sector: sectorKey,
          companies: 0,
          scope1: 0,
          scope2: 0,
          scope3: 0,
          energy: 0,
          water: 0,
          waste: 0,
          trifrTotal: 0,
          femaleRepTotal: 0,
          femaleLeadershipTotal: 0,
          governanceYes: 0,
          governanceChecks: 0,
          emissionsIntensityTotal: 0,
          emissionsIntensityCount: 0,
        })
      }
      const sector = sectorMap.get(sectorKey)
      sector.companies += 1
      sector.scope1 += scope1
      sector.scope2 += scope2
      sector.scope3 += scope3
      sector.energy += energy
      sector.water += water
      sector.waste += waste
      sector.trifrTotal += trifr
      sector.femaleRepTotal += femaleRep
      sector.femaleLeadershipTotal += femaleLeadership
      sector.governanceYes += policyYesCount
      sector.governanceChecks += policyFields.length
      if (emissionsIntensity > 0) {
        sector.emissionsIntensityTotal += emissionsIntensity
        sector.emissionsIntensityCount += 1
      }

      return {
        id: record.companyId,
        company: record.companyName,
        sector: record.sector,
        compositeScore: Number(compositeScore.toFixed(1)),
        environmentScore: Number(environmentScore.toFixed(1)),
        socialScore: Number(socialScore.toFixed(1)),
        governanceScore: Number(governanceScore.toFixed(1)),
        emissions: Number(emissions.toFixed(2)),
        emissionsIntensity: Number(emissionsIntensity.toFixed(3)),
        renewableShare: Number(renewableShare.toFixed(1)),
        femaleLeadership: Number(femaleLeadership.toFixed(1)),
        independentBoard: Number(independentBoard.toFixed(1)),
        previousComposite: Number((previousScores?.composite || 0).toFixed(1)),
        scoreChange: Number((compositeScore - (previousScores?.composite || compositeScore)).toFixed(1)),
        reductionTarget: Number(toNumber(payload.reduction_target_percent).toFixed(1)),
        actualReduction: Number(actualReduction.toFixed(1)),
        missingValues: missingCount,
        estimatedValues: estimatedCount,
        validationFlags: record.validationFlagCount,
        dataIssues: missingCount + estimatedCount + record.validationFlagCount,
      }
    })

    const sectorRows = Array.from(sectorMap.values()).map((item) => {
      const totalSectorEmissions = item.scope1 + item.scope2 + item.scope3
      return {
        sector: item.sector,
        scope1: Number(item.scope1.toFixed(2)),
        scope2: Number(item.scope2.toFixed(2)),
        scope3: Number(item.scope3.toFixed(2)),
        totalEmissions: Number(totalSectorEmissions.toFixed(2)),
        avgTRIFR: Number(toAverage(item.trifrTotal, item.companies).toFixed(2)),
        avgFemaleRep: Number(toAverage(item.femaleRepTotal, item.companies).toFixed(1)),
        avgFemaleLeadership: Number(toAverage(item.femaleLeadershipTotal, item.companies).toFixed(1)),
        governanceAdoption: Number(
          (item.governanceChecks ? (item.governanceYes / item.governanceChecks) * 100 : 0).toFixed(1)
        ),
        avgIntensity: Number(
          toAverage(item.emissionsIntensityTotal, item.emissionsIntensityCount || item.companies).toFixed(3)
        ),
      }
    })

    const scopeMixData = [
      { name: 'Scope 1', value: Number(emissionsScopeTotals.scope1.toFixed(2)), color: '#0f766e' },
      { name: 'Scope 2', value: Number(emissionsScopeTotals.scope2.toFixed(2)), color: '#0284c7' },
      { name: 'Scope 3', value: Number(emissionsScopeTotals.scope3.toFixed(2)), color: '#f97316' },
    ]

    const workforceMix = [
      { name: 'Women', value: Number(toAverage(totalFemaleRep, records.length).toFixed(1)), color: '#ec4899' },
      { name: 'Other', value: Number((100 - toAverage(totalFemaleRep, records.length)).toFixed(1)), color: '#3b82f6' },
    ]

    const boardMix = [
      { name: 'Independent Board', value: Number(toAverage(totalIndependentBoard, records.length).toFixed(1)), color: '#0ea5e9' },
      { name: 'Non-Independent', value: Number((100 - toAverage(totalIndependentBoard, records.length)).toFixed(1)), color: '#94a3b8' },
    ]

    const riskTierData = [
      { name: 'Strong', value: benchmarkRows.filter((row) => row.compositeScore >= 75).length, color: '#16a34a' },
      { name: 'Watchlist', value: benchmarkRows.filter((row) => row.compositeScore >= 55 && row.compositeScore < 75).length, color: '#d97706' },
      { name: 'At Risk', value: benchmarkRows.filter((row) => row.compositeScore < 55).length, color: '#dc2626' },
    ]

    return {
      totalCompanies: scopedCompanies.length,
      reportingCompanies: records.length,
      avgTRIFR: Number(toAverage(totalTRIFR, records.length).toFixed(2)),
      totalEmissions: Number((emissionsScopeTotals.scope1 + emissionsScopeTotals.scope2 + emissionsScopeTotals.scope3).toFixed(2)),
      renewableShare: Number((totalEnergy > 0 ? (renewableEnergy / totalEnergy) * 100 : 0).toFixed(1)),
      avgFemaleRep: Number(toAverage(totalFemaleRep, records.length).toFixed(1)),
      avgFemaleLeadership: Number(toAverage(totalFemaleLeadership, records.length).toFixed(1)),
      governanceAdoption: Number((policyChecks ? (policyYes / policyChecks) * 100 : 0).toFixed(1)),
      confidenceMeasured: Number((totalConfidence ? (measuredConfidence / totalConfidence) * 100 : 0).toFixed(1)),
      sectorRows: sectorRows.sort((left, right) => right.totalEmissions - left.totalEmissions),
      scopeMixData,
      workforceMix,
      boardMix,
      riskTierData,
      confidenceMix: [
        { name: 'Measured', value: measuredConfidence, color: '#0f8f88' },
        { name: 'Estimated / other', value: Math.max(0, totalConfidence - measuredConfidence), color: '#f59e0b' },
      ],
      dataQualityRows: [...benchmarkRows].sort((left, right) => right.dataIssues - left.dataIssues),
      topBenchmarkRows: [...benchmarkRows].sort((left, right) => right.compositeScore - left.compositeScore).slice(0, 10),
      benchmarkRows,
      avgReductionTarget: Number(toAverage(benchmarkRows.reduce((sum, row) => sum + row.reductionTarget, 0), benchmarkRows.length).toFixed(1)),
      avgActualReduction: Number(toAverage(benchmarkRows.reduce((sum, row) => sum + row.actualReduction, 0), benchmarkRows.length).toFixed(1)),
    }
  }, [scopedCompanies, selectedCycle])

  const qualityScope = useMemo(() => {
    const rows = (qualityData?.rows || []).filter((row) => {
      const sectorMatch = selectedSector === 'All' || row.sector === selectedSector
      const companyMatch = selectedCompany === 'All' || String(row.company_id) === selectedCompany
      return sectorMatch && companyMatch
    })
    const reportingRows = rows.filter((row) => row.submission_id)
    const average = (key) => reportingRows.length
      ? reportingRows.reduce((sum, row) => sum + Number(row[key] || 0), 0) / reportingRows.length
      : 0
    const measured = rows.reduce((sum, row) => sum + Number(row.measured_values || 0), 0)
    const estimated = rows.reduce((sum, row) => sum + Number(row.estimated_values || 0), 0)
    const confidenceTotal = rows.reduce((sum, row) => sum + Number(row.confidence_values || 0), 0)
    const severityNames = ['Critical', 'High', 'Medium', 'Low']
    return {
      rows,
      reportingCompanies: reportingRows.length,
      qualityIndex: average('quality_score'),
      completeness: average('completeness'),
      measuredConfidence: average('measured_confidence'),
      evidenceCoverage: average('evidence_coverage'),
      openFlags: rows.reduce((sum, row) => sum + Number(row.validation_flags || 0), 0),
      atRiskCompanies: rows.filter((row) => row.priority === 'At risk').length,
      confidenceMix: [
        { name: 'Measured', value: measured, color: '#0f8f88' },
        { name: 'Estimated', value: estimated, color: '#f59e0b' },
        { name: 'Other / unavailable', value: Math.max(0, confidenceTotal - measured - estimated), color: '#94a3b8' },
      ],
      severityMix: severityNames.map((name) => ({
        name,
        value: rows.reduce((sum, row) => sum + Number(row.severity_counts?.[name] || 0), 0),
        color: { Critical: '#991b1b', High: '#dc2626', Medium: '#f59e0b', Low: '#2563eb' }[name],
      })),
      issueCategories: [
        { name: 'Missing required', value: rows.reduce((sum, row) => sum + Number(row.missing_required || 0), 0) },
        { name: 'Estimated data', value: estimated },
        { name: 'Validation flags', value: rows.reduce((sum, row) => sum + Number(row.validation_flags || 0), 0) },
        { name: 'Missing evidence', value: rows.reduce((sum, row) => sum + Number(row.missing_evidence || 0), 0) },
      ],
    }
  }, [qualityData, selectedCompany, selectedSector])

  const exportAnalyticsCsv = () => {
    const columns = ['company', 'sector', 'compositeScore', 'scoreChange', 'reductionTarget', 'actualReduction', 'dataIssues']
    const rows = [columns.join(','), ...analytics.benchmarkRows.map((row) => columns.map((column) => JSON.stringify(row[column] ?? '')).join(','))]
    const url = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `esg-analytics-${selectedCycle.toLowerCase()}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="Admin Analytics" subtitle="Loading analytics from latest submissions...">
          <p>Loading data from backend.</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="Admin Analytics" subtitle="Live data unavailable">
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <ExecutivePageHeader
        eyebrow="Portfolio intelligence"
        title="ESG analytics command center"
        description="Move from portfolio signals to company-level evidence with a consistent environmental, social, governance, and benchmarking view."
        meta={[
          { label: 'Scope', value: selectedCompany !== 'All' ? 'Single company' : selectedSector !== 'All' ? selectedSector : 'Full portfolio' },
          { label: 'Reporting', value: `${analytics.reportingCompanies}/${analytics.totalCompanies}` },
          { label: 'Measured data', value: `${analytics.confidenceMeasured}%` },
        ]}
        actions={(
          <div className="analytics-scope-controls">
            <label>
              Cycle
              <select value={selectedCycle} onChange={(event) => setSelectedCycle(event.target.value)}>
                <option value="Latest">Latest submission</option>
                {cycles.map((cycle) => <option key={cycle.id} value={String(cycle.cycle_year)}>FY{cycle.cycle_year}</option>)}
              </select>
            </label>
            <label>
              Sector
              <select
                value={selectedSector}
                onChange={(event) => {
                  setSelectedSector(event.target.value)
                  setSelectedCompany('All')
                }}
              >
                {sectorOptions.map((sector) => <option key={sector} value={sector}>{sector}</option>)}
              </select>
            </label>
            <label>
              Company
              <select value={selectedCompany} onChange={(event) => setSelectedCompany(event.target.value)}>
                <option value="All">All companies</option>
                {companyOptions.map((company) => <option key={company.id} value={String(company.id)}>{company.name}</option>)}
              </select>
            </label>
            <button type="button" className="button" onClick={exportAnalyticsCsv}>Export CSV</button>
            <button type="button" className="button" onClick={() => window.print()}>Export PDF</button>
          </div>
        )}
      />

      <section className="executive-kpi-grid" aria-label="Portfolio analytics metrics">
        <KpiCard title="Reporting Coverage" value={`${analytics.reportingCompanies}/${analytics.totalCompanies}`} trendLabel="companies with submissions" />
        <KpiCard title="Portfolio Emissions" value={`${analytics.totalEmissions.toLocaleString()} tCO2e`} />
        <KpiCard title="Renewable Share" value={`${analytics.renewableShare}%`} />
        <KpiCard title="Governance Adoption" value={`${analytics.governanceAdoption}%`} />
        <KpiCard title="Reduction Target" value={`${analytics.avgReductionTarget}%`} trendLabel="portfolio average" />
        <KpiCard title="Actual Reduction" value={`${analytics.avgActualReduction}%`} trendLabel="versus prior cycle" />
      </section>

      <SectionCard title="Target versus actual" subtitle="Emissions reduction commitments compared with achieved year-on-year change">
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={analytics.benchmarkRows.slice(0, 12)}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="company" tick={{ fontSize: 11 }} angle={-18} textAnchor="end" height={75} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="reductionTarget" fill="#2563eb" name="Target %" />
              <Bar dataKey="actualReduction" fill="#0f766e" name="Actual %" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </SectionCard>

      <section className="analytics-insight-strip" aria-label="Current portfolio insight">
        <div>
          <span>Decision signal</span>
          <strong>
            {analytics.riskTierData.find((item) => item.name === 'At Risk')?.value || 0} companies currently fall in the at-risk benchmark tier
          </strong>
        </div>
        <p>
          Average workforce representation is {analytics.avgFemaleRep}% and safety performance is {analytics.avgTRIFR.toFixed(2)} TRIFR across the selected scope.
        </p>
      </section>

      {!analytics.reportingCompanies ? (
        <div className="analytics-empty-scope" role="status">
          <strong>No submitted ESG data in this scope</strong>
          <p>Select another company or return to the full portfolio to populate charts and benchmarks.</p>
        </div>
      ) : null}

      <SectionCard
        title="Admin ESG Analytics"
        subtitle="Redesigned deep analytics by environmental, social, governance, and benchmark performance lenses"
        actions={
          <div className="tab-row">
            {analyticsTabs.map((tab) => (
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
        {activeTab === 'Environmental' ? (
          <section className="two-col-grid">
            <div className="chart-wrap">
              <h4>Emissions by Sector (Scope 1/2/3)</h4>
              <ResponsiveContainer width="100%" height={310}>
                <BarChart data={analytics.sectorRows.slice(0, 10)}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="sector" tick={{ fontSize: 11 }} angle={-18} textAnchor="end" height={60} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="scope1" stackId="emissions" fill="#0f766e" name="Scope 1" />
                  <Bar dataKey="scope2" stackId="emissions" fill="#0284c7" name="Scope 2" />
                  <Bar dataKey="scope3" stackId="emissions" fill="#f97316" name="Scope 3" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-wrap">
              <h4>Portfolio Emissions Mix</h4>
              <ResponsiveContainer width="100%" height={310}>
                <PieChart>
                  <Pie data={analytics.scopeMixData} dataKey="value" nameKey="name" innerRadius={72} outerRadius={116}>
                    {analytics.scopeMixData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-wrap">
              <h4>Emissions Intensity by Sector (tCO2e / FTE)</h4>
              <ResponsiveContainer width="100%" height={290}>
                <LineChart data={analytics.sectorRows.slice(0, 10)}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="sector" tick={{ fontSize: 11 }} angle={-18} textAnchor="end" height={60} />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="avgIntensity" stroke="#1d4ed8" strokeWidth={3} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>
        ) : null}

        {activeTab === 'Social' ? (
          <section className="two-col-grid">
            <div className="chart-wrap">
              <h4>Safety Performance by Sector (Avg TRIFR)</h4>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={analytics.sectorRows.slice(0, 10)}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="sector" tick={{ fontSize: 11 }} angle={-18} textAnchor="end" height={60} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="avgTRIFR" fill="#0f766e" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-wrap">
              <h4>Portfolio Workforce Mix</h4>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={analytics.workforceMix} dataKey="value" nameKey="name" innerRadius={68} outerRadius={112}>
                    {analytics.workforceMix.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-wrap">
              <h4>Diversity Progress by Sector</h4>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={analytics.sectorRows.slice(0, 10)}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="sector" tick={{ fontSize: 11 }} angle={-18} textAnchor="end" height={60} />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="avgFemaleRep" fill="#ec4899" name="Women Workforce %" />
                  <Bar dataKey="avgFemaleLeadership" fill="#2563eb" name="Women Leadership %" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        ) : null}

        {activeTab === 'Governance' ? (
          <section className="two-col-grid">
            <div className="chart-wrap">
              <h4>Governance Adoption by Sector</h4>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={analytics.sectorRows.slice(0, 10)}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="sector" tick={{ fontSize: 11 }} angle={-18} textAnchor="end" height={60} />
                  <YAxis domain={[0, 100]} />
                  <Tooltip />
                  <Bar dataKey="governanceAdoption" fill="#1d4ed8" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-wrap">
              <h4>Board Composition (Portfolio Average)</h4>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={analytics.boardMix} dataKey="value" nameKey="name" innerRadius={68} outerRadius={112}>
                    {analytics.boardMix.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </section>
        ) : null}

        {activeTab === 'Data Quality' ? (
          <section className="space-y-4">
            {qualityLoading ? <p className="action-message">Calculating cycle-specific quality indicators...</p> : null}
            {qualityError ? <p className="action-message" role="alert">{qualityError}</p> : null}

            <section className="executive-kpi-grid" aria-label="Data quality indicators">
              <KpiCard title="Quality Index" value={`${qualityScope.qualityIndex.toFixed(1)}/100`} trendLabel="weighted quality score" icon="analytics" />
              <KpiCard title="Completeness" value={`${qualityScope.completeness.toFixed(1)}%`} trendLabel="required metrics reported" icon="submissions" />
              <KpiCard title="Measured Confidence" value={`${qualityScope.measuredConfidence.toFixed(1)}%`} trendLabel="confidence-tagged values" icon="review" />
              <KpiCard title="Evidence Coverage" value={`${qualityScope.evidenceCoverage.toFixed(1)}%`} trendLabel="required evidence attached" icon="reports" />
              <KpiCard title="Open Validation Flags" value={qualityScope.openFlags.toLocaleString()} trendLabel="selected reporting scope" icon="risks" tone="amber" />
              <KpiCard title="At-risk Companies" value={qualityScope.atRiskCompanies.toLocaleString()} trendLabel={`${qualityScope.reportingCompanies}/${qualityScope.rows.length} reporting`} icon="anomaly" tone="rose" />
            </section>

            <div className="three-col-grid">
              <div className="chart-wrap">
                <h4>Confidence classification</h4>
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie data={qualityScope.confidenceMix} dataKey="value" nameKey="name" innerRadius={58} outerRadius={96}>
                      {qualityScope.confidenceMix.map((entry) => (
                        <Cell key={entry.name} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div className="chart-wrap">
                <h4>Validation severity</h4>
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie data={qualityScope.severityMix} dataKey="value" nameKey="name" innerRadius={58} outerRadius={96}>
                      {qualityScope.severityMix.map((entry) => (
                        <Cell key={entry.name} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div className="chart-wrap">
                <h4>Issue composition</h4>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={qualityScope.issueCategories} layout="vertical" margin={{ left: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis type="number" allowDecimals={false} />
                    <YAxis dataKey="name" type="category" width={105} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="value" fill="#2563eb" name="Issues" radius={[0, 8, 8, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="analytics-insight-strip">
              <div>
                <span>Remediation priority</span>
                <strong>{qualityScope.atRiskCompanies} companies require data-quality intervention</strong>
              </div>
              <p>The quality index weights completeness 40%, measured confidence 30%, validation health 20%, and required evidence coverage 10%.</p>
            </div>

            <DataTable
              columns={[
                { key: 'company', label: 'Company', sortable: true },
                { key: 'sector', label: 'Sector', sortable: true },
                { key: 'quality_score', label: 'Quality index', sortable: true, render: (row) => `${row.quality_score.toFixed(1)}/100` },
                { key: 'completeness', label: 'Complete', sortable: true, render: (row) => `${row.completeness.toFixed(1)}%` },
                { key: 'measured_confidence', label: 'Measured', sortable: true, render: (row) => `${row.measured_confidence.toFixed(1)}%` },
                { key: 'evidence_coverage', label: 'Evidence', sortable: true, render: (row) => `${row.evidence_coverage.toFixed(1)}%` },
                { key: 'validation_flags', label: 'Flags', sortable: true },
                { key: 'priority', label: 'Priority', sortable: true, render: (row) => <span className={`quality-priority quality-priority-${row.priority.toLowerCase().replace(/\s+/g, '-')}`}>{row.priority}</span> },
                { key: 'top_issue', label: 'Primary issue' },
              ]}
              rows={qualityScope.rows}
              pageSize={10}
              emptyMessage="No company data-quality records are available."
            />
          </section>
        ) : null}

        {activeTab === 'Benchmarking' ? (
          <section className="space-y-4">
            <div className="two-col-grid">
              <div className="chart-wrap">
                <h4>Top ESG Composite Scores</h4>
                <ResponsiveContainer width="100%" height={320}>
                  <BarChart data={analytics.topBenchmarkRows}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="company" tick={{ fontSize: 11 }} angle={-18} textAnchor="end" height={70} />
                    <YAxis domain={[0, 100]} />
                    <Tooltip />
                    <Bar dataKey="compositeScore" fill="#0f766e" radius={[8, 8, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="chart-wrap">
                <h4>Portfolio Risk Tier Distribution</h4>
                <ResponsiveContainer width="100%" height={320}>
                  <PieChart>
                    <Pie data={analytics.riskTierData} dataKey="value" nameKey="name" innerRadius={72} outerRadius={118}>
                      {analytics.riskTierData.map((entry) => (
                        <Cell key={entry.name} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            <DataTable
              columns={[
                { key: 'company', label: 'Company', sortable: true },
                { key: 'sector', label: 'Sector', sortable: true },
                { key: 'compositeScore', label: 'Composite', sortable: true },
                { key: 'scoreChange', label: 'YoY change', sortable: true },
                { key: 'environmentScore', label: 'Env Score', sortable: true },
                { key: 'socialScore', label: 'Social Score', sortable: true },
                { key: 'governanceScore', label: 'Gov Score', sortable: true },
                { key: 'renewableShare', label: 'Renewable %', sortable: true },
                { key: 'emissionsIntensity', label: 'tCO2e/FTE', sortable: true },
                { key: 'dataIssues', label: 'Data issues', sortable: true },
              ]}
              rows={analytics.benchmarkRows}
              pageSize={10}
              emptyMessage="No benchmark data available."
            />
          </section>
        ) : null}
      </SectionCard>

    </div>
  )
}
