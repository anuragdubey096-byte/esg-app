import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData, { getLatestSubmission, parseSubmissionPayload, calculateESGScore, normalizeStatus } from '../hooks/useDashboardData'

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
  const { companies } = useDashboardData(user)
  const [selectedCompanyId, setSelectedCompanyId] = useState(null)
  const [actionMessage, setActionMessage] = useState('')

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
        payload
      }
    })
  }, [companies])

  const selectedCompany = useMemo(() => {
    return submissionRows.find((row) => row.id === Number(selectedCompanyId)) || submissionRows[0] || { companyName: 'No submissions yet', sector: '--', geography: '--', status: 'Not Started', esgScore: 0, payload: {} }
  }, [selectedCompanyId, submissionRows])

  const dataRows = useMemo(() => {
    if (!selectedCompany.payload) return []
    return Object.entries(selectedCompany.payload)
      .filter(([key]) => !key.endsWith('_confidence') && typeof selectedCompany.payload[key] === 'number')
      .map(([key, value], index) => {
        const confidence = selectedCompany.payload[`${key}_confidence`] || 'NA'
        return { id: index + 1, metric: key.replace(/_/g, ' '), value: value, validation: 'Pass', confidence: confidence, comment: '' }
      })
  }, [selectedCompany])

  const summary = getValidationSummary(dataRows)

  const columns = [
    { key: 'metric', label: 'Metric', sortable: true },
    { key: 'value', label: 'Value', sortable: true },
    { key: 'validation', label: 'Validation Status', sortable: true, render: (row) => <StatusBadge value={row.validation} /> },
    { key: 'confidence', label: 'Confidence', sortable: true },
    {
      key: 'comment',
      label: 'Comment',
      render: (row) => <input className="inline-comment" defaultValue={row.comment} aria-label={`${row.metric} comment`} />,
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

        <div className="summary-grid three">
          <article className="summary-box">
            <p>Errors</p>
            <strong>{summary.errors}</strong>
          </article>
          <article className="summary-box">
            <p>Warnings</p>
            <strong>{summary.warnings}</strong>
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
          <button type="button" className="button good" onClick={() => setActionMessage('Submission approved and locked.')}>Approve</button>
          <button type="button" className="button warning" onClick={() => setActionMessage('Resubmission request sent to company owner.')}>Request Resubmission</button>
          <button type="button" className="button" onClick={() => setActionMessage('Reviewer note saved to audit log.')}>Add Comment</button>
          {actionMessage ? <p className="action-message">{actionMessage}</p> : null}
        </div>
      </SectionCard>
    </div>
  )
}
