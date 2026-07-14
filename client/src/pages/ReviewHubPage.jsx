import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData, {
  calculateESGScore,
  getLatestSubmission,
  getSortedSubmissions,
  getSubmissionReportingYear,
  normalizeStatus,
  parseSubmissionPayload,
} from '../hooks/useDashboardData'
import { validateSubmissionData } from '../esgValidation'
import { ESG_FORM_SECTIONS } from '../esgFormConfig'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

function toApiReviewStatus(statusLabel) {
  const normalized = String(statusLabel || '').trim().toLowerCase()
  if (normalized === 'under review') return 'under review'
  if (normalized === 'approved') return 'approved'
  if (normalized === 'rejected') return 'rejected'
  if (normalized === 'resubmission requested') return 'resubmission requested'
  if (normalized === 'submitted') return 'submitted'
  return 'under review'
}

function getValidationSummary(rows) {
  let errors = 0
  let warnings = 0
  let passes = 0
  let measured = 0
  let confidenceCount = 0

  rows.forEach((row) => {
    if (row.validation === 'Fail') errors += 1
    if (row.validation === 'Warning') warnings += 1
    if (row.validation === 'Pass') passes += 1
    if (row.confidence === 'Measured') measured += 1
    if (row.confidence !== 'NA') confidenceCount += 1
  })

  return {
    errors,
    warnings,
    passes,
    confidence: confidenceCount ? Math.round((measured / confidenceCount) * 100) : 0,
  }
}

const METRIC_FIELDS = ESG_FORM_SECTIONS.flatMap((section) =>
  section.fields
    .filter((field) => !field.name.endsWith('_document_reference') && field.name !== 'reduction_strategy_description')
    .map((field) => ({
      key: field.name,
      label: field.label,
    }))
)

