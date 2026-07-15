import { useCallback, useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import DataTable from '../components/DataTable'
import ExecutivePageHeader from '../components/ExecutivePageHeader'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import { API_BASE_URL } from '../lib/api'

const emptyForm = {
  topic: '',
  pillar: 'Environmental',
  impact_score: 3,
  financial_score: 3,
  stakeholder_score: 3,
  rationale: '',
  owner: '',
  status: 'assessed',
}

const defaultScenario = {
  scenario_name: 'Orderly transition',
  temperature_pathway: 1.5,
  carbon_price: 100,
  energy_cost_change_percent: 20,
  physical_risk_multiplier: 1.2,
  horizon_year: 2030,
}

export default function StrategyPage() {
  const { user } = useOutletContext()
  const [data, setData] = useState({ topics: [], priority_topics: 0, action_required: 0, average_priority: 0 })
  const [form, setForm] = useState(emptyForm)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [scenarioInputs, setScenarioInputs] = useState(defaultScenario)
  const [scenarioResult, setScenarioResult] = useState(null)
  const [scenarioLoading, setScenarioLoading] = useState(false)
  const isManager = String(user?.role || '').toLowerCase() === 'manager'

  const headers = useMemo(() => ({
    'Content-Type': 'application/json',
    'x-user-role': user?.role || '',
    'x-user-email': user?.email || '',
  }), [user?.email, user?.role])

  const loadTopics = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/materiality/topics`, { headers })
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Unable to load materiality topics.')
      setData(await response.json())
    } catch (error) {
      setMessage(error.message)
    } finally {
      setLoading(false)
    }
  }, [headers])

  useEffect(() => { loadTopics() }, [loadTopics])

  const createTopic = async (event) => {
    event.preventDefault()
    setMessage('')
    const response = await fetch(`${API_BASE_URL}/materiality/topics`, {
      method: 'POST', headers, body: JSON.stringify(form),
    })
    if (!response.ok) {
      setMessage((await response.json().catch(() => ({}))).detail || 'Unable to save topic.')
      return
    }
    setForm(emptyForm)
    setMessage('Materiality topic added.')
    await loadTopics()
  }

  const runScenario = async (event) => {
    event.preventDefault()
    setScenarioLoading(true)
    setMessage('')
    try {
      const response = await fetch(`${API_BASE_URL}/analytics/scenario-analysis`, {
        method: 'POST', headers, body: JSON.stringify(scenarioInputs),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Unable to run scenario.')
      setScenarioResult(await response.json())
    } catch (error) {
      setMessage(error.message)
    } finally {
      setScenarioLoading(false)
    }
  }

  return (
    <div className="page-grid">
      <ExecutivePageHeader
        eyebrow="Strategy & risk"
        title="ESG Strategy Lab"
        description="Prioritise double-materiality topics and stress-test portfolio exposure under transparent climate scenarios."
      />

      <SectionCard title="Climate scenario analysis" subtitle="Adjust transition and physical-risk assumptions; results use current reported portfolio data">
        <form className="scenario-controls" onSubmit={runScenario}>
          <label><span>Scenario</span><input value={scenarioInputs.scenario_name} onChange={(event) => setScenarioInputs({ ...scenarioInputs, scenario_name: event.target.value })} /></label>
          <label><span>Temperature pathway</span><input type="number" min="1" max="4.5" step="0.1" value={scenarioInputs.temperature_pathway} onChange={(event) => setScenarioInputs({ ...scenarioInputs, temperature_pathway: Number(event.target.value) })} /></label>
          <label><span>Carbon price / tCO2e</span><input type="number" min="0" max="500" value={scenarioInputs.carbon_price} onChange={(event) => setScenarioInputs({ ...scenarioInputs, carbon_price: Number(event.target.value) })} /></label>
          <label><span>Energy cost change %</span><input type="number" min="-50" max="300" value={scenarioInputs.energy_cost_change_percent} onChange={(event) => setScenarioInputs({ ...scenarioInputs, energy_cost_change_percent: Number(event.target.value) })} /></label>
          <label><span>Physical-risk multiplier</span><input type="number" min="0" max="5" step="0.1" value={scenarioInputs.physical_risk_multiplier} onChange={(event) => setScenarioInputs({ ...scenarioInputs, physical_risk_multiplier: Number(event.target.value) })} /></label>
          <label><span>Horizon</span><input type="number" min="2026" max="2100" value={scenarioInputs.horizon_year} onChange={(event) => setScenarioInputs({ ...scenarioInputs, horizon_year: Number(event.target.value) })} /></label>
          <button className="button primary" disabled={scenarioLoading} type="submit">{scenarioLoading ? 'Running…' : 'Run scenario'}</button>
        </form>

        {scenarioResult ? (
          <div className="space-y-4">
            <section className="executive-kpi-grid">
              <KpiCard title="Annual Exposure" value={`$${Math.round(scenarioResult.annual_exposure).toLocaleString()}`} trendLabel="modelled cost proxy" icon="risks" tone="amber" />
              <KpiCard title="Cumulative Exposure" value={`$${Math.round(scenarioResult.cumulative_exposure).toLocaleString()}`} trendLabel={`through ${scenarioResult.scenario.horizon_year}`} icon="analytics" />
              <KpiCard title="Average Risk" value={`${scenarioResult.average_risk_score}/100`} trendLabel="portfolio screening score" icon="overview" />
              <KpiCard title="High Risk" value={scenarioResult.high_risk_companies} trendLabel={`${scenarioResult.modelled_companies} companies modelled`} icon="anomaly" tone="rose" />
            </section>
            <div className="chart-wrap">
              <h4>Largest annual exposure drivers</h4>
              <ResponsiveContainer width="100%" height={340}>
                <BarChart data={scenarioResult.rows.slice(0, 10)}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="company" tick={{ fontSize: 11 }} angle={-18} textAnchor="end" height={70} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="transition_cost" stackId="cost" fill="#0f766e" name="Transition" />
                  <Bar dataKey="energy_cost_impact" stackId="cost" fill="#2563eb" name="Energy" />
                  <Bar dataKey="physical_risk_cost" stackId="cost" fill="#f97316" name="Physical" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <DataTable
              columns={[
                { key: 'company', label: 'Company', sortable: true },
                { key: 'sector', label: 'Sector', sortable: true },
                { key: 'annual_exposure', label: 'Annual exposure', sortable: true, render: (row) => `$${Math.round(row.annual_exposure).toLocaleString()}` },
                { key: 'cumulative_exposure', label: 'Cumulative', sortable: true, render: (row) => `$${Math.round(row.cumulative_exposure).toLocaleString()}` },
                { key: 'risk_score', label: 'Risk score', sortable: true },
                { key: 'risk_tier', label: 'Risk tier', sortable: true },
              ]}
              rows={scenarioResult.rows}
              pageSize={8}
            />
            <ul className="scenario-methodology">{scenarioResult.methodology.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        ) : <p className="review-history-empty">Run a scenario to calculate company and portfolio exposure.</p>}
      </SectionCard>

      <section className="executive-kpi-grid">
        <KpiCard title="Topics Assessed" value={data.topics.length} trendLabel="materiality universe" icon="analytics" />
        <KpiCard title="Material Priorities" value={data.priority_topics} trendLabel="high impact and financial relevance" icon="risks" tone="rose" />
        <KpiCard title="Action Required" value={data.action_required} trendLabel="management attention" icon="actions" tone="amber" />
        <KpiCard title="Average Priority" value={`${Number(data.average_priority || 0).toFixed(2)}/5`} trendLabel="weighted double-materiality score" icon="overview" />
      </section>

      <SectionCard title="Materiality matrix" subtitle="Bubble size reflects stakeholder importance">
        {loading ? <p className="action-message">Loading assessment...</p> : null}
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height={390}>
            <ScatterChart margin={{ top: 24, right: 30, bottom: 30, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" dataKey="financial_score" name="Financial relevance" domain={[1, 5]} label={{ value: 'Financial relevance', position: 'bottom' }} />
              <YAxis type="number" dataKey="impact_score" name="Impact significance" domain={[1, 5]} label={{ value: 'Impact significance', angle: -90, position: 'insideLeft' }} />
              <ZAxis type="number" dataKey="stakeholder_score" range={[100, 700]} />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={(value, name) => [value, name]} />
              <Scatter name="Material topics" data={data.topics} fill="#0f766e" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </SectionCard>

      {isManager ? (
        <SectionCard title="Assess a topic" subtitle="Scores use a controlled 1–5 scale">
          <form className="target-form materiality-form" onSubmit={createTopic}>
            <label><span>Topic</span><input required value={form.topic} onChange={(event) => setForm({ ...form, topic: event.target.value })} /></label>
            <label><span>Pillar</span><select value={form.pillar} onChange={(event) => setForm({ ...form, pillar: event.target.value })}><option>Environmental</option><option>Social</option><option>Governance</option></select></label>
            <label><span>Impact score</span><input type="number" min="1" max="5" step="0.1" value={form.impact_score} onChange={(event) => setForm({ ...form, impact_score: Number(event.target.value) })} /></label>
            <label><span>Financial score</span><input type="number" min="1" max="5" step="0.1" value={form.financial_score} onChange={(event) => setForm({ ...form, financial_score: Number(event.target.value) })} /></label>
            <label><span>Stakeholder score</span><input type="number" min="1" max="5" step="0.1" value={form.stakeholder_score} onChange={(event) => setForm({ ...form, stakeholder_score: Number(event.target.value) })} /></label>
            <label><span>Owner</span><input required value={form.owner} onChange={(event) => setForm({ ...form, owner: event.target.value })} /></label>
            <label><span>Status</span><select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}><option value="assessed">Assessed</option><option value="monitoring">Monitoring</option><option value="action required">Action required</option></select></label>
            <label className="target-form-notes"><span>Rationale</span><textarea rows="2" value={form.rationale} onChange={(event) => setForm({ ...form, rationale: event.target.value })} /></label>
            <button className="button primary" type="submit">Add topic</button>
          </form>
          {message ? <p className="action-message">{message}</p> : null}
        </SectionCard>
      ) : null}

      <SectionCard title="Material topic register" subtitle="Decision-ready ownership and prioritisation">
        <DataTable
          columns={[
            { key: 'topic', label: 'Topic', sortable: true },
            { key: 'pillar', label: 'Pillar', sortable: true },
            { key: 'impact_score', label: 'Impact', sortable: true },
            { key: 'financial_score', label: 'Financial', sortable: true },
            { key: 'stakeholder_score', label: 'Stakeholder', sortable: true },
            { key: 'priority_score', label: 'Priority', sortable: true },
            { key: 'quadrant', label: 'Classification', sortable: true },
            { key: 'owner', label: 'Owner', sortable: true },
            { key: 'status', label: 'Status', sortable: true },
          ]}
          rows={data.topics}
          pageSize={10}
          emptyMessage="No materiality topics have been assessed yet."
        />
      </SectionCard>
    </div>
  )
}
