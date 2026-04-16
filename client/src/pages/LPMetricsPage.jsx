import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import SectionCard from '../components/SectionCard'
import { Button } from '../components/ui'
import { API_BASE_URL } from '../lib/api'
const TAB_CATEGORIES = ['Environmental', 'Social', 'Governance', 'Asset Classes', 'Benchmarks']

export default function LPMetricsPage() {
  const { user } = useOutletContext()
  const [activeTab, setActiveTab] = useState('Environmental')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchMetricsData = async () => {
      try {
        setLoading(true)
        const response = await fetch(`${API_BASE_URL}/lp/metrics`, {
          headers: {
            'X-User-Role': user?.role || 'investor',
            'X-User-Email': user?.email || '',
            'Content-Type': 'application/json',
          },
        })

        if (!response.ok) {
          throw new Error(`Failed to fetch metrics data: ${response.status}`)
        }

        const metricsData = await response.json()
        setData(metricsData)
        setError(null)
      } catch (err) {
        console.error('Error fetching metrics:', err)
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchMetricsData()
  }, [user])

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="ESG Metrics" subtitle="Loading data...">
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="ESG Metrics" subtitle="Error loading data">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
            <p className="ui-text-strong">Error: {error}</p>
            <p className="text-sm mt-2">Make sure the backend API is reachable.</p>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="page-grid">
        <SectionCard title="ESG Metrics" subtitle="No data available">
          <p className="text-gray-600">Unable to load metrics data.</p>
        </SectionCard>
      </div>
    )
  }

  const environmental = data.environmental
  const social = data.social
  const governance = data.governance
  const assetClassBreakdown = data.asset_class_breakdown
  const benchmarkComparisons = data.benchmark_comparisons

  const renderEnvironmental = () => (
    <div className="space-y-6">
      <SectionCard title="Greenhouse Gas Emissions" subtitle="Scope 1, 2, and 3 Trends">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          {[
            { title: 'Scope 1 Emissions', data: environmental.scope_1_emissions, color: '#ef4444' },
            { title: 'Scope 2 Emissions', data: environmental.scope_2_emissions, color: '#0ea5e9' },
            { title: 'Scope 3 Emissions', data: environmental.scope_3_emissions, color: '#f59e0b' },
          ].map((scope) => (
            <div key={scope.title}>
              <p className="text-sm ui-text-strong text-gray-700 mb-3">{scope.title}</p>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={scope.data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" style={{ fontSize: '12px' }} />
                  <YAxis style={{ fontSize: '12px' }} />
                  <Tooltip formatter={(value) => `${value.toLocaleString()} tCO2e`} />
                  <Line type="monotone" dataKey="value" stroke={scope.color} strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Energy Consumption" subtitle="Total and Renewable Energy">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[
            { title: 'Total Energy Consumption (MWh)', data: environmental.energy_total },
            { title: 'Renewable Energy %', data: environmental.energy_renewable },
          ].map((energy) => (
            <div key={energy.title}>
              <p className="text-sm ui-text-strong text-gray-700 mb-3">{energy.title}</p>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={energy.data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" style={{ fontSize: '12px' }} />
                  <YAxis style={{ fontSize: '12px' }} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#0ea5e9" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Water & Waste Management" subtitle="Usage, Recycling, and Diversion Rates">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div>
            <p className="text-sm ui-text-strong text-gray-700 mb-3">Water Usage & Recycling (ML)</p>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={environmental.water_usage}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period" style={{ fontSize: '12px' }} />
                <YAxis style={{ fontSize: '12px' }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="value" fill="#0ea5e9" name="Total Usage" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div>
            <p className="text-sm ui-text-strong text-gray-700 mb-3">Waste Generated & Diverted (tonnes)</p>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={environmental.waste_generated}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="period" style={{ fontSize: '12px' }} />
                <YAxis style={{ fontSize: '12px' }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="value" stroke="#10b981" strokeWidth={2} name="Generated" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </SectionCard>
    </div>
  )

  const renderSocial = () => (
    <div className="space-y-6">
      <SectionCard title="Health & Safety" subtitle="TRIFR and Fatalities Trends">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[
            { title: 'TRIFR (Total Recordable Incident Frequency Rate)', data: social.trifr },
            { title: 'Fatalities', data: social.fatalities },
          ].map((metric) => (
            <div key={metric.title}>
              <p className="text-sm ui-text-strong text-gray-700 mb-3">{metric.title}</p>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={metric.data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" style={{ fontSize: '12px' }} />
                  <YAxis style={{ fontSize: '12px' }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke="#ef4444" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Workforce Metrics" subtitle="Employment, Turnover, and Diversity">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {[
            { title: 'Total Employees (FTE)', data: social.total_employees, color: '#0ea5e9' },
            { title: 'Female Workforce %', data: social.female_workforce_percent, color: '#ec4899' },
            { title: 'Female Leadership %', data: social.female_leadership_percent, color: '#a855f7' },
          ].map((metric) => (
            <div key={metric.title}>
              <p className="text-sm ui-text-strong text-gray-700 mb-3">{metric.title}</p>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={metric.data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" style={{ fontSize: '12px' }} />
                  <YAxis style={{ fontSize: '12px' }} />
                  <Tooltip />
                  <Bar dataKey="value" fill={metric.color} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Community Investment" subtitle="Annual Spend Trends">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={social.community_investment}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" />
            <YAxis />
            <Tooltip formatter={(value) => `$${(value / 1000000).toFixed(1)}M`} />
            <Line type="monotone" dataKey="value" stroke="#10b981" strokeWidth={2} dot={{ r: 5 }} name="Investment" />
          </LineChart>
        </ResponsiveContainer>
      </SectionCard>
    </div>
  )

  const renderGovernance = () => (
    <div className="space-y-6">
      <SectionCard title="Policy Compliance" subtitle="Adoption Rates Across Portfolio">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: 'ESG Policy', value: governance.esg_policy_compliance },
            { label: 'WHS Policy', value: governance.whs_policy_compliance },
            { label: 'Cybersecurity', value: governance.cybersecurity_policy_compliance },
            { label: 'Anti-Bribery', value: governance.antibribery_policy_compliance },
          ].map((item) => (
            <div key={item.label} className="bg-gradient-to-br from-indigo-50 to-indigo-100 p-4 rounded-lg">
              <p className="text-xs text-gray-600">{item.label}</p>
              <p className="ui-text-display text-indigo-900 mt-2">{item.value.toFixed(1)}%</p>
              <div className="mt-3 bg-gray-200 rounded-full h-2">
                <div className="bg-indigo-500 h-2 rounded-full" style={{ width: `${item.value}%` }} />
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Board & Oversight" subtitle="Governance Structure">
        <div className="bg-blue-50 p-6 rounded-lg">
          <p className="text-sm text-gray-600 mb-2">Board-Level ESG Oversight</p>
          <p className="ui-text-display text-blue-900">{governance.board_esg_oversight.toFixed(1)}%</p>
          <p className="text-xs text-gray-500 mt-2">of portfolio companies with dedicated ESG board oversight</p>
        </div>
      </SectionCard>

      <SectionCard title="Cyber Incidents" subtitle="Trend Over Time">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={governance.cyber_incidents}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="period" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="value" fill="#ef4444" name="Incidents" />
          </BarChart>
        </ResponsiveContainer>
      </SectionCard>
    </div>
  )

  const renderAssetClasses = () => (
    <SectionCard title="Asset Class Breakdown" subtitle="Performance Metrics by Class">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-100 border-b">
            <tr>
              <th className="text-left p-3 ui-text-strong">Asset Class</th>
              <th className="text-right p-3 ui-text-strong">Companies</th>
              <th className="text-right p-3 ui-text-strong">Avg ESG Score</th>
              <th className="text-right p-3 ui-text-strong">Avg Emissions Intensity</th>
              <th className="text-right p-3 ui-text-strong">Avg Female Representation</th>
            </tr>
          </thead>
          <tbody>
            {assetClassBreakdown.map((row, idx) => (
              <tr key={idx} className="border-b hover:bg-gray-50">
                <td className="p-3 font-medium">{row.asset_class}</td>
                <td className="p-3 text-right">{row.company_count}</td>
                <td className="p-3 text-right">{row.avg_esg_score.toFixed(1)}</td>
                <td className="p-3 text-right">{row.avg_emission_intensity.toFixed(1)}</td>
                <td className="p-3 text-right">{row.avg_female_representation.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  )

  const renderBenchmarks = () => (
    <SectionCard title="Benchmark Comparison" subtitle="Portfolio vs Industry Standards">
      <div className="space-y-4">
        {benchmarkComparisons.map((benchmark, idx) => {
          const isAbove = benchmark.status === 'above'
          const statusColor = isAbove ? 'text-green-600' : benchmark.status === 'at' ? 'text-blue-600' : 'text-red-600'
          const statusIcon = isAbove ? '↑' : benchmark.status === 'at' ? '→' : '↓'
          const bgColor = isAbove ? 'bg-green-50' : benchmark.status === 'at' ? 'bg-blue-50' : 'bg-red-50'

          return (
            <div key={idx} className={`${bgColor} p-4 rounded-lg border-l-4 ${isAbove ? 'border-green-500' : benchmark.status === 'at' ? 'border-blue-500' : 'border-red-500'}`}>
              <div className="flex justify-between items-start">
                <div>
                  <p className="ui-text-strong text-gray-800">{benchmark.metric_name}</p>
                  <p className="text-xs text-gray-600 mt-1">{benchmark.industry}</p>
                </div>
                <div className="text-right">
                  <p className={`ui-text-display ${statusColor}`}>
                    {statusIcon} {benchmark.status.toUpperCase()}
                  </p>
                  <p className="text-xs text-gray-600 mt-1">Portfolio vs Benchmark</p>
                </div>
              </div>
              <div className="mt-3 flex justify-between text-sm">
                <div>
                  <p className="text-gray-600">Portfolio</p>
                  <p className="ui-text-strong text-gray-800">{benchmark.portfolio_value.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-gray-600">Benchmark</p>
                  <p className="ui-text-strong text-gray-800">{benchmark.benchmark_value.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-gray-600">Variance</p>
                  <p className={`ui-text-strong ${isAbove ? 'text-green-600' : 'text-red-600'}`}>
                    {(benchmark.portfolio_value - benchmark.benchmark_value).toFixed(2)}
                  </p>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </SectionCard>
  )

  const renderContent = () => {
    switch (activeTab) {
      case 'Environmental':
        return renderEnvironmental()
      case 'Social':
        return renderSocial()
      case 'Governance':
        return renderGovernance()
      case 'Asset Classes':
        return renderAssetClasses()
      case 'Benchmarks':
        return renderBenchmarks()
      default:
        return renderEnvironmental()
    }
  }

  return (
    <div className="page-grid">
      <div className="flex flex-wrap gap-2 mb-6">
        {TAB_CATEGORIES.map((tab) => (
          <Button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeTab === tab ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-800 hover:bg-gray-300'
            }`}
          >
            {tab}
          </Button>
        ))}
      </div>

      {renderContent()}

      {/* Export Section */}
      <SectionCard title="Export Data" subtitle="Download detailed metrics in Excel format">
        <div className="flex gap-3">
          <Button className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium">
            Export {activeTab}
          </Button>
          <Button className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
            Export All Metrics
          </Button>
        </div>
      </SectionCard>
    </div>
  )
}


