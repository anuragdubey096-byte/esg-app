import { useEffect, useMemo, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import NarrativeEditor from '../components/NarrativeEditor'
import NarrativeSummaryCard from '../components/NarrativeSummaryCard'
import NarrativeToolbar from '../components/NarrativeToolbar'
import SectionCard from '../components/SectionCard'
import useDashboardData from '../hooks/useDashboardData'
import useNarrativeSummary from '../hooks/useNarrativeSummary'
import { API_BASE_URL } from '../lib/api'
import {
  createFilterPresetId,
  loadLastFilterState,
  loadSavedFilterPresets,
  removeSavedFilterPreset,
  sanitizeFilterPresetName,
  saveLastFilterState,
  upsertSavedFilterPreset,
} from '../lib/experience'
import { DEFAULT_REPORT_VIEW, NARRATIVE_UI_COPY, REPORT_FRAMEWORK_OPTIONS } from '../lib/portalOptions'
import { Button } from '../components/ui'

export default function ReportsPage() {
  const { user } = useOutletContext()
  const { companies, cycles } = useDashboardData(user)
  const normalizedRole = String(user?.role || '').toLowerCase()
  const canExport = normalizedRole === 'manager' || normalizedRole === 'investor'
  const canEditNarrative = normalizedRole === 'manager'
  const [framework, setFramework] = useState(DEFAULT_REPORT_VIEW.framework)
  const [portfolio, setPortfolio] = useState(DEFAULT_REPORT_VIEW.portfolio)
  const [period, setPeriod] = useState(DEFAULT_REPORT_VIEW.period)
  const [format, setFormat] = useState(DEFAULT_REPORT_VIEW.format)
  const [message, setMessage] = useState('')
  const [download, setDownload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [narrativeTone, setNarrativeTone] = useState(DEFAULT_REPORT_VIEW.narrativeTone)
  const [narrativeDraft, setNarrativeDraft] = useState(null)
  const [narrativeMessage, setNarrativeMessage] = useState('')
  const [narrativeBusy, setNarrativeBusy] = useState(false)
  const [savedViews, setSavedViews] = useState([])
  const [activeViewId, setActiveViewId] = useState('')
  const hydratedFiltersRef = useRef(false)

  const portfolios = useMemo(() => [DEFAULT_REPORT_VIEW.portfolio, ...companies.map((c) => c.name)], [companies])
  const periods = useMemo(() => {
    const cyclePeriods = (cycles || []).map((cycle) => `FY${cycle.cycle_year}`)
    return [DEFAULT_REPORT_VIEW.period, ...cyclePeriods]
  }, [cycles])
  const filterScope = useMemo(() => `reports:${user?.role || 'guest'}:${user?.email || 'guest'}`, [user?.email, user?.role])
  const activeSavedView = useMemo(
    () => savedViews.find((item) => item.id === activeViewId) || null,
    [activeViewId, savedViews],
  )
  const selectedFramework = useMemo(
    () => REPORT_FRAMEWORK_OPTIONS.find((item) => item.id === framework) || REPORT_FRAMEWORK_OPTIONS[0],
    [framework],
  )
  const narrative = useNarrativeSummary({
    user,
    audience: 'board',
    tone: narrativeTone,
    enabled: Boolean(user),
  })

  useEffect(() => {
    const persisted = loadLastFilterState(filterScope) || {}
    setFramework(
      REPORT_FRAMEWORK_OPTIONS.some((item) => item.id === persisted.framework)
        ? persisted.framework
        : DEFAULT_REPORT_VIEW.framework,
    )
    setPortfolio(persisted.portfolio || DEFAULT_REPORT_VIEW.portfolio)
    setPeriod(persisted.period || DEFAULT_REPORT_VIEW.period)
    setFormat(persisted.format || DEFAULT_REPORT_VIEW.format)
    setNarrativeTone(persisted.narrativeTone || DEFAULT_REPORT_VIEW.narrativeTone)
    setSavedViews(loadSavedFilterPresets(filterScope))
    setActiveViewId('')
    hydratedFiltersRef.current = true
  }, [filterScope])

  useEffect(() => {
    if (!hydratedFiltersRef.current) return
    saveLastFilterState(filterScope, {
      framework,
      portfolio,
      period,
      format,
      narrativeTone,
    })
  }, [filterScope, format, framework, narrativeTone, period, portfolio])

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

  const applySavedView = (preset) => {
    if (!preset?.filters) return
    setFramework(
      REPORT_FRAMEWORK_OPTIONS.some((item) => item.id === preset.filters.framework)
        ? preset.filters.framework
        : DEFAULT_REPORT_VIEW.framework,
    )
    setPortfolio(preset.filters.portfolio || DEFAULT_REPORT_VIEW.portfolio)
    setPeriod(preset.filters.period || DEFAULT_REPORT_VIEW.period)
    setFormat(preset.filters.format || DEFAULT_REPORT_VIEW.format)
    setNarrativeTone(preset.filters.narrativeTone || DEFAULT_REPORT_VIEW.narrativeTone)
    setActiveViewId(preset.id)
  }

  const handleSaveCurrentView = () => {
    const suggestedName = activeSavedView?.name || 'Saved report view'
    const name = sanitizeFilterPresetName(window.prompt('Name this saved report view', suggestedName))
    if (!name) return

    const preset = {
      id: activeSavedView?.id || createFilterPresetId('reports'),
      name,
      filters: {
        framework,
        portfolio,
        period,
        format,
        narrativeTone,
      },
      createdAt: activeSavedView?.createdAt || new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    }

    const nextPresets = upsertSavedFilterPreset(filterScope, preset)
    setSavedViews(nextPresets)
    setActiveViewId(preset.id)
  }

  const handleDeleteSavedView = () => {
    if (!activeSavedView) return
    if (!window.confirm(`Delete saved report view "${activeSavedView.name}"?`)) return
    const nextPresets = removeSavedFilterPreset(filterScope, activeSavedView.id)
    setSavedViews(nextPresets)
    setActiveViewId('')
  }

  const clearFilters = () => {
    setFramework(DEFAULT_REPORT_VIEW.framework)
    setPortfolio(DEFAULT_REPORT_VIEW.portfolio)
    setPeriod(DEFAULT_REPORT_VIEW.period)
    setFormat(DEFAULT_REPORT_VIEW.format)
    setNarrativeTone(DEFAULT_REPORT_VIEW.narrativeTone)
    setActiveViewId('')
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
    setMessage(`Generating ${selectedFramework.label} report...`)
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
      const response = await fetch(`${API_BASE_URL}/reports/${selectedFramework.id}/export?${query.toString()}`, {
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
      setMessage(`Generated ${selectedFramework.label} export (${payload.rows_exported} rows).`)
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
        <div className="saved-filter-toolbar">
          <label>
            <span>Saved views</span>
            <select
              value={activeViewId}
              onChange={(event) => {
                const nextId = event.target.value
                setActiveViewId(nextId)
                if (!nextId) return
                const preset = savedViews.find((item) => item.id === nextId)
                applySavedView(preset)
              }}
            >
              <option value="">Last used</option>
              {savedViews.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.name}
                </option>
              ))}
            </select>
          </label>

          <div className="action-row">
            <Button type="button" variant="secondary" onClick={handleSaveCurrentView}>
              Save current view
            </Button>
            <Button type="button" variant="secondary" onClick={handleDeleteSavedView} disabled={!activeSavedView}>
              Delete saved view
            </Button>
            <Button type="button" variant="ghost" onClick={clearFilters}>
              Clear filters
            </Button>
          </div>
        </div>

        {activeSavedView ? (
          <div className="saved-filter-note">
            Using saved report view "{activeSavedView.name}".
          </div>
        ) : null}

        <div className="framework-row">
          {REPORT_FRAMEWORK_OPTIONS.map((item) => (
            <Button
              key={item.id}
              type="button"
              className={`framework-button ${framework === item.id ? 'active' : ''}`}
              onClick={() => setFramework(item.id)}
            >
              {item.label}
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
          <div className="space-y-3 rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] p-4 text-sm text-[color:var(--ui-text)]">
            <p className="ui-text-strong">
              Download:
              {' '}
              <a href={`${API_BASE_URL}${download.download_url}`} target="_blank" rel="noreferrer" className="underline">
                {download.file_name}
              </a>
            </p>
            <p>
              {download.narrative_included
                ? `Narrative insert attached: ${download.narrative_headline || 'Approved narrative'}`
                : 'No narrative insert attached to this export.'}
            </p>
            {download.impact_headline ? <p>Impact focus: {download.impact_headline}</p> : null}
            {Array.isArray(download.context_summary) && download.context_summary.length ? (
              <ul className="space-y-2">
                {download.context_summary.map((line) => (
                  <li key={line} className="rounded-lg border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] px-3 py-2">
                    {line}
                  </li>
                ))}
              </ul>
            ) : null}
            {Array.isArray(download.benchmark_callouts) && download.benchmark_callouts.length ? (
              <div className="flex flex-wrap gap-2">
                {download.benchmark_callouts.map((callout) => (
                  <span key={callout} className="rounded-full border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] px-3 py-1 text-xs ui-text-strong text-[color:var(--ui-text-muted)]">
                    {callout}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </SectionCard>

      <SectionCard
        title="AI ESG Narrative Summary"
        subtitle={NARRATIVE_UI_COPY.pages.reportsNarrativeSubtitle}
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
            subtitle={NARRATIVE_UI_COPY.pages.reportsNarrativeInsertSubtitle}
          />
        </div>
      </SectionCard>
    </div>
  )
}

