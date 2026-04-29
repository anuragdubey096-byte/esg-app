import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData, { getLatestSubmission, parseSubmissionPayload, calculateESGScore, normalizeStatus } from '../hooks/useDashboardData'
import { validateSubmissionData } from '../esgValidation'
import { ESG_FORM_SECTIONS } from '../esgFormConfig'

const BACKEND_URL = 'http://127.0.0.1:8000'

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

export default function ReviewHubPage() {
  const { user } = useOutletContext()
  const { companies, refresh } = useDashboardData(user)
  const [selectedCompanyId, setSelectedCompanyId] = useState(null)
  const [actionMessage, setActionMessage] = useState('')
  const [metricCommentsByCell, setMetricCommentsByCell] = useState({})

  const submissionRows = useMemo(() => {
    return companies.filter(c => getLatestSubmission(c)).map(c => {
      const latest = getLatestSubmission(c)
      const payload = parseSubmissionPayload(latest)
      const status = normalizeStatus(latest?.status || 'Not Started')
      return {
        id: c.id,
        companyName: c.name,
        sector: c.sector,
        geography: c.geography,
        status,
        esgScore: calculateESGScore(status, payload),
        payload,
        submissionId: latest?.id || null,
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
      esgScore: 0,
      payload: {},
      submissionId: null,
      reviewActions: [],
      validationFlags: [],
    }
  }, [selectedCompanyId, submissionRows])

  const handleMetricCommentChange = (commentKey, value) => {
    if (!commentKey) return
    setMetricCommentsByCell((current) => ({
      ...current,
      [commentKey]: value,
    }))
  }

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
          metric: field.label,
          value: normalizeValue(rawValue),
          validation: mostSevereFlag ? toValidationFromSeverity(mostSevereFlag.severity) : 'Pass',
          confidence: normalizeValue(confidence),
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
        metric: toMetricLabel(fieldName),
        value: normalizeValue(payloadForValidation[fieldName]),
        validation: toValidationFromSeverity(firstFlag.severity),
        confidence: 'NA',
        comment: '',
      })
    })

    if (!rows.length) {
      const checks = validateSubmissionData(payloadForValidation)
      return checks.checks.map((check, index) => ({
        id: index + 1,
        commentKey: buildCommentKey(selectedCompany.id, check.label),
        metric: check.label,
        value: check.message,
        validation: check.status === 'fail' ? 'Fail' : check.status === 'warning' ? 'Warning' : 'Pass',
        confidence: 'NA',
        comment: '',
      }))
    }

    return rows
  }, [selectedCompany])

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
      setActionMessage(successMessage)
    } catch (error) {
      setActionMessage(error.message || 'Unable to update review action right now.')
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

  const columns = [
    { key: 'metric', label: 'Metric', sortable: true },
    { key: 'value', label: 'Value', sortable: false },
    { key: 'validation', label: 'Validation Status', sortable: true, render: (row) => <StatusBadge value={row.validation} /> },
    { key: 'confidence', label: 'Confidence', sortable: false },
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
            <select value={selectedCompanyId || selectedCompany.id || ''} onChange={(event) => setSelectedCompanyId(event.target.value)}>
              {submissionRows.slice(0, 24).map((row) => (
                <option key={row.id} value={row.id}>{row.companyName}</option>
              ))}
            </select>
          </div>
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
            <h4>ESG Score {selectedCompany.esgScore}</h4>
            <p>Submission status: {selectedCompany.status}</p>
          </article>
          <article className="compare-card muted">
            <p className="eyebrow">Previous Year</p>
            <h4>ESG Score {Math.max(0, selectedCompany.esgScore - 5)}</h4>
            <p>Submission status: Approved</p>
          </article>
        </div>

        <DataTable columns={columns} rows={dataRows} pageSize={7} />

        <div className="action-row">
          <button type="button" className="button good" onClick={() => handleReviewAction('approved', 'Submission approved and logged.')}>Approve</button>
          <button type="button" className="button warning" onClick={() => handleReviewAction('resubmission requested', 'Resubmission request sent and logged.')}>Request Resubmission</button>
          <button type="button" className="button" onClick={handleAddComment}>Add Comment</button>
          {actionMessage ? <p className="action-message">{actionMessage}</p> : null}
        </div>
      </SectionCard>
    </div>
  )
}
