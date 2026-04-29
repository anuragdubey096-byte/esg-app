import { useEffect, useMemo, useRef, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import AnomalySummaryCard from '../components/AnomalySummaryCard'
import ExternalContextFeedCard from '../components/ExternalContextFeedCard'
import ImpactStoryCard from '../components/ImpactStoryCard'
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
import { REPORT_PERIOD_OPTIONS } from '../lib/portalOptions'
import { Button } from '../components/ui'

export default function ReportsPage() {
  const { user } = useOutletContext()
  const { companies } = useDashboardData(user)
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
  const periods = useMemo(() => REPORT_PERIOD_OPTIONS, [])
  const filterScope = useMemo(() => `reports:${user?.role || 'guest'}:${user?.email || 'guest'}`, [user?.email, user?.role])
  const activeSavedView = useMemo(
    () => savedViews.find((item) => item.id === activeViewId) || null,
    [activeViewId, savedViews],
  )
  const selectedCompany = useMemo(
    () => companies.find((item) => item.name === portfolio) || null,
    [companies, portfolio],
  )
  const narrativeAudience = useMemo(
    () => (normalizedRole === 'manager' && selectedCompany ? 'company' : 'board'),
    [normalizedRole, selectedCompany],
  )
  const narrativeCompanyId = narrativeAudience === 'company' ? selectedCompany?.id || null : null
  const selectedFramework = useMemo(
    () => REPORT_FRAMEWORK_OPTIONS.find((item) => item.id === framework) || REPORT_FRAMEWORK_OPTIONS[0],
    [framework],
  )
  const narrative = useNarrativeSummary({
    user,
    audience: narrativeAudience,
    companyId: narrativeCompanyId,
    tone: narrativeTone,
    enabled: Boolean(user),
  })
  const [selectedNarrativeId, setSelectedNarrativeId] = useState('')
  const [reportPreview, setReportPreview] = useState(null)
  const [reportPreviewLoading, setReportPreviewLoading] = useState(false)
  const [reportPreviewError, setReportPreviewError] = useState('')

  useEffect(() => {
    const persisted = loadLastFilterState(filterScope) || {}
    setFramework(
      REPORT_FRAMEWORK_OPTIONS.some((item) => item.id === persisted.framework)
        ? persisted.framework
        : DEFAULT_REPORT_VIEW.framework,
    )
    setPortfolio(persisted.portfolio || DEFAULT_REPORT_VIEW.portfolio)
    setPeriod(periods.includes(persisted.period) ? persisted.period : DEFAULT_REPORT_VIEW.period)
    setFormat(persisted.format || DEFAULT_REPORT_VIEW.format)
    setNarrativeTone(persisted.narrativeTone || DEFAULT_REPORT_VIEW.narrativeTone)
    setSavedViews(loadSavedFilterPresets(filterScope))
    setActiveViewId('')
    hydratedFiltersRef.current = true
  }, [filterScope, periods])

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
    setPeriod(periods.includes(preset.filters.period) ? preset.filters.period : DEFAULT_REPORT_VIEW.period)
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
    setSelectedNarrativeId('')
  }, [narrativeAudience, narrativeCompanyId])

  useEffect(() => {
    syncNarrativeDraft(narrative.data)
  }, [narrative.data])

  useEffect(() => {
    if (selectedNarrativeId) return
    const latestId = narrative.history?.[0]?.narrative_id
    if (latestId) {
      setSelectedNarrativeId(String(latestId))
    }
  }, [narrative.history, selectedNarrativeId])

  useEffect(() => {
    let active = true

    const fetchPreview = async () => {
      if (!user?.role || !canExport) {
        setReportPreview(null)
        setReportPreviewError('')
        setReportPreviewLoading(false)
        return
      }

      setReportPreviewLoading(true)
      setReportPreviewError('')
      try {
        const params = new URLSearchParams({
          period,
          portfolio,
        })
        if (narrative.data?.narrative_id) {
          params.set('narrative_id', String(narrative.data.narrative_id))
        }
        const response = await fetch(`${API_BASE_URL}/reports/${selectedFramework.id}/preview?${params.toString()}`, {
          headers: {
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          },
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(payload.detail || 'Unable to load report preview.')
        }
        if (active) {
          setReportPreview(payload)
        }
      } catch (error) {
        if (active) {
          setReportPreview(null)
          setReportPreviewError(error.message || 'Unable to load report preview.')
        }
      } finally {
        if (active) {
          setReportPreviewLoading(false)
        }
      }
    }

    fetchPreview()
    return () => {
      active = false
    }
  }, [
    canExport,
    narrative.data?.narrative_id,
    period,
    portfolio,
    selectedFramework.id,
    user?.email,
    user?.role,
  ])

  const generateNarrative = async () => {
    setNarrativeBusy(true)
    setNarrativeMessage('')
    try {
      const payload = await narrative.generate({
        audience: narrativeAudience,
        companyId: narrativeCompanyId,
        tone: narrativeTone,
        forceRefresh: true,
      })
      syncNarrativeDraft(payload)
      setNarrativeMessage('Narrative regenerated from latest approved data.')
    } catch (error) {
      setNarrativeMessage(error.message || 'Unable to regenerate narrative.')
    } finally {
      setNarrativeBusy(false)
    }
  }

  const loadSavedNarrative = async () => {
    if (!selectedNarrativeId) return
    setNarrativeBusy(true)
    setNarrativeMessage('')
    try {
      const payload = await narrative.loadNarrative(Number(selectedNarrativeId))
      syncNarrativeDraft(payload)
      setNarrativeMessage(`Loaded saved narrative #${selectedNarrativeId}.`)
    } catch (error) {
      setNarrativeMessage(error.message || 'Unable to load saved narrative.')
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
      if (format === 'pdf' && narrative.data?.narrative_id) {
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
      setMessage(`Generated ${selectedFramework.label} export (${payload.rows_exported} rows). ${payload.narrative_status_label || ''}`.trim())
    } catch (error) {
      setMessage(error.message)
    } finally {
      setLoading(false)
    }
  }

  const previewStatusTone =
    reportPreview?.narrative_status === 'current'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
      : reportPreview?.narrative_status === 'stale'
        ? 'border-amber-200 bg-amber-50 text-amber-800'
        : 'border-slate-200 bg-slate-50 text-slate-700'
  const narrativeSectionSubtitle =
    narrativeAudience === 'company'
      ? 'Board-ready narrative from the selected company approved data'
      : NARRATIVE_UI_COPY.pages.reportsNarrativeSubtitle
  const narrativeInsertSubtitle =
    narrativeAudience === 'company'
      ? 'Selected company narrative insert for reports'
      : NARRATIVE_UI_COPY.pages.reportsNarrativeInsertSubtitle

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

        {canEditNarrative ? (
          <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${previewStatusTone}`}>
            <p className="ui-text-strong">
              {reportPreviewLoading
                ? 'Checking narrative status...'
                : reportPreview?.narrative_status_label || 'No approved narrative'}
            </p>
            <p className="mt-1">
              {reportPreview?.narrative_status_reason || reportPreviewError || 'Report preview will appear once the current context is ready.'}
            </p>
          </div>
        ) : null}

        {reportPreviewError ? <p className="action-message">{reportPreviewError}</p> : null}
        {reportPreview?.trend_summary ? (
          <div className="mt-4 rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-4 py-3 text-sm text-[color:var(--ui-text)]">
            <p className="ui-text-strong">Impact trend preview</p>
            <p className="mt-1">{reportPreview.trend_summary}</p>
          </div>
        ) : null}

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
                : `${download.narrative_status_label || 'No approved narrative'}: ${download.narrative_status_reason || 'No narrative insert attached to this export.'}`}
            </p>
            {download.impact_headline ? <p>Impact focus: {download.impact_headline}</p> : null}
            {download.trend_summary ? <p>{download.trend_summary}</p> : null}
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
            {Array.isArray(download.comparison_rows) && download.comparison_rows.length ? (
              <div className="space-y-2">
                <p className="ui-text-strong text-[color:var(--ui-text)]">Current vs previous</p>
                <div className="grid gap-3 md:grid-cols-2">
                  {download.comparison_rows.slice(0, 4).map((row) => (
                    <div key={row.metric_name} className="rounded-lg border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] px-3 py-2 text-sm text-[color:var(--ui-text)]">
                      <p className="ui-text-strong">{row.metric_name}</p>
                      <p className="text-xs text-[color:var(--ui-text-muted)]">
                        Current: {row.current_value}
                        {' '}
                        {row.unit || ''}
                      </p>
                      <p className="text-xs text-[color:var(--ui-text-muted)]">
                        Previous: {row.previous_value}
                        {' '}
                        {row.unit || ''}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {download?.anomaly_summary?.headline ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-3 text-sm text-amber-950">
                <p className="ui-text-strong">{download.anomaly_summary.headline}</p>
                {download.anomaly_summary.summary ? <p className="mt-1">{download.anomaly_summary.summary}</p> : null}
              </div>
            ) : null}
            {Array.isArray(download.external_context_items) && download.external_context_items.length ? (
              <div className="space-y-2">
                <p className="ui-text-strong text-[color:var(--ui-text)]">Sector & regulatory context included</p>
                <ul className="space-y-2">
                  {download.external_context_items.slice(0, 3).map((item) => (
                    <li key={item.id} className="rounded-lg border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] px-3 py-2">
                      <p className="ui-text-strong">{item.title}</p>
                      {item.action_prompt ? <p className="mt-1 text-xs text-[color:var(--ui-text-muted)]">{item.action_prompt}</p> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </SectionCard>

      {reportPreview?.impact_story ? (
        <ImpactStoryCard
          title="Report Impact Preview"
          subtitle="The approved-data intelligence package that will flow into this export"
          story={reportPreview.impact_story}
          maxInsights={4}
        />
      ) : null}

      {reportPreview?.anomaly_summary ? (
        <AnomalySummaryCard
          title="Report Anomaly Preview"
          subtitle="The approved-data watchlist that will be packaged into this export"
          data={reportPreview.anomaly_summary}
          maxItems={4}
        />
      ) : null}

      {Array.isArray(reportPreview?.external_context_items) && reportPreview.external_context_items.length ? (
        <ExternalContextFeedCard
          title="Report Context Preview"
          subtitle="Sector and regulatory context that will travel with this report package"
          data={{ items: reportPreview.external_context_items }}
        />
      ) : null}

      <SectionCard
        title="AI ESG Narrative Summary"
        subtitle={narrativeSectionSubtitle}
      >
        <div className="space-y-4">
          <div className="flex flex-col gap-3 rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] p-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-wide text-[color:var(--ui-text-muted)]">Saved narratives</p>
              <label className="block min-w-[240px]">
                <span className="sr-only">Select a saved narrative</span>
                <select
                  value={selectedNarrativeId}
                  onChange={(event) => setSelectedNarrativeId(event.target.value)}
                  className="w-full rounded-lg border border-[color:var(--ui-panel-border)] bg-white px-3 py-2 text-sm text-[color:var(--ui-text)]"
                >
                  <option value="">Most recent saved narrative</option>
                  {narrative.history.map((item) => (
                    <option key={item.narrative_id} value={String(item.narrative_id)}>
                      #{item.narrative_id} {item.headline ? `- ${item.headline}` : ''} ({item.status})
                    </option>
                  ))}
                </select>
              </label>
              {narrative.historyError ? (
                <p className="text-xs text-rose-700">{narrative.historyError}</p>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              <Button type="button" variant="secondary" onClick={loadSavedNarrative} disabled={!selectedNarrativeId || narrativeBusy || narrative.historyLoading}>
                Load saved narrative
              </Button>
              <Button type="button" variant="ghost" onClick={narrative.refreshHistory} disabled={narrative.historyLoading}>
                {narrative.historyLoading ? 'Refreshing' : 'Refresh history'}
              </Button>
            </div>
          </div>
          <NarrativeToolbar
            tone={narrativeTone}
            onToneChange={setNarrativeTone}
            onGenerate={canEditNarrative ? generateNarrative : undefined}
            onSave={canEditNarrative ? saveNarrative : undefined}
            onApprove={canEditNarrative ? approveNarrative : undefined}
            onExport={exportNarrative}
            loading={narrativeBusy || narrative.loading}
            canEdit={canEditNarrative}
            generateLabel="Regenerate from latest approved data"
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
            subtitle={narrativeInsertSubtitle}
          />
        </div>
      </SectionCard>
    </div>
  )
}

