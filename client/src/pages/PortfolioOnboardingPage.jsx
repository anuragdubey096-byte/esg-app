import { useCallback, useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import ExecutivePageHeader from '../components/ExecutivePageHeader'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import { API_BASE_URL } from '../lib/api'

const emptyCompany = {
  code: '', name: '', sector: '', geography: '', asset_class: '',
  contact_name: '', contact_email: '', temporary_password: '', current_status: 'onboarding',
}
const emptyPortfolio = { code: '', name: '', base_currency: 'USD', description: '' }
const emptyFund = { portfolio_id: '', code: '', name: '', base_currency: 'USD', vintage_year: '' }
const emptyHolding = () => ({
  fund_id: '', company_id: '', external_id: '', ownership_percent: '',
  invested_amount_base: '', nav_value_base: '', currency: 'USD',
  effective_from: new Date().toISOString().slice(0, 10), status: 'active',
})

const holdingColumns = [
  { key: 'external_id', label: 'Holding ID', sortable: true },
  { key: 'portfolio_name', label: 'Portfolio', sortable: true },
  { key: 'fund_name', label: 'Fund', sortable: true },
  { key: 'company_name', label: 'Company', sortable: true },
  { key: 'ownership_percent', label: 'Ownership', sortable: true, render: (row) => `${Number(row.ownership_percent).toFixed(2)}%` },
  { key: 'nav_value_base', label: 'Current NAV', sortable: true, render: (row) => `${row.currency} ${Number(row.nav_value_base || row.invested_amount_base).toLocaleString()}` },
  { key: 'weight_percent', label: 'Weight', sortable: true, render: (row) => `${Number(row.weight_percent).toFixed(2)}%` },
]

const companyColumns = [
  { key: 'code', label: 'Code', sortable: true },
  { key: 'name', label: 'Company', sortable: true },
  { key: 'sector', label: 'Sector', sortable: true },
  { key: 'asset_class', label: 'Asset class', sortable: true },
  { key: 'geography', label: 'Geography', sortable: true },
  { key: 'current_status', label: 'Status', sortable: true },
]

export default function PortfolioOnboardingPage() {
  const { user } = useOutletContext()
  const headers = useMemo(() => ({
    'Content-Type': 'application/json',
    'x-user-role': user?.role || '',
    'x-user-email': user?.email || '',
  }), [user?.email, user?.role])
  const [structure, setStructure] = useState({ portfolios: [], holdings: [], summary: {} })
  const [companies, setCompanies] = useState([])
  const [companyForm, setCompanyForm] = useState(emptyCompany)
  const [portfolioForm, setPortfolioForm] = useState(emptyPortfolio)
  const [fundForm, setFundForm] = useState(emptyFund)
  const [holdingForm, setHoldingForm] = useState(emptyHolding)
  const [credentials, setCredentials] = useState(null)
  const [portfolioCsv, setPortfolioCsv] = useState(null)
  const [importPreview, setImportPreview] = useState(null)
  const [importing, setImporting] = useState(false)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [structureResponse, dashboardResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/portfolio-structure`, { headers }),
        fetch(`${API_BASE_URL}/dashboard/manager`, { headers }),
      ])
      if (!structureResponse.ok || !dashboardResponse.ok) throw new Error('Unable to load portfolio setup data.')
      setStructure(await structureResponse.json())
      setCompanies((await dashboardResponse.json()).companies || [])
    } catch (error) {
      setMessage(error.message)
    } finally {
      setLoading(false)
    }
  }, [headers])

  useEffect(() => { loadData() }, [loadData])

  const postItem = async (path, payload) => {
    const normalized = Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== '' && value !== undefined))
    const response = await fetch(`${API_BASE_URL}/${path}`, { method: 'POST', headers, body: JSON.stringify(normalized) })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || `Unable to save ${path}.`)
    return body
  }

  const submitCompany = async (event) => {
    event.preventDefault(); setMessage(''); setCredentials(null)
    try {
      const result = await postItem('companies', companyForm)
      setCredentials({ email: result.portfolio_user_email, password: result.portfolio_user_password, company: result.name })
      setCompanyForm(emptyCompany); setMessage('Company onboarded and data-collection account created.'); await loadData()
    } catch (error) { setMessage(error.message) }
  }

  const submitPortfolio = async (event) => {
    event.preventDefault(); setMessage('')
    try { await postItem('portfolios', portfolioForm); setPortfolioForm(emptyPortfolio); setMessage('Portfolio created.'); await loadData() }
    catch (error) { setMessage(error.message) }
  }

  const submitFund = async (event) => {
    event.preventDefault(); setMessage('')
    try {
      await postItem('funds', { ...fundForm, portfolio_id: Number(fundForm.portfolio_id), vintage_year: fundForm.vintage_year ? Number(fundForm.vintage_year) : undefined })
      setFundForm(emptyFund); setMessage('Fund created.'); await loadData()
    } catch (error) { setMessage(error.message) }
  }

  const submitHolding = async (event) => {
    event.preventDefault(); setMessage('')
    try {
      await postItem('holdings', {
        ...holdingForm, fund_id: Number(holdingForm.fund_id), company_id: Number(holdingForm.company_id),
        ownership_percent: Number(holdingForm.ownership_percent), invested_amount_base: Number(holdingForm.invested_amount_base || 0),
        nav_value_base: Number(holdingForm.nav_value_base || 0),
      })
      setHoldingForm(emptyHolding()); setMessage('Holding linked to the company.'); await loadData()
    } catch (error) { setMessage(error.message) }
  }

  const submitPortfolioCsv = async (mode) => {
    if (!portfolioCsv) { setMessage('Choose an editable portfolio CSV first.'); return }
    setImporting(true); setMessage('')
    try {
      const formData = new FormData()
      formData.append('file', portfolioCsv)
      formData.append('mode', mode)
      const response = await fetch(`${API_BASE_URL}/admin/import/portfolio-csv`, {
        method: 'POST',
        headers: { 'x-user-role': user?.role || '', 'x-user-email': user?.email || '' },
        body: formData,
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) {
        const detail = typeof body.detail === 'string' ? body.detail : body.detail?.message
        throw new Error(detail || 'Unable to import the portfolio CSV.')
      }
      setImportPreview(body)
      if (mode === 'commit') {
        setMessage(`Portfolio CSV committed: ${body.summary.holdings_created} holdings created and ${body.summary.holdings_updated} updated.`)
        await loadData()
      } else {
        setMessage(body.summary.blocked_rows ? 'Preview found blocked rows. Correct the CSV before committing.' : 'Preview passed. The CSV is ready to commit.')
      }
    } catch (error) { setMessage(error.message) }
    finally { setImporting(false) }
  }

  const funds = structure.portfolios.flatMap((portfolio) => portfolio.funds.map((fund) => ({ ...fund, portfolio_name: portfolio.name })))

  return <div className="page-grid">
    <ExecutivePageHeader eyebrow="Portfolio administration" title="Portfolio & company onboarding" description="Create the investment hierarchy, onboard company contributors, and establish the ownership and valuation scope used by ESG analytics." />
    <section className="executive-kpi-grid" aria-label="Portfolio onboarding status">
      <KpiCard title="Companies" value={companies.length} trendLabel="ESG data-collection entities" icon="overview" />
      <KpiCard title="Portfolios" value={structure.summary.portfolio_count || 0} trendLabel="investment scopes" icon="analytics" />
      <KpiCard title="Funds" value={structure.summary.fund_count || 0} trendLabel="reporting structures" icon="reports" />
      <KpiCard title="Active Holdings" value={structure.summary.holding_count || 0} trendLabel={structure.summary.ready_for_exposure ? 'exposure ready' : 'setup required'} icon="actions" tone={structure.summary.ready_for_exposure ? undefined : 'amber'} />
    </section>

    <SectionCard title="Onboard a company" subtitle="Creates the company record and its secure ESG contributor account in one transaction">
      <form className="onboarding-form-grid" onSubmit={submitCompany}>
        <label><span>Company code</span><input required value={companyForm.code} onChange={(event) => setCompanyForm({ ...companyForm, code: event.target.value.toUpperCase() })} /></label>
        <label><span>Legal/company name</span><input required value={companyForm.name} onChange={(event) => setCompanyForm({ ...companyForm, name: event.target.value })} /></label>
        <label><span>Sector</span><input required value={companyForm.sector} onChange={(event) => setCompanyForm({ ...companyForm, sector: event.target.value })} /></label>
        <label><span>Asset class</span><input required value={companyForm.asset_class} onChange={(event) => setCompanyForm({ ...companyForm, asset_class: event.target.value })} /></label>
        <label><span>Geography</span><input required value={companyForm.geography} onChange={(event) => setCompanyForm({ ...companyForm, geography: event.target.value })} /></label>
        <label><span>Onboarding status</span><select value={companyForm.current_status} onChange={(event) => setCompanyForm({ ...companyForm, current_status: event.target.value })}><option value="pre-acquisition">Pre-acquisition</option><option value="onboarding">Onboarding</option><option value="active">Active</option></select></label>
        <label><span>Contributor name</span><input required value={companyForm.contact_name} onChange={(event) => setCompanyForm({ ...companyForm, contact_name: event.target.value })} /></label>
        <label><span>Contributor email</span><input required type="email" value={companyForm.contact_email} onChange={(event) => setCompanyForm({ ...companyForm, contact_email: event.target.value })} /></label>
        <label><span>Temporary password</span><input required type="password" minLength="8" autoComplete="new-password" value={companyForm.temporary_password} onChange={(event) => setCompanyForm({ ...companyForm, temporary_password: event.target.value })} /></label>
        <button className="button primary" type="submit">Onboard company</button>
      </form>
      {credentials ? <div className="credential-callout" role="status"><strong>Share once with {credentials.company}</strong><span>Login: {credentials.email}</span><span>Temporary password: {credentials.password}</span><small>Ask the contributor to sign in and replace the temporary password through the approved support process.</small></div> : null}
    </SectionCard>

    <SectionCard title="Investment hierarchy" subtitle="Create portfolio and fund scopes before linking companies as holdings">
      <div className="portfolio-setup-grid">
        <form className="target-form" onSubmit={submitPortfolio}><h4>Portfolio</h4><label><span>Code</span><input required value={portfolioForm.code} onChange={(event) => setPortfolioForm({ ...portfolioForm, code: event.target.value })} /></label><label><span>Name</span><input required value={portfolioForm.name} onChange={(event) => setPortfolioForm({ ...portfolioForm, name: event.target.value })} /></label><label><span>Base currency</span><input required maxLength="3" value={portfolioForm.base_currency} onChange={(event) => setPortfolioForm({ ...portfolioForm, base_currency: event.target.value.toUpperCase() })} /></label><button className="button secondary" type="submit">Create portfolio</button></form>
        <form className="target-form" onSubmit={submitFund}><h4>Fund</h4><label><span>Portfolio</span><select required value={fundForm.portfolio_id} onChange={(event) => setFundForm({ ...fundForm, portfolio_id: event.target.value })}><option value="">Select</option>{structure.portfolios.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span>Code</span><input required value={fundForm.code} onChange={(event) => setFundForm({ ...fundForm, code: event.target.value })} /></label><label><span>Name</span><input required value={fundForm.name} onChange={(event) => setFundForm({ ...fundForm, name: event.target.value })} /></label><label><span>Vintage year</span><input type="number" value={fundForm.vintage_year} onChange={(event) => setFundForm({ ...fundForm, vintage_year: event.target.value })} /></label><button className="button secondary" type="submit">Create fund</button></form>
        <form className="target-form" onSubmit={submitHolding}><h4>Holding</h4><label><span>Fund</span><select required value={holdingForm.fund_id} onChange={(event) => { const fund = funds.find((item) => item.id === Number(event.target.value)); setHoldingForm({ ...holdingForm, fund_id: event.target.value, currency: fund?.base_currency || 'USD' }) }}><option value="">Select</option>{funds.map((fund) => <option key={fund.id} value={fund.id}>{fund.portfolio_name} / {fund.name}</option>)}</select></label><label><span>Company</span><select required value={holdingForm.company_id} onChange={(event) => setHoldingForm({ ...holdingForm, company_id: event.target.value })}><option value="">Select</option>{companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label><span>Holding ID</span><input required value={holdingForm.external_id} onChange={(event) => setHoldingForm({ ...holdingForm, external_id: event.target.value })} /></label><label><span>Ownership %</span><input required type="number" min="0.0001" max="100" step="0.0001" value={holdingForm.ownership_percent} onChange={(event) => setHoldingForm({ ...holdingForm, ownership_percent: event.target.value })} /></label><label><span>Invested amount</span><input type="number" min="0" step="0.01" value={holdingForm.invested_amount_base} onChange={(event) => setHoldingForm({ ...holdingForm, invested_amount_base: event.target.value })} /></label><label><span>Current NAV</span><input type="number" min="0" step="0.01" value={holdingForm.nav_value_base} onChange={(event) => setHoldingForm({ ...holdingForm, nav_value_base: event.target.value })} /></label><label><span>Effective from</span><input required type="date" value={holdingForm.effective_from} onChange={(event) => setHoldingForm({ ...holdingForm, effective_from: event.target.value })} /></label><button className="button primary" type="submit">Link holding</button></form>
      </div>
    </SectionCard>

    <SectionCard title="Editable portfolio CSV" subtitle="Preview and import portfolio data without hardcoding ownership or valuation values">
      <div className="portfolio-setup-grid">
        <div className="target-form portfolio-import-card">
          <h4>Demo template</h4>
          <p>Contains synthetic, editable records for C001–C020. It is demonstration data, not actual financial exposure.</p>
          <a className="button secondary" href="/demo-portfolio.csv" download>Download demo CSV</a>
        </div>
        <div className="target-form portfolio-import-card">
          <h4>Validate and import</h4>
          <label><span>Portfolio CSV</span><input type="file" accept=".csv,text/csv" onChange={(event) => { setPortfolioCsv(event.target.files?.[0] || null); setImportPreview(null) }} /></label>
          <div className="button-row">
            <button className="button secondary" type="button" disabled={!portfolioCsv || importing} onClick={() => submitPortfolioCsv('preview')}>Preview CSV</button>
            <button className="button primary" type="button" disabled={!portfolioCsv || importing || !importPreview || importPreview.summary.blocked_rows > 0} onClick={() => submitPortfolioCsv('commit')}>Commit CSV</button>
          </div>
        </div>
        <div className="target-form portfolio-import-card" aria-live="polite">
          <h4>Import status</h4>
          {importPreview ? <>
            <span>Total rows: {importPreview.summary.total_rows}</span>
            <span>Ready: {importPreview.summary.ready_rows}</span>
            <span>Blocked: {importPreview.summary.blocked_rows}</span>
            {importPreview.errors.slice(0, 5).map((item) => <small key={`${item.row_number}-${item.holding_external_id}`}>Row {item.row_number}: {item.errors.join('; ')}</small>)}
          </> : <span>Preview a CSV to see validation results.</span>}
        </div>
      </div>
    </SectionCard>

    {message ? <p className="action-message" role="status">{message}</p> : null}
    <SectionCard title="Active holdings register" subtitle="Current ownership, valuation, and portfolio weight"><DataTable columns={holdingColumns} rows={structure.holdings} pageSize={10} emptyMessage={loading ? 'Loading holdings…' : 'No active holdings configured.'} /></SectionCard>
    <SectionCard title="Onboarded companies" subtitle="Companies available for ESG data collection and holding assignment"><DataTable columns={companyColumns} rows={companies} pageSize={10} emptyMessage={loading ? 'Loading companies…' : 'No companies onboarded.'} /></SectionCard>
  </div>
}
