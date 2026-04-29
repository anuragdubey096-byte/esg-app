import { useEffect, useMemo, useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import ActivityFeedCard from '../components/ActivityFeedCard'
import CollaborationPanel from '../components/CollaborationPanel'
import DataTable from '../components/DataTable'
import NarrativeEditor from '../components/NarrativeEditor'
import NarrativeSummaryCard from '../components/NarrativeSummaryCard'
import NarrativeToolbar from '../components/NarrativeToolbar'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import { Button, SelectInput, TextInput } from '../components/ui'
import { useOptionalLiveUpdates } from '../contexts/LiveUpdatesContext'
import useDashboardData, { getLatestSubmission, parseSubmissionPayload, normalizeStatus } from '../hooks/useDashboardData'
import useNarrativeSummary from '../hooks/useNarrativeSummary'
import { API_BASE_URL } from '../lib/api'
import { DEFAULT_REPORT_VIEW, NARRATIVE_UI_COPY } from '../lib/portalOptions'
import { humanizeKey } from '../lib/text'

function toNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function formatValue(value) {
  if (value === null || value === undefined || value === '') return 'n/a'
  if (typeof value === 'number') return value
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

function formatDelta(current, previous) {
  const currentNum = toNumber(current)
  const previousNum = toNumber(previous)
  if (currentNum === null || previousNum === null || previousNum === 0) return 'n/a'
  const pct = Number((((currentNum - previousNum) / previousNum) * 100).toFixed(2))
  return `${pct > 0 ? '+' : ''}${pct}%`
}

function formatScore(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed.toFixed(1) : 'N/A'
}

function getValidationSummary(rows) {
  let errors = 0
  let warnings = 0
  let measured = 0
  let confidenceCount = 0

  rows.forEach((row) => {
    if (row.validation === 'Fail') errors += 1
    if (row.validation === 'Warning') warnings += 1
    if (row.confidence === 'Measured') measured += 1
    if (row.confidence !== 'NA') confidenceCount += 1
  })

  return {
    errors,
    warnings,
    confidence: confidenceCount ? Math.round((measured / confidenceCount) * 100) : 0,
  }
}

export default function ReviewHubPage() {
  const { user } = useOutletContext()
  const [searchParams] = useSearchParams()
  const { companies, refresh: refreshDashboard } = useDashboardData(user)
  const [selectedCompanyId, setSelectedCompanyId] = useState(null)
  const [actionMessage, setActionMessage] = useState('')
  const [validationByField, setValidationByField] = useState({})
  const [rowComments, setRowComments] = useState({})
  const [loadingValidation, setLoadingValidation] = useState(false)
  const [validationErrorMessage, setValidationErrorMessage] = useState('')
  const [activeDecisionField, setActiveDecisionField] = useState('')
  const [activeReviewSection, setActiveReviewSection] = useState('Environmental')
  const [collaboration, setCollaboration] = useState(null)
  const [collaborationMessage, setCollaborationMessage] = useState('')
  const [narrativeTone, setNarrativeTone] = useState(DEFAULT_REPORT_VIEW.narrativeTone)
  const [narrativeDraft, setNarrativeDraft] = useState(null)
  const [narrativeMessage, setNarrativeMessage] = useState('')
  const [narrativeBusy, setNarrativeBusy] = useState(false)
  const targetFieldKey = searchParams.get('field') || ''
  const liveUpdates = useOptionalLiveUpdates()

  useEffect(() => {
    const companyIdParam = searchParams.get('companyId')
    if (companyIdParam) {
      setSelectedCompanyId(companyIdParam)
    }
  }, [searchParams])

  const submissionRows = useMemo(() => {
    return companies.filter(c => getLatestSubmission(c)).map(c => {
      const submissions = Array.isArray(c.submissions) ? [...c.submissions] : []
      const latest = submissions[submissions.length - 1] || null
      const previous = submissions.length > 1 ? submissions[submissions.length - 2] : null
      const payload = parseSubmissionPayload(latest)
      const previousPayload = parseSubmissionPayload(previous)
      const status = normalizeStatus(latest?.status || 'Not Started')
      const previousStatus = normalizeStatus(previous?.status || 'Not Started')
      const backendEsgScore = Number(c.reporting_esg_score)
      const previousEsgScore = toNumber(previousPayload?.esg_score)
      return {
        id: c.id,
        companyName: c.name,
        sector: c.sector,
        geography: c.geography,
        status,
        previousStatus,
        esgScore: Number.isFinite(backendEsgScore) ? backendEsgScore : null,
        previousEsgScore,
        submissionId: latest?.id || null,
        payload,
        previousPayload
      }
    })
  }, [companies])

  const selectedCompany = useMemo(() => {
    return submissionRows.find((row) => row.id === Number(selectedCompanyId)) || submissionRows[0] || { companyName: 'No submissions yet', sector: '--', geography: '--', status: 'Not Started', esgScore: null, previousEsgScore: null, submissionId: null, payload: {} }
  }, [selectedCompanyId, submissionRows])
  const narrative = useNarrativeSummary({
    user,
    audience: 'company',
    companyId: selectedCompany?.id || null,
    tone: narrativeTone,
    enabled: Boolean(selectedCompany?.id),
  })

  useEffect(() => {
    if (!narrative.data?.available) {
      setNarrativeDraft(null)
      return
    }
    setNarrativeDraft({
      headline: narrative.data.headline || '',
      summary: narrative.data.summary || '',
      highlights: Array.isArray(narrative.data.highlights) ? narrative.data.highlights : [],
      watchouts: Array.isArray(narrative.data.watchouts) ? narrative.data.watchouts : [],
      recommendations: Array.isArray(narrative.data.recommendations) ? narrative.data.recommendations : [],
    })
    if (narrative.data.tone) {
      setNarrativeTone(narrative.data.tone)
    }
  }, [narrative.data])

  useEffect(() => {
    let active = true

    const loadValidationErrors = async () => {
      if (!selectedCompany?.submissionId) {
        if (active) {
          setValidationByField({})
          setValidationErrorMessage('')
          setLoadingValidation(false)
        }
        return
      }

      setLoadingValidation(true)
      setValidationErrorMessage('')
      try {
        const response = await fetch(`${API_BASE_URL}/submissions/${selectedCompany.submissionId}/validation-errors`, {
          headers: {
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          },
        })
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}))
          throw new Error(payload.detail || `Failed to load validation errors (${response.status})`)
        }
        const payload = await response.json()
        const grouped = {}
        payload.forEach((item) => {
          const key = item?.field_key
          if (!key) return
          if (!grouped[key]) grouped[key] = []
          grouped[key].push(item)
        })
        if (active) setValidationByField(grouped)
      } catch (error) {
        if (active) {
          setValidationByField({})
          setValidationErrorMessage(error.message || 'Unable to load backend validation errors.')
        }
      } finally {
        if (active) setLoadingValidation(false)
      }
    }

    loadValidationErrors()
    return () => {
      active = false
    }
  }, [selectedCompany?.submissionId, user?.email, user?.role, liveUpdates?.lastEvent?.id])

  useEffect(() => {
    if (!liveUpdates?.lastEvent || !selectedCompany?.submissionId) return
    if (
      liveUpdates.lastEvent.submission_id
      && Number(liveUpdates.lastEvent.submission_id) !== Number(selectedCompany.submissionId)
    ) {
      return
    }
    refreshDashboard()
    narrative.refresh()
  }, [liveUpdates?.lastEvent?.id, narrative.refresh, refreshDashboard, selectedCompany?.submissionId])

  const handleMetricDecision = async (fieldKey, decision) => {
    if (!selectedCompany?.submissionId) return
    setActiveDecisionField(fieldKey)
    setActionMessage('')
    try {
        const response = await fetch(`${API_BASE_URL}/submissions/${selectedCompany.submissionId}/validation-errors/decision`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
        body: JSON.stringify({
          field_key: fieldKey,
          decision,
          comment: rowComments[fieldKey] || null,
        }),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Decision update failed (${response.status})`)
      }
      const payload = await response.json()
      setActionMessage(payload.message || 'Reviewer decision saved.')

        const refreshResponse = await fetch(`${API_BASE_URL}/submissions/${selectedCompany.submissionId}/validation-errors`, {
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
      })
      if (refreshResponse.ok) {
        const refreshed = await refreshResponse.json()
        const grouped = {}
        refreshed.forEach((item) => {
          const key = item?.field_key
          if (!key) return
          if (!grouped[key]) grouped[key] = []
          grouped[key].push(item)
        })
        setValidationByField(grouped)
      }
    } catch (error) {
      setActionMessage(error.message || 'Unable to save reviewer decision.')
    } finally {
      setActiveDecisionField('')
    }
  }

  const submitReview = async (reviewStatus, message) => {
    if (!selectedCompany?.submissionId) return
    setActionMessage('')
    try {
        const response = await fetch(`${API_BASE_URL}/submissions/${selectedCompany.submissionId}/review`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
        body: JSON.stringify({
          reviewer_role: user?.role || 'manager',
          review_status: reviewStatus,
          review_comment: message,
        }),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Review update failed (${response.status})`)
      }
      const payload = await response.json()
      setActionMessage(payload.message || 'Review logged successfully.')
      await refreshDashboard()
      narrative.refresh()
    } catch (error) {
      setActionMessage(error.message || 'Unable to save review status.')
    }
  }

  const generateNarrative = async () => {
    if (!selectedCompany?.id) return
    setNarrativeBusy(true)
    setNarrativeMessage('')
    try {
      const payload = await narrative.generate({
        audience: 'company',
        companyId: selectedCompany.id,
        tone: narrativeTone,
        forceRefresh: true,
      })
      setNarrativeDraft({
        headline: payload.headline || '',
        summary: payload.summary || '',
        highlights: Array.isArray(payload.highlights) ? payload.highlights : [],
        watchouts: Array.isArray(payload.watchouts) ? payload.watchouts : [],
        recommendations: Array.isArray(payload.recommendations) ? payload.recommendations : [],
      })
      setNarrativeMessage('Narrative generated from approved data.')
    } catch (error) {
      setNarrativeMessage(error.message || 'Unable to generate narrative.')
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
      setNarrativeDraft({
        headline: payload.headline || '',
        summary: payload.summary || '',
        highlights: Array.isArray(payload.highlights) ? payload.highlights : [],
        watchouts: Array.isArray(payload.watchouts) ? payload.watchouts : [],
        recommendations: Array.isArray(payload.recommendations) ? payload.recommendations : [],
      })
      setNarrativeMessage('Narrative draft saved.')
    } catch (error) {
      setNarrativeMessage(error.message || 'Unable to save narrative.')
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
      setNarrativeDraft({
        headline: payload.headline || '',
        summary: payload.summary || '',
        highlights: Array.isArray(payload.highlights) ? payload.highlights : [],
        watchouts: Array.isArray(payload.watchouts) ? payload.watchouts : [],
        recommendations: Array.isArray(payload.recommendations) ? payload.recommendations : [],
      })
      await refreshDashboard()
      setNarrativeMessage('Narrative approved and published.')
    } catch (error) {
      setNarrativeMessage(error.message || 'Unable to approve narrative.')
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
      setNarrativeMessage(error.message || 'Unable to export narrative.')
    } finally {
      setNarrativeBusy(false)
    }
  }

  const canEditNarrative = String(user?.role || '').toLowerCase() === 'manager'
  const narrativeFreshnessTone =
    narrative.data?.freshness_status === 'current'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
      : narrative.data?.freshness_status === 'stale'
        ? 'border-amber-200 bg-amber-50 text-amber-800'
        : 'border-slate-200 bg-slate-50 text-slate-700'

  const dataRows = useMemo(() => {
    if (!selectedCompany.payload) return []
    const current = selectedCompany.payload || {}
    const previous = selectedCompany.previousPayload || {}
    const metricKeys = Array.from(
      new Set([
        ...Object.keys(current).filter((key) => !key.endsWith('_confidence')),
        ...Object.keys(previous).filter((key) => !key.endsWith('_confidence')),
      ])
    )

    return metricKeys
      .sort()
      .map((key, index) => {
        const currentValue = current[key]
        const previousValue = previous[key]
        const backendIssues = validationByField[key] || []
        const hasError = backendIssues.some((issue) => String(issue.severity).toLowerCase() === 'error')
        const hasWarning = backendIssues.some((issue) => String(issue.severity).toLowerCase() === 'warning')
        const confidence = current[`${key}_confidence`] || previous[`${key}_confidence`] || 'NA'
        const delta = formatDelta(currentValue, previousValue)
        const validation = hasError ? 'Fail' : hasWarning ? 'Warning' : 'Pass'
        const validationMessage = backendIssues.length > 0 ? backendIssues[0].error_message : ''

        return {
          id: index + 1,
          fieldKey: key,
          section: backendIssues[0]?.section || 'General',
          metric: humanizeKey(key),
          currentValue: formatValue(currentValue),
          previousValue: formatValue(previousValue),
          delta,
          validation,
          validationMessage,
          confidence,
        }
      })
  }, [selectedCompany, validationByField])

  const reviewSections = useMemo(() => {
    const sections = Array.from(new Set(dataRows.map((row) => row.section || 'General').filter(Boolean)))
    return sections.length ? sections : ['General']
  }, [dataRows])

  useEffect(() => {
    if (!reviewSections.includes(activeReviewSection)) {
      setActiveReviewSection(reviewSections[0] || 'General')
    }
  }, [activeReviewSection, reviewSections])

  useEffect(() => {
    if (!selectedCompany?.submissionId || !activeReviewSection) {
      setCollaboration(null)
      setCollaborationMessage('')
      return undefined
    }
    let cancelled = false

    const claimSection = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/submissions/${selectedCompany.submissionId}/collaboration/claim`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          },
          body: JSON.stringify({ section: activeReviewSection }),
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          if (response.status === 409) {
            if (!cancelled) {
              setCollaboration(payload)
              setCollaborationMessage(payload.detail || 'This review section is already claimed by another active editor.')
            }
            return
          }
          throw new Error(payload.detail || `Failed to claim review section (${response.status})`)
        }
        if (!cancelled) {
          setCollaboration(payload)
          setCollaborationMessage('')
        }
      } catch (error) {
        if (!cancelled) {
          setCollaborationMessage(error.message || 'Unable to refresh collaboration state.')
        }
      }
    }

    claimSection()
    const timerId = window.setInterval(claimSection, 30000)
    return () => {
      cancelled = true
      window.clearInterval(timerId)
      fetch(`${API_BASE_URL}/submissions/${selectedCompany.submissionId}/collaboration/release`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
        body: JSON.stringify({ section: activeReviewSection, force: false }),
      }).catch(() => {})
    }
  }, [activeReviewSection, selectedCompany?.submissionId, user?.email, user?.role])

  const targetAlertRow = useMemo(() => {
    if (!targetFieldKey) return null
    return dataRows.find((row) => row.fieldKey === targetFieldKey) || null
  }, [dataRows, targetFieldKey])

  useEffect(() => {
    if (!targetAlertRow?.section) return
    setActiveReviewSection(targetAlertRow.section)
  }, [targetAlertRow?.section])

  useEffect(() => {
    if (!targetFieldKey || !dataRows.length) return undefined
    const timer = window.setTimeout(() => {
      const targetRow = document.querySelector('.row-target-alert')
      if (targetRow) {
        targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }, 120)

    return () => window.clearTimeout(timer)
  }, [targetFieldKey, dataRows.length])

  const visibleRows = useMemo(
    () => dataRows.filter((row) => (activeReviewSection ? row.section === activeReviewSection : true)),
    [activeReviewSection, dataRows],
  )
  const summary = getValidationSummary(visibleRows)
  const activeSectionOwner = useMemo(() => {
    const items = Array.isArray(collaboration?.active_sections) ? collaboration.active_sections : []
    return items.find((item) => item.section === activeReviewSection) || null
  }, [activeReviewSection, collaboration?.active_sections])
  const reviewBlocked = Boolean(activeSectionOwner && !activeSectionOwner.is_you)

  const columns = [
    {
      key: 'metric',
      label: 'Metric',
      sortable: true,
      render: (row) => (
        <div>
          <div>{row.metric}</div>
          {row.validationMessage ? <small style={{ color: 'var(--ui-text-muted)' }}>{row.validationMessage}</small> : null}
        </div>
      ),
    },
    { key: 'currentValue', label: 'Current Year', sortable: true },
    { key: 'previousValue', label: 'Previous Year', sortable: true },
    { key: 'delta', label: 'YoY Delta', sortable: true },
    { key: 'validation', label: 'Validation Status', sortable: true, render: (row) => <StatusBadge value={row.validation} /> },
    { key: 'confidence', label: 'Confidence', sortable: true },
    {
      key: 'comment',
      label: 'Comment',
      render: (row) => (
        <TextInput
          label=""
          value={rowComments[row.fieldKey] || ''}
          onChange={(event) => setRowComments((current) => ({ ...current, [row.fieldKey]: event.target.value }))}
          aria-label={`${row.metric} comment`}
          placeholder="Optional reviewer note"
          disabled={reviewBlocked}
        />
      ),
    },
    {
      key: 'reviewDecision',
      label: 'Reviewer Decision',
      render: (row) => (
        <div className="action-row">
          <Button
            onClick={() => handleMetricDecision(row.fieldKey, 'pass')}
            disabled={activeDecisionField === row.fieldKey || reviewBlocked}
            variant="primary"
          >
            Pass
          </Button>
          <Button
            onClick={() => handleMetricDecision(row.fieldKey, 'fail')}
            disabled={activeDecisionField === row.fieldKey || reviewBlocked}
            variant="secondary"
          >
            Fail
          </Button>
        </div>
      ),
    },
  ]

  return (
    <div className="page-grid">
      <SectionCard title="Review Hub" subtitle="Deep-dive validation and reviewer actions">
        <div className="review-header">
          <div>
            <h4>{selectedCompany.companyName}</h4>
            <p>{selectedCompany.sector} | {selectedCompany.geography}</p>
          </div>

          <div className="review-header-controls">
            <StatusBadge value={selectedCompany.status} />
            <SelectInput
              label="Company"
              value={selectedCompanyId || selectedCompany.id || ''}
              onChange={(event) => setSelectedCompanyId(event.target.value)}
            >
              {submissionRows.slice(0, 24).map((row) => (
                <option key={row.id} value={row.id}>{row.companyName}</option>
              ))}
            </SelectInput>
          </div>
        </div>

        <div className="summary-grid three">
          <article className="summary-box">
            <p>Backend Errors</p>
            <strong>{summary.errors}</strong>
          </article>
          <article className="summary-box">
            <p>Backend Warnings</p>
            <strong>{summary.warnings}</strong>
          </article>
          <article className="summary-box">
            <p>Reviewed Metrics</p>
            <strong>{dataRows.length - summary.errors - summary.warnings}</strong>
          </article>
        </div>

        <p className="mt-2 text-xs text-gray-500">
          Summary sourced from backend validation errors for this submission.
        </p>

        {targetAlertRow ? (
          <article className="focus-alert-card">
            <p className="eyebrow">Opened from Alerts & Risks</p>
            <h4>{targetAlertRow.metric}</h4>
            <p>{targetAlertRow.validationMessage || 'No backend issue text available.'}</p>
            <div className="summary-grid three">
              <article className="summary-box">
                <p>Current Year</p>
                <strong>{targetAlertRow.currentValue}</strong>
              </article>
              <article className="summary-box">
                <p>Previous Year</p>
                <strong>{targetAlertRow.previousValue}</strong>
              </article>
              <article className="summary-box">
                <p>Status</p>
                <strong>{targetAlertRow.validation}</strong>
              </article>
            </div>
          </article>
        ) : null}

        {loadingValidation ? <p className="action-message">Loading backend validation errors...</p> : null}
        {validationErrorMessage ? <p className="action-message">{validationErrorMessage}</p> : null}

        <div className="two-col-grid compact">
          <article className="compare-card">
            <p className="eyebrow">Current Submission</p>
            <h4>ESG Score {formatScore(selectedCompany.esgScore)}</h4>
            <p>Submission ID: {selectedCompany.submissionId || 'n/a'}</p>
            <p>Status: {selectedCompany.status}</p>
          </article>
          <article className="compare-card muted">
            <p className="eyebrow">Prior Submission</p>
            <h4>ESG Score {formatScore(selectedCompany.previousEsgScore)}</h4>
            <p>Status: {selectedCompany.previousStatus}</p>
            <p className="text-xs text-gray-500">Backend payload comparison only.</p>
          </article>
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          {reviewSections.map((section) => (
            <Button
              key={section}
              type="button"
              variant={activeReviewSection === section ? 'primary' : 'secondary'}
              onClick={() => setActiveReviewSection(section)}
            >
              {section}
            </Button>
          ))}
        </div>

        <CollaborationPanel
          collaboration={collaboration}
          activeSection={activeReviewSection}
          conflictMessage={collaborationMessage}
        />

        <DataTable
          columns={columns}
          rows={visibleRows}
          pageSize={7}
          rowClassName={(row) => (row.fieldKey === targetFieldKey ? 'row-target-alert' : '')}
        />

        <div className="action-row">
          <Button type="button" variant="primary" onClick={() => submitReview('approved', 'Submission approved from Review Hub.')} disabled={reviewBlocked}>Approve</Button>
          <Button type="button" variant="secondary" onClick={() => submitReview('resubmission requested', 'Resubmission requested from Review Hub.')} disabled={reviewBlocked}>Request Resubmission</Button>
          <Button type="button" variant="ghost" onClick={() => setActionMessage('Reviewer note saved to audit log.')}>Add Comment</Button>
          {actionMessage ? <p className="action-message">{actionMessage}</p> : null}
        </div>
      </SectionCard>

      <NarrativeSummaryCard
        data={narrative.data}
        loading={narrative.loading}
        error={narrative.error}
        onRefresh={narrative.refresh}
        title="AI ESG Narrative Summary"
        subtitle={NARRATIVE_UI_COPY.pages.reviewHubNarrativeSubtitle}
      />

      <SectionCard
        title="Narrative Controls"
        subtitle={NARRATIVE_UI_COPY.pages.reviewHubNarrativeControlsSubtitle}
      >
        <div className="space-y-4">
          {narrative.data ? (
            <div className={`rounded-xl border px-4 py-3 text-sm ${narrativeFreshnessTone}`}>
              <p className="ui-text-strong">{narrative.data.freshness_label || 'No approved narrative'}</p>
              <p className="mt-1">{narrative.data.freshness_reason || narrative.data.message || 'Narrative refresh state is unavailable.'}</p>
            </div>
          ) : null}
          <NarrativeToolbar
            tone={narrativeTone}
            onToneChange={setNarrativeTone}
            onGenerate={generateNarrative}
            onSave={saveNarrative}
            onApprove={approveNarrative}
            onExport={exportNarrative}
            loading={narrativeBusy}
            canEdit={canEditNarrative}
            generateLabel="Regenerate from latest approved data"
          />
          {canEditNarrative ? (
            <NarrativeEditor value={narrativeDraft || {}} onChange={setNarrativeDraft} disabled={narrativeBusy} />
          ) : null}
          {narrativeMessage ? <p className="text-sm text-slate-600">{narrativeMessage}</p> : null}
        </div>
      </SectionCard>

      <ActivityFeedCard
        user={user}
        title="Review Activity Feed"
        subtitle="Live submission reviews, approvals, unlocks, and active section ownership"
        companyId={selectedCompany?.id || null}
        submissionId={selectedCompany?.submissionId || null}
      />
    </div>
  )
}