function toMetricLabel(fieldName) {
  const mapped = METRIC_FIELDS.find((field) => field.key === fieldName)
  if (mapped) return mapped.label
  return String(fieldName || '')
    .replace(/_confidence$/, ' confidence')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function toValidationFromSeverity(severity) {
  const normalized = String(severity || '').trim().toLowerCase()
  if (normalized === 'high') return 'Fail'
  if (normalized === 'medium') return 'Warning'
  if (normalized === 'low') return 'Warning'
  return 'Pass'
}

function normalizeValue(value) {
  if (value === null || value === undefined || value === '') return 'Not provided'
  return String(value)
}

function buildCommentKey(companyId, metricKey) {
  return `${companyId || 'none'}::${metricKey || 'unknown'}`
}

function formatHistoryDate(value) {
  if (!value) return 'Previously recorded'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

export default function ReviewHubPage() {
  const { user } = useOutletContext()
  const { companies, refresh } = useDashboardData(user)
  const canAdminValidate = ['manager', 'admin'].includes(String(user?.role || '').trim().toLowerCase())
  const [selectedCompanyId, setSelectedCompanyId] = useState(null)
  const [actionMessage, setActionMessage] = useState('')
  const [metricCommentsByCell, setMetricCommentsByCell] = useState({})
  const [historicalContext, setHistoricalContext] = useState(null)
  const [historicalLoading, setHistoricalLoading] = useState(false)
  const [submissionHistory, setSubmissionHistory] = useState([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyRevision, setHistoryRevision] = useState(0)
  const [resubmissionDialogOpen, setResubmissionDialogOpen] = useState(false)
  const [resubmissionReason, setResubmissionReason] = useState('')
  const [resubmissionHours, setResubmissionHours] = useState(72)
  const [resubmissionSaving, setResubmissionSaving] = useState(false)

  const submissionRows = useMemo(() => {
    return companies.filter(c => getLatestSubmission(c)).map(c => {
      const submissions = getSortedSubmissions(c)
      const latest = submissions[submissions.length - 1]
      const previous = submissions.length > 1 ? submissions[submissions.length - 2] : null
      const payload = parseSubmissionPayload(latest)
      const previousPayload = parseSubmissionPayload(previous)
      const status = normalizeStatus(latest?.status || 'Not Started')
      return {
        id: c.id,
        companyName: c.name,
        sector: c.sector,
        geography: c.geography,
        status,
        esgScore: calculateESGScore(status, payload),
        priorEsgScore: calculateESGScore(normalizeStatus(previous?.status || ''), previousPayload),
        payload,
        submissionId: latest?.id || null,
        submissionYear: getSubmissionReportingYear(latest) || null,
        reviewActions: c.review_actions || [],
        validationFlags: c.validation_flags || [],
      }
    })
  }, [companies])

  const selectedCompany = useMemo(() => {
    return submissionRows.find((row) => row.id === Number(selectedCompanyId)) || submissionRows[0] || {
      companyName: 'No submissions yet',
      sector: '--',
      geography: '--',
      status: 'Not Started',
      esgScore: null,
      priorEsgScore: null,
      payload: {},
      submissionId: null,
      submissionYear: null,
      reviewActions: [],
      validationFlags: [],
    }
  }, [selectedCompanyId, submissionRows])

  useEffect(() => {
    if (!submissionRows.length) return
    let preferredCompanyId = null
    try {
      preferredCompanyId = Number(localStorage.getItem('reviewHub.selectedCompanyId') || '')
    } catch {
      preferredCompanyId = null
    }

    if (
      preferredCompanyId
      && submissionRows.some((row) => row.id === preferredCompanyId)
      && Number(selectedCompanyId) !== preferredCompanyId
    ) {
      setSelectedCompanyId(preferredCompanyId)
      return
    }

    if (!selectedCompanyId) {
      setSelectedCompanyId(submissionRows[0].id)
    }
  }, [selectedCompanyId, submissionRows])

  const historicalByField = useMemo(() => {
    const lookup = {}
    const rowsBySection = historicalContext?.rows_by_section || {}
    Object.values(rowsBySection).forEach((rows) => {
      if (!Array.isArray(rows)) return
      rows.forEach((row) => {
        if (!row?.field_key) return
        lookup[row.field_key] = row
      })
    })
    return lookup
  }, [historicalContext])

  const handleMetricCommentChange = (commentKey, value) => {
    if (!commentKey) return
    setMetricCommentsByCell((current) => ({
      ...current,
      [commentKey]: value,
    }))
  }

  useEffect(() => {
    let cancelled = false
    const loadHistoricalContext = async () => {
      if (!selectedCompany?.id || !selectedCompany?.submissionId) {
        setHistoricalContext(null)
        return
      }
      setHistoricalLoading(true)
      try {
        const response = await fetch(
          `${BACKEND_URL}/historical-context/company/${selectedCompany.id}?submission_id=${selectedCompany.submissionId}`,
          {
            headers: {
              'x-user-role': user?.role || '',
              'x-user-email': user?.email || '',
            },
          },
        )
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}))
          throw new Error(payload.detail || `Historical context failed (${response.status})`)
        }
        const payload = await response.json()
        if (!cancelled) setHistoricalContext(payload)
      } catch (error) {
        if (!cancelled) {
          setHistoricalContext(null)
          setActionMessage(error.message || 'Unable to load historical context.')
        }
      } finally {
        if (!cancelled) setHistoricalLoading(false)
      }
    }
    loadHistoricalContext()
    return () => {
      cancelled = true
    }
  }, [selectedCompany?.id, selectedCompany?.submissionId, user?.email, user?.role])

  useEffect(() => {
    let cancelled = false
    const loadSubmissionHistory = async () => {
      if (!selectedCompany?.submissionId) {
        setSubmissionHistory([])
        return
      }
      setHistoryLoading(true)
      try {
        const response = await fetch(`${BACKEND_URL}/submissions/${selectedCompany.submissionId}/history`, {
          headers: {
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          },
        })
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}))
          throw new Error(payload.detail || `Submission history failed (${response.status})`)
        }
        const payload = await response.json()
        if (!cancelled) setSubmissionHistory(Array.isArray(payload) ? payload : [])
      } catch (error) {
        if (!cancelled) {
          setSubmissionHistory([])
          setActionMessage(error.message || 'Unable to load submission history.')
        }
      } finally {
        if (!cancelled) setHistoryLoading(false)
      }
    }
    loadSubmissionHistory()
    return () => {
      cancelled = true
    }
  }, [historyRevision, selectedCompany?.submissionId, user?.email, user?.role])

  const dataRows = useMemo(() => {
    const payloadForValidation = selectedCompany.payload && typeof selectedCompany.payload === 'object'
      ? selectedCompany.payload
      : {}
    const validationFlags = Array.isArray(selectedCompany.validationFlags) ? selectedCompany.validationFlags : []

    const payloadYear = Number(payloadForValidation.reporting_year || 0) || null
    const targetYear = payloadYear
    const yearFlags = targetYear
      ? validationFlags.filter((flag) => Number(flag.reporting_year || 0) === targetYear)
      : validationFlags

    const flagsByField = yearFlags.reduce((accumulator, flag) => {
      const key = flag.field_name || 'general'
      if (!accumulator[key]) accumulator[key] = []
      accumulator[key].push(flag)
      return accumulator
    }, {})

    const rows = METRIC_FIELDS
      .map((field, index) => {
        const rawValue = payloadForValidation[field.key]
        const confidence = payloadForValidation[`${field.key}_confidence`] || 'NA'
        const fieldFlags = flagsByField[field.key] || []

        if (rawValue === undefined && fieldFlags.length === 0) return null

        const mostSevereFlag = [...fieldFlags].sort((left, right) => {
          const rank = { high: 3, medium: 2, low: 1 }
          const leftRank = rank[String(left.severity || '').toLowerCase()] || 0
          const rightRank = rank[String(right.severity || '').toLowerCase()] || 0
          return rightRank - leftRank
        })[0]

        return {
          id: index + 1,
          commentKey: buildCommentKey(selectedCompany.id, field.key),
          fieldKey: field.key,
          metric: field.label,
          value: normalizeValue(rawValue),
          validation: mostSevereFlag ? toValidationFromSeverity(mostSevereFlag.severity) : 'Pass',
          confidence: normalizeValue(confidence),
          priorValue: normalizeValue(historicalByField[field.key]?.prior_value),
          delta: historicalByField[field.key]?.delta ?? 'N/A',
          variance: historicalByField[field.key]?.variance_percent ?? 'N/A',
          varianceStatus: historicalByField[field.key]?.status || 'ok',
          comment: '',
        }
      })
      .filter(Boolean)

    Object.keys(flagsByField).forEach((fieldName) => {
      if (METRIC_FIELDS.some((field) => field.key === fieldName)) return
      const firstFlag = flagsByField[fieldName]?.[0]
      if (!firstFlag) return
      rows.push({
        id: rows.length + 1,
        commentKey: buildCommentKey(selectedCompany.id, fieldName),
        fieldKey: fieldName,
        metric: toMetricLabel(fieldName),
        value: normalizeValue(payloadForValidation[fieldName]),
        validation: toValidationFromSeverity(firstFlag.severity),
        confidence: 'NA',
        priorValue: normalizeValue(historicalByField[fieldName]?.prior_value),
        delta: historicalByField[fieldName]?.delta ?? 'N/A',
        variance: historicalByField[fieldName]?.variance_percent ?? 'N/A',
        varianceStatus: historicalByField[fieldName]?.status || 'ok',
        comment: '',
      })
    })

    if (!rows.length) {
      const checks = validateSubmissionData(payloadForValidation)
      return checks.checks.map((check, index) => ({
        id: index + 1,
        commentKey: buildCommentKey(selectedCompany.id, check.label),
        fieldKey: null,
        metric: check.label,
        value: check.message,
        validation: check.status === 'fail' ? 'Fail' : check.status === 'warning' ? 'Warning' : 'Pass',
        confidence: 'NA',
        priorValue: 'N/A',
        delta: 'N/A',
        variance: 'N/A',
        varianceStatus: 'ok',
        comment: '',
      }))
    }

    return rows
  }, [historicalByField, selectedCompany])

  const summary = getValidationSummary(dataRows)

  const managerPost = async (path, method = 'POST', body = null) => {
    const response = await fetch(`${BACKEND_URL}${path}`, {
      method,
      headers: body
        ? {
            'Content-Type': 'application/json',
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          }
        : {
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          },
      ...(body ? { body: JSON.stringify(body) } : {}),
    })
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}))
      throw new Error(errorPayload.detail || `Request failed (${response.status})`)
    }
    return response.json().catch(() => ({}))
  }

  const handleReviewAction = async (targetStatus, successMessage, commentText = '') => {
    if (!selectedCompany.submissionId) {
      setActionMessage('No submission is selected for review actions.')
      return
    }

    try {
      const currentStatus = toApiReviewStatus(selectedCompany.status)
      if (
        ['approved', 'rejected', 'resubmission requested'].includes(targetStatus)
        && currentStatus === 'submitted'
      ) {
        await managerPost(`/submissions/${selectedCompany.submissionId}/status`, 'PATCH', { status: 'under review' })
      }
      await managerPost(`/submissions/${selectedCompany.submissionId}/review`, 'POST', {
        reviewer_role: 'Manager',
        review_status: targetStatus,
        review_comment: commentText || 'Reviewed via Review Hub',
      })
      await refresh()
      setHistoryRevision((current) => current + 1)
      setActionMessage(successMessage)
    } catch (error) {
      setActionMessage(error.message || 'Unable to update review action right now.')
    }
  }

  const handleRequestResubmission = async (event) => {
    event.preventDefault()
    const reason = resubmissionReason.trim()
    if (!reason) {
      setActionMessage('A correction reason is required before resubmission can be requested.')
      return
    }
    if (!selectedCompany.submissionId) return

    setResubmissionSaving(true)
    try {
      await managerPost(`/submissions/${selectedCompany.submissionId}/unlock`, 'POST', {
        reason,
        expiry_hours: Number(resubmissionHours),
      })
      await refresh()
      setHistoryRevision((current) => current + 1)
      setResubmissionDialogOpen(false)
      setResubmissionReason('')
      setActionMessage(`Corrections requested. Editing is unlocked for ${resubmissionHours} hours.`)
    } catch (error) {
      setActionMessage(error.message || 'Unable to request resubmission right now.')
    } finally {
      setResubmissionSaving(false)
    }
  }

  const handleAddComment = async () => {
    const comment = window.prompt('Enter reviewer comment', '')
    if (comment == null) return
    const trimmed = comment.trim()
    if (!trimmed) {
      setActionMessage('Comment was empty, nothing was saved.')
      return
    }
    const currentStatus = toApiReviewStatus(selectedCompany.status)
    await handleReviewAction(currentStatus, 'Reviewer comment saved.', trimmed)
  }

  const handleValidationDecision = async (row, decision) => {
    if (!selectedCompany.submissionId) {
      setActionMessage('No submission is selected for validation decision.')
      return
    }
    if (!row?.fieldKey) {
      setActionMessage('This row does not have a mappable field key.')
      return
    }

    let comment = ''
    if (decision === 'fail') {
      const prompted = window.prompt('Optional fail reason for this metric', '')
      if (prompted === null) return
      comment = prompted.trim()
    }

    try {
      await managerPost(`/submissions/${selectedCompany.submissionId}/validation-decision`, 'POST', {
        field_name: row.fieldKey,
        decision,
        comment,
      })
      await refresh()
      setActionMessage(`Validation marked as ${decision.toUpperCase()} for ${row.metric}.`)
    } catch (error) {
      setActionMessage(error.message || 'Unable to save validation decision right now.')
    }
  }

  const columns = [
    { key: 'metric', label: 'Metric', sortable: true },
    { key: 'value', label: 'Value', sortable: false },
    { key: 'priorValue', label: 'Prior Year', sortable: false },
    {
      key: 'variance',
      label: 'Variance',
      sortable: true,
      render: (row) => (
        <span
          style={{
            color: row.varianceStatus === 'error' ? '#b91c1c' : row.varianceStatus === 'warning' ? '#b45309' : '#166534',
            fontWeight: 600,
          }}
        >
          {row.variance === 'N/A' ? 'N/A' : `${row.variance}%`}
        </span>
      ),
    },
    { key: 'delta', label: 'Delta', sortable: true },
    { key: 'validation', label: 'Validation Status', sortable: true, render: (row) => <StatusBadge value={row.validation} /> },
    { key: 'confidence', label: 'Confidence', sortable: false },
    {
      key: 'validationActions',
      label: 'Pass / Fail',
      render: (row) => (
        canAdminValidate ? (
          <div className="inline-flex gap-2">
            <button
              type="button"
              className="button text-xs"
              onClick={() => handleValidationDecision(row, 'pass')}
              disabled={!selectedCompany.submissionId || !row.fieldKey}
            >
              Pass
            </button>
            <button
              type="button"
              className="button warning text-xs"
              onClick={() => handleValidationDecision(row, 'fail')}
              disabled={!selectedCompany.submissionId || !row.fieldKey}
            >
              Fail
            </button>
          </div>
        ) : <span>-</span>
      ),
    },
    {
      key: 'comment',
      label: 'Comment',
      render: (row) => (
        <input
          className="inline-comment"
          value={metricCommentsByCell[row.commentKey] || row.comment || ''}
          onChange={(event) => handleMetricCommentChange(row.commentKey, event.target.value)}
          aria-label={`${row.metric} comment`}
          placeholder="Add comment"
          autoComplete="off"
        />
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
            <select
              value={selectedCompanyId || selectedCompany.id || ''}
              onChange={(event) => {
                const nextCompanyId = Number(event.target.value)
                setSelectedCompanyId(nextCompanyId)
                try {
                  localStorage.setItem('reviewHub.selectedCompanyId', String(nextCompanyId))
                } catch {
                  // Ignore local storage write failures.
                }
              }}
            >
              {submissionRows.slice(0, 24).map((row) => (
                <option key={row.id} value={row.id}>{row.companyName}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="summary-box">
          <p>
            Submission year: <strong>{selectedCompany.submissionYear || historicalContext?.current_cycle_year || 'N/A'}</strong>
            {' '}| Prior approved year:{' '}
            <strong>{historicalContext?.prior_cycle_year || 'Not available'}</strong>
          </p>
          {historicalContext && !historicalContext.prior_submission_id ? (
            <p className="text-sm text-amber-700">No prior approved submission was found before this selected submission.</p>
          ) : null}
        </div>

        <div className="summary-grid four">
          <article className="summary-box">
            <p>Errors</p>
            <strong>{summary.errors}</strong>
          </article>
          <article className="summary-box">
            <p>Warnings</p>
            <strong>{summary.warnings}</strong>
          </article>
          <article className="summary-box">
            <p>Passes</p>
            <strong>{summary.passes}</strong>
          </article>
          <article className="summary-box">
            <p>Data Confidence</p>
            <strong>{summary.confidence}%</strong>
          </article>
        </div>

        <div className="two-col-grid compact">
          <article className="compare-card">
            <p className="eyebrow">Current Year</p>
            <h4>ESG Score {selectedCompany.esgScore ?? 'N/A'}</h4>
            <p>Submission status: {selectedCompany.status}</p>
          </article>
          <article className="compare-card muted">
            <p className="eyebrow">Previous Year</p>
            <h4>ESG Score {selectedCompany.priorEsgScore ?? 'N/A'}</h4>
            <p>Submission status: {selectedCompany.priorEsgScore == null ? 'No prior submission' : 'Historical'}</p>
          </article>
        </div>

        <SectionCard title="Company Section Comments" subtitle="Read-only explanations grouped by ESG category">
          {historicalLoading ? <p>Loading comments...</p> : null}
          {!historicalLoading && historicalContext ? (
            <div className="grid gap-3 md:grid-cols-3">
              {['environmental', 'social', 'governance'].map((sectionKey) => {
                const comments = historicalContext?.section_comments?.[sectionKey] || []
                return (
                  <article key={sectionKey} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">{sectionKey}</p>
                    {comments.length ? (
                      <ul className="mt-2 space-y-2 text-xs text-slate-700">
                        {comments.slice(-5).reverse().map((item, index) => (
                          <li key={`${sectionKey}-${index}`} className="rounded border border-slate-200 bg-white p-2">
                            <p className="font-semibold text-slate-600">{item.timestamp || 'N/A'}</p>
                            <p>{item.text || ''}</p>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-xs text-slate-500">No comments provided.</p>
                    )}
                  </article>
                )
              })}
            </div>
          ) : null}
        </SectionCard>

        <DataTable columns={columns} rows={dataRows} pageSize={7} />

        <SectionCard title="Submission History" subtitle="Review decisions and correction windows for this reporting cycle">
          {historyLoading ? <p className="review-history-empty">Loading submission history...</p> : null}
          {!historyLoading && !submissionHistory.length ? (
            <p className="review-history-empty">No review activity has been recorded yet.</p>
          ) : null}
          {!historyLoading && submissionHistory.length ? (
            <ol className="review-history-list">
              {submissionHistory.map((entry) => (
                <li key={entry.id} className="review-history-item">
                  <span className={`review-history-marker ${entry.event_type}`} aria-hidden="true" />
                  <div>
                    <div className="review-history-heading">
                      <StatusBadge value={entry.status} />
                      <time dateTime={entry.created_at || undefined}>{formatHistoryDate(entry.created_at)}</time>
                    </div>
                    <p>{entry.comment || 'No comment provided.'}</p>
                    <small>
                      {entry.event_type === 'unlock' ? 'Correction window' : 'Review decision'} by {entry.actor || 'manager'}
                      {entry.expires_at ? ` · Expires ${formatHistoryDate(entry.expires_at)}` : ''}
                      {entry.event_type === 'unlock' ? ` · ${entry.active ? 'Active' : 'Expired'}` : ''}
                    </small>
                  </div>
                </li>
              ))}
            </ol>
          ) : null}
        </SectionCard>

        <div className="action-row">
          <button type="button" className="button good" onClick={() => handleReviewAction('approved', 'Submission approved and logged.')}>Approve</button>
          <button type="button" className="button warning" onClick={() => setResubmissionDialogOpen(true)}>Request Resubmission</button>
          <button type="button" className="button" onClick={handleAddComment}>Add Comment</button>
          {actionMessage ? <p className="action-message">{actionMessage}</p> : null}
        </div>
      </SectionCard>

      {resubmissionDialogOpen ? (
        <div className="submission-dialog-backdrop" role="presentation" onMouseDown={() => !resubmissionSaving && setResubmissionDialogOpen(false)}>
          <form
            className="submission-dialog resubmission-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="resubmission-dialog-title"
            onMouseDown={(event) => event.stopPropagation()}
            onSubmit={handleRequestResubmission}
          >
            <p className="submission-progress-eyebrow">Manager action</p>
            <h3 id="resubmission-dialog-title">Request corrections</h3>
            <p>The company will receive an editable draft based on its latest submission.</p>
            <label>
              Correction reason
              <textarea
                value={resubmissionReason}
                onChange={(event) => setResubmissionReason(event.target.value)}
                placeholder="Describe the metrics or evidence that must be corrected"
                rows={4}
                required
                autoFocus
              />
            </label>
            <label>
              Editing window
              <select value={resubmissionHours} onChange={(event) => setResubmissionHours(Number(event.target.value))}>
                <option value={24}>24 hours</option>
                <option value={72}>3 days</option>
                <option value={168}>7 days</option>
                <option value={336}>14 days</option>
                <option value={720}>30 days</option>
              </select>
            </label>
            <div className="submission-dialog-actions">
              <button type="button" onClick={() => setResubmissionDialogOpen(false)} disabled={resubmissionSaving}>Cancel</button>
              <button type="submit" className="confirm" disabled={resubmissionSaving || !resubmissionReason.trim()}>
                {resubmissionSaving ? 'Requesting...' : 'Request corrections'}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  )
}
