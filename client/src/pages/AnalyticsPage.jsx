import { useMemo, useState } from 'react'
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
import AdminAnalyticsSections from '../components/analytics/AdminAnalyticsSections'
import useDashboardData, { calculateESGPillarScores, getLatestSubmission, parseSubmissionPayload } from '../hooks/useDashboardData'

const analyticsTabs = ['Environmental', 'Social', 'Governance', 'Benchmarking']

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
  const { companies, loading, error } = useDashboardData(user)
  const [activeTab, setActiveTab] = useState(analyticsTabs[0])
  const [selectedSector, setSelectedSector] = useState('All')
  const [selectedCompany, setSelectedCompany] = useState('All')

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
        const latestSubmission = getLatestSubmission(company)
        const payload = parseSubmissionPayload(latestSubmission)
        if (!payload || typeof payload !== 'object') return null
        return {
          companyId: company.id,
          companyName: company.name,
          sector: company.sector || 'Unassigned',
          payload,
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
      topBenchmarkRows: [...benchmarkRows].sort((left, right) => right.compositeScore - left.compositeScore).slice(0, 10),
      benchmarkRows,
    }
  }, [scopedCompanies])

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
          </div>
        )}
      />

      <section className="executive-kpi-grid" aria-label="Portfolio analytics metrics">
        <KpiCard title="Reporting Coverage" value={`${analytics.reportingCompanies}/${analytics.totalCompanies}`} trendLabel="companies with submissions" />
        <KpiCard title="Portfolio Emissions" value={`${analytics.totalEmissions.toLocaleString()} tCO2e`} />
        <KpiCard title="Renewable Share" value={`${analytics.renewableShare}%`} />
        <KpiCard title="Governance Adoption" value={`${analytics.governanceAdoption}%`} />
      </section>

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
                { key: 'environmentScore', label: 'Env Score', sortable: true },
                { key: 'socialScore', label: 'Social Score', sortable: true },
                { key: 'governanceScore', label: 'Gov Score', sortable: true },
                { key: 'renewableShare', label: 'Renewable %', sortable: true },
                { key: 'emissionsIntensity', label: 'tCO2e/FTE', sortable: true },
              ]}
              rows={analytics.benchmarkRows}
              pageSize={10}
              emptyMessage="No benchmark data available."
            />
          </section>
        ) : null}
      </SectionCard>

      <AdminAnalyticsSections user={user} />
    </div>
  )
}
