import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import NarrativeEditor from '../components/NarrativeEditor'
import NarrativeSummaryCard from '../components/NarrativeSummaryCard'
import NarrativeToolbar from '../components/NarrativeToolbar'
import SectionCard from '../components/SectionCard'
import useDashboardData from '../hooks/useDashboardData'
import useNarrativeSummary from '../hooks/useNarrativeSummary'
import { API_BASE_URL } from '../lib/api'
import { Button } from '../components/ui'
const reportFrameworks = ['EDCI', 'SFDR']

export default function ReportsPage() {
  const { user } = useOutletContext()
  const { companies, cycles } = useDashboardData(user)
  const normalizedRole = String(user?.role || '').toLowerCase()
  const canExport = normalizedRole === 'manager' || normalizedRole === 'investor'
  const canEditNarrative = normalizedRole === 'manager'
  const [framework, setFramework] = useState(reportFrameworks[0])
  const [portfolio, setPortfolio] = useState('All Portfolio Companies')
  const [period, setPeriod] = useState('Current Cycle')
  const [format, setFormat] = useState('csv')
  const [message, setMessage] = useState('')
  const [download, setDownload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [narrativeTone, setNarrativeTone] = useState('board-ready')
  const [narrativeDraft, setNarrativeDraft] = useState(null)
  const [narrativeMessage, setNarrativeMessage] = useState('')
  const [narrativeBusy, setNarrativeBusy] = useState(false)

  const portfolios = useMemo(() => ['All Portfolio Companies', ...companies.map((c) => c.name)], [companies])
  const periods = useMemo(() => {
    const cyclePeriods = (cycles || []).map((cycle) => `FY${cycle.cycle_year}`)
    return ['Current Cycle', ...cyclePeriods]
  }, [cycles])
  const narrative = useNarrativeSummary({
    user,
    audience: 'board',
    tone: narrativeTone,
    enabled: Boolean(user),
  })

  const syncNarrativeDraft = (payload) => {
    if (!payload?.available) {
      setNarrativeDraft(null)
      return
    }
    setNarrativeDraft({
      headline: payload.headline || '',
      summary: payload.summary || '',
      highlights: Array.isArray(payload.highlights) ? payload.highlights : [],
      watchouts: Array.isArray(payload.watchouts) ? payload.watchouts : [],
      recommendations: Array.isArray(payload.recommendations) ? payload.recommendations : [],
    })
  }

  useEffect(() => {
    syncNarrativeDraft(narrative.data)
  }, [narrative.data])

  const generateNarrative = async () => {
    setNarrativeBusy(true)
    setNarrativeMessage('')
    try {
      const payload = await narrative.generate({
        audience: 'board',
        tone: narrativeTone,
        forceRefresh: true,
      })
      syncNarrativeDraft(payload)
      setNarrativeMessage('Portfolio narrative generated.')
    } catch (error) {
      setNarrativeMessage(error.message || 'Unable to generate portfolio narrative.')
    } finally {
      setNarrativeBusy(false)
    }
  }

  const saveNarrative = async () => {
    if (!canEditNarrative || !narrative.data?.narrative_id || !narrativeDraft) return
    setNarrativeBusy(true)
    setNarrativeMessage('')
    try {
      const payload = await narrative.update(narrative.data.narrative_id, narrativeDraft)
      syncNarrativeDraft(payload)
      setNarrativeMessage('Portfolio narrative saved.')
    } catch (error) {
      setNarrativeMessage(error.message || 'Unable to save portfolio narrative.')
    } finally {
      setNarrativeBusy(false)
    }
  }

  const approveNarrative = async () => {
    if (!canEditNarrative || !narrative.data?.narrative_id) return
    setNarrativeBusy(true)
    setNarrativeMessage('')
    try {
      await narrative.update(narrative.data.narrative_id, narrativeDraft || {})
      const payload = await narrative.approve(narrative.data.narrative_id, true)
      syncNarrativeDraft(payload)
      setNarrativeMessage('Portfolio narrative approved for report inserts.')
    } catch (error) {
      setNarrativeMessage(error.message || 'Unable to approve portfolio narrative.')
    } finally {
      setNarrativeBusy(false)
    }
  }

  const exportNarrative = async () => {
    if (!narrative.data?.narrative_id) return
    setNarrativeBusy(true)
    setNarrativeMessage('')
    try {
      const payload = await narrative.exportNarrative(narrative.data.narrative_id)
      window.open(`${API_BASE_URL}${payload.download_url}`, '_blank', 'noopener,noreferrer')
      setNarrativeMessage('Narrative PDF exported.')
    } catch (error) {
      setNarrativeMessage(error.message || 'Unable to export portfolio narrative.')
    } finally {
      setNarrativeBusy(false)
    }
  }

  const exportReport = async (event) => {
    event.preventDefault()
    setLoading(true)
    setMessage('Generating report...')
    setDownload(null)
    try {
      const query = new URLSearchParams({
        format,
        period,
        portfolio,
      })
      if (format === 'pdf' && narrative.data?.status === 'approved' && narrative.data?.narrative_id) {
        query.set('narrative_id', String(narrative.data.narrative_id))
      }
      const response = await fetch(`${API_BASE_URL}/reports/${framework.toLowerCase()}/export?${query.toString()}`, {
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || 'Failed to export report')
      }
      const payload = await response.json()
      setDownload(payload)
      setMessage(`Generated ${framework} export (${payload.rows_exported} rows).`)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-grid">
      <SectionCard title="Reports" subtitle="Generate aligned reporting exports for LPs and internal committees">
        {!canExport ? (
          <p className="action-message">CSV/PDF exports are available to manager and investor roles.</p>
        ) : null}
        <div className="framework-row">
          {reportFrameworks.map((item) => (
            <Button
              key={item}
              type="button"
              className={`framework-button ${framework === item ? 'active' : ''}`}
              onClick={() => setFramework(item)}
            >
              {item}
            </Button>
          ))}
        </div>

        <form className="report-form" onSubmit={exportReport}>
          <label>
            <span>Select portfolio/company</span>
            <select value={portfolio} onChange={(event) => setPortfolio(event.target.value)}>
              {portfolios.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>

          <label>
            <span>Select time period</span>
            <select value={period} onChange={(event) => setPeriod(event.target.value)}>
              {periods.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>

          <label>
            <span>Export format</span>
            <select value={format} onChange={(event) => setFormat(event.target.value)}>
              <option value="csv">CSV</option>
              <option value="pdf">PDF</option>
            </select>
          </label>

          <Button className="button" type="submit" disabled={loading || !canExport}>
            {loading ? 'Generating...' : 'Generate Report'}
          </Button>
        </form>

        {message ? <p className="action-message">{message}</p> : null}
        {download ? (
          <p className="text-sm text-slate-700">
            Download:
            {' '}
            <a href={`${API_BASE_URL}${download.download_url}`} target="_blank" rel="noreferrer">
              {download.file_name}
            </a>
          </p>
        ) : null}
      </SectionCard>

      <SectionCard
        title="AI ESG Narrative Summary"
        subtitle="Board-ready narrative from approved portfolio data"
      >
        <div className="space-y-4">
          <NarrativeToolbar
            tone={narrativeTone}
            onToneChange={setNarrativeTone}
            onGenerate={canEditNarrative ? generateNarrative : undefined}
            onSave={canEditNarrative ? saveNarrative : undefined}
            onApprove={canEditNarrative ? approveNarrative : undefined}
            onExport={exportNarrative}
            loading={narrativeBusy || narrative.loading}
            canEdit={canEditNarrative}
          />
          {canEditNarrative ? (
            <NarrativeEditor value={narrativeDraft || {}} onChange={setNarrativeDraft} disabled={narrativeBusy} />
          ) : null}
          {narrativeMessage ? <p className="text-sm text-slate-600">{narrativeMessage}</p> : null}
          <NarrativeSummaryCard
            data={narrative.data}
            loading={narrative.loading}
            error={narrative.error}
            onRefresh={narrative.refresh}
            subtitle="Portfolio-level narrative insert for reports"
          />
        </div>
      </SectionCard>
    </div>
  )
}

