import { useState, useMemo } from 'react'
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
import SectionCard from '../components/SectionCard'
import useDashboardData, { getLatestSubmission, parseSubmissionPayload } from '../hooks/useDashboardData'

const analyticsTabs = ['Environmental', 'Social', 'Governance']

export default function AnalyticsPage() {
  const { user } = useOutletContext()
  const { companies } = useDashboardData(user)
  const [activeTab, setActiveTab] = useState(analyticsTabs[0])

  const { emissionsData, energyData, trifrData, diversityData, governanceData } = useMemo(() => {
    let energy = 0, renewable = 0, female = 0, count = 0
    let esgYes = 0, whsYes = 0, cyberYes = 0
    
    companies.forEach(c => {
      const payload = parseSubmissionPayload(getLatestSubmission(c))
      if (payload) {
        energy += payload.total_energy_consumption || 0
        renewable += payload.renewable_energy_consumption || 0
        female += payload.female_representation_percent || 0
        if (payload.esg_policy_in_place === 'Yes') esgYes++
        if (payload.whs_policy_in_place === 'Yes') whsYes++
        if (payload.cybersecurity_policy_in_place === 'Yes') cyberYes++
        count++
      }
    })

    const validCount = count || 1

    return {
      emissionsData: companies.map(c => {
        const p = parseSubmissionPayload(getLatestSubmission(c))
        return { name: c.name, scope1: p?.scope_1_emissions || 0, scope2: p?.scope_2_location_based || 0, scope3: p?.scope_3_emissions || 0 }
      }),
      energyData: [{ source: 'Renewable', value: renewable }, { source: 'Non-Renewable', value: Math.max(0, energy - renewable) }],
      trifrData: companies.map(c => {
         const p = parseSubmissionPayload(getLatestSubmission(c))
         return { name: c.name, trifr: p?.trifr || 0 }
      }),
      diversityData: [{ name: 'Female', value: Math.round(female / validCount), color: '#ec4899' }, { name: 'Male', value: 100 - Math.round(female / validCount), color: '#3b82f6' }].filter(d => d.value > 0),
      governanceData: [{ policy: 'ESG Policy', adoption: Math.round((esgYes / validCount) * 100) }, { policy: 'WHS Policy', adoption: Math.round((whsYes / validCount) * 100) }, { policy: 'Cyber Policy', adoption: Math.round((cyberYes / validCount) * 100) }]
    }
  }, [companies])

  return (
    <div className="page-grid">
      <SectionCard
        title="ESG Analytics"
        subtitle="Environmental, Social, Governance, and Benchmarking insights"
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
        {activeTab === 'Environmental' && (
          <div className="two-col-grid">
            <div className="chart-wrap">
              <h4>Emissions Trend</h4>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={emissionsData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} angle={-15} textAnchor="end" height={50} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="scope1" stackId="a" fill="#0ea5e9" name="Scope 1" />
                  <Bar dataKey="scope2" stackId="a" fill="#14b8a6" name="Scope 2" />
                  <Bar dataKey="scope3" stackId="a" fill="#f97316" name="Scope 3" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-wrap">
              <h4>Energy Mix</h4>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={energyData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="source" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="value" fill="#2563eb" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {activeTab === 'Social' && (
          <div className="two-col-grid">
            <div className="chart-wrap">
              <h4>Portfolio TRIFR</h4>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={trifrData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} angle={-15} textAnchor="end" height={50} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="trifr" fill="#0f766e" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="chart-wrap">
              <h4>Diversity Mix</h4>
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie data={diversityData} dataKey="value" nameKey="name" innerRadius={60} outerRadius={98}>
                    {diversityData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
              <ul className="mini-legend">
                {diversityData.map((entry) => (
                  <li key={entry.name}>
                    <span style={{ background: entry.color }} /> {entry.name}: {entry.value}%
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {activeTab === 'Governance' && (
          <div className="chart-wrap">
            <h4>Governance Policy Adoption</h4>
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={governanceData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="policy" />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Bar dataKey="adoption" fill="#8b5cf6" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </SectionCard>
    </div>
  )
}
