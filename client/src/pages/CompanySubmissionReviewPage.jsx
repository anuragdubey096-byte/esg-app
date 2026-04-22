import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useOutletContext, useSearchParams } from 'react-router-dom'
import NarrativeSummaryCard from '../components/NarrativeSummaryCard'
import SectionCard from '../components/SectionCard'
import { Button, TextareaInput } from '../components/ui'
import useNarrativeSummary from '../hooks/useNarrativeSummary'
import useCompanyActiveCycleId from '../hooks/useCompanyActiveCycleId'
import { API_BASE_URL } from '../lib/api'

export default function CompanySubmissionReviewPage() {
  const { user } = useOutletContext()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [agreedToTerms, setAgreedToTerms] = useState(false)
  const [showAllValidationIssues, setShowAllValidationIssues] = useState(false)

  // Review/Audit placeholders (intentionally local and non-persistent)
  const [reviewerComment, setReviewerComment] = useState('')
  const [clarificationDrafts, setClarificationDrafts] = useState({})
  const [sourceReferences, setSourceReferences] = useState({})
  const [lastReviewRefresh, setLastReviewRefresh] = useState(null)

  const requestedCycleId = searchParams.get('cycleId') || ''
  const { cycleId: activeCycleId, loading: cycleLoading, error: cycleError } = useCompanyActiveCycleId(user)
  const cycleId = requestedCycleId || activeCycleId

  useEffect(() => {
    const fetchReview = async () => {
      try {
        setLoading(true)
        const response = await fetch(`${API_BASE_URL}/company/submission/${cycleId}/review`, {
          headers: {
            'X-User-Role': user?.role || 'company',
            'X-User-Email': user?.email || '',
            'Content-Type': 'application/json',
          },
        })

        if (!response.ok) {
          throw new Error(`Failed to fetch review: ${response.status}`)
        }

        const reviewData = await response.json()
        setData(reviewData)
        setLastReviewRefresh(new Date())
        setError(null)
      } catch (err) {
        console.error('Error fetching review:', err)
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    if (!cycleId) return

    fetchReview()
  }, [cycleId, user])

  const flatFields = useMemo(() => {
    if (!data?.all_entered_data) return []
    const rows = []
    data.all_entered_data.forEach((section) => {
      section.fields.forEach((field) => {
        rows.push({
          section: section.section,
          ...field,
        })
      })
    })
    return rows
  }, [data])

  const lowConfidenceCount = useMemo(
    () =>
      flatFields.filter((f) => {
        const level = String(f.confidence_level || '').toLowerCase()
        return level === 'low' || level === 'not available'
      }).length,
    [flatFields]
  )

  const exportReadyCount = useMemo(
    () => flatFields.filter((f) => f.supports_reporting !== false).length,
    [flatFields]
  )
  const narrative = useNarrativeSummary({
    user,
    audience: 'company',
    companyId: data?.company_id || null,
    tone: 'exec-summary',
    enabled: Boolean(data?.company_id),
  })

  const comparisonRows = useMemo(
    () =>
      flatFields
        .filter((field) => (field.prior_year_value ?? '').toString().trim() !== '')
        .slice(0, 8)
        .map((field) => ({
          key: fieldToken(field.section, field.field_key),
          label: field.field_label,
          current: field.value || 'n/a',
          previous: field.prior_year_value || 'n/a',
          yoy:
            field.yoy_variance_percent !== null && field.yoy_variance_percent !== undefined
              ? Number(field.yoy_variance_percent)
              : computeYoyPercent(field.value, field.prior_year_value),
        })),
    [flatFields]
  )

  const missingSourceReferenceCount = useMemo(
    () =>
      flatFields.filter(
        (f) => f.supports_reporting !== false && (f.value || '').toString().trim() !== '' && !sourceReferences[fieldToken(f.section, f.field_key)]
      ).length,
    [flatFields, sourceReferences]
  )

  const handleSubmit = async () => {
    if (!agreedToTerms) {
      alert('Please confirm that the information is accurate')
      return
    }

    try {
      setSubmitting(true)
      const response = await fetch(`${API_BASE_URL}/company/submission/${cycleId}/submit`, {
        method: 'POST',
        headers: {
          'X-User-Role': user?.role || 'company',
          'X-User-Email': user?.email || '',
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        throw new Error('Failed to submit')
      }

      await response.json()
      alert('Submission successful. Your ESG data has been received.')
      navigate('/company/dashboard')
    } catch (err) {
      console.error('Error submitting:', err)
      alert('Error submitting: ' + err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const copyExportFieldList = async () => {
    const exportKeys = flatFields
      .filter((f) => f.supports_reporting !== false)
      .map((f) => `${f.field_key} (${f.unit || 'n/a'})`)
      .join('\n')
    try {
      await navigator.clipboard.writeText(exportKeys)
      alert('Export-ready field list copied.')
    } catch {
      alert('Unable to copy field list on this browser.')
    }
  }

  if (cycleLoading || (loading && Boolean(cycleId))) {
    return (
      <div className="page-grid">
        <SectionCard title="Review & Submit" subtitle="Loading...">
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
        <SectionCard title="Review & Submit" subtitle="Error loading data">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
            <p className="ui-text-strong">Error: {error}</p>
            <p className="text-sm mt-2">Make sure the backend server is running</p>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (!cycleId) {
    return (
      <div className="page-grid">
        <SectionCard title="Review & Submit" subtitle="Error loading data">
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-900">
            <p className="ui-text-strong">Unable to resolve the active reporting cycle.</p>
            <p className="mt-2 text-sm">{cycleError || 'The company dashboard did not return an active cycle id.'}</p>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="page-grid">
        <SectionCard title="Review & Submit" subtitle="No data available">
          <p className="text-gray-600">Unable to load review data.</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <SectionCard title="Submission Summary" subtitle={data.company_name}>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
            <p className="text-sm text-blue-600 ui-text-strong">Total Fields</p>
            <p className="ui-text-display text-blue-700 mt-1">{data.total_data_points}</p>
          </div>
          <div className="p-4 bg-green-50 rounded-lg border border-green-200">
            <p className="text-sm text-green-600 ui-text-strong">Completed Fields</p>
            <p className="ui-text-display text-green-700 mt-1">{data.total_data_points - data.mandatory_fields_incomplete}</p>
          </div>
          <div className={`p-4 rounded-lg border ${data.mandatory_fields_incomplete === 0 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
            <p className={`text-sm ui-text-strong ${data.mandatory_fields_incomplete === 0 ? 'text-green-600' : 'text-red-600'}`}>
              Incomplete Required
            </p>
            <p className={`ui-text-display mt-1 ${data.mandatory_fields_incomplete === 0 ? 'text-green-700' : 'text-red-700'}`}>
              {data.mandatory_fields_incomplete}
            </p>
          </div>
        </div>

        {data.mandatory_fields_incomplete === 0 ? (
          <div className="p-3 bg-green-100 border border-green-300 rounded-lg">
            <p className="ui-text-strong text-green-800">All mandatory fields are complete</p>
          </div>
        ) : (
          <div className="p-3 bg-red-100 border border-red-300 rounded-lg">
            <p className="ui-text-strong text-red-800">{data.mandatory_fields_incomplete} field(s) must be completed before submission</p>
            <Button
              onClick={() => navigate(`/company/submission?cycleId=${cycleId}`)}
              className="mt-2"
              variant="primary"
            >
              Complete Missing Fields
            </Button>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Reviewer Metadata (Placeholder)" subtitle="Local-only review context">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div className="rounded-lg border border-gray-200 p-3 bg-gray-50">
            <p><span className="ui-text-strong">Submission ID:</span> {data.submission_id}</p>
            <p><span className="ui-text-strong">Company ID:</span> {data.company_id}</p>
            <p><span className="ui-text-strong">Cycle Year:</span> {data.cycle_year}</p>
            <p><span className="ui-text-strong">Refreshed At:</span> {lastReviewRefresh ? lastReviewRefresh.toLocaleString() : 'n/a'}</p>
          </div>
          <div className="rounded-lg border border-gray-200 p-3 bg-gray-50">
            <p><span className="ui-text-strong">Prepared By:</span> {user?.email || 'unknown'}</p>
            <p><span className="ui-text-strong">Role:</span> {user?.role || 'company'}</p>
            <p><span className="ui-text-strong">Clarification Drafts:</span> {Object.keys(clarificationDrafts).length}</p>
            <p><span className="ui-text-strong">Source References Drafted:</span> {Object.keys(sourceReferences).length}</p>
          </div>
        </div>
        <div className="mt-4">
          <label className="block text-sm ui-text-strong text-gray-700 mb-1">Reviewer Comment Placeholder</label>
          <TextareaInput
            label="Reviewer Comment Placeholder"
            value={reviewerComment}
            onChange={(e) => setReviewerComment(e.target.value)}
            rows={3}
            placeholder="Local-only reviewer note placeholder (not submitted to backend)."
          />
        </div>
      </SectionCard>

      <SectionCard title="Audit & Export Readiness" subtitle="Placeholder support without API changes">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <AuditMetric title="Export-ready Fields" value={exportReadyCount} tone="blue" />
          <AuditMetric title="Low-confidence Fields" value={lowConfidenceCount} tone="amber" />
          <AuditMetric title="Missing Source References" value={missingSourceReferenceCount} tone="red" />
        </div>
        <div className="mt-4">
          <Button
            onClick={copyExportFieldList}
            variant="primary"
          >
            Copy Export-ready Field List
          </Button>
        </div>
      </SectionCard>

      <SectionCard title="Previous Year Comparison" subtitle="Light-weight reference view for reviewer context">
        {comparisonRows.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 border-b">
                <tr>
                  <th className="text-left p-3 ui-text-strong">Metric</th>
                  <th className="text-right p-3 ui-text-strong">Current</th>
                  <th className="text-right p-3 ui-text-strong">Previous</th>
                  <th className="text-right p-3 ui-text-strong">YoY</th>
                </tr>
              </thead>
              <tbody>
                {comparisonRows.map((row) => (
                  <tr key={row.key} className="border-b hover:bg-gray-50">
                    <td className="p-3 font-medium">{row.label}</td>
                    <td className="p-3 text-right">{row.current}</td>
                    <td className="p-3 text-right">{row.previous}</td>
                    <td className="p-3 text-right ui-text-strong">
                      {row.yoy === null ? 'n/a' : `${row.yoy > 0 ? '+' : ''}${row.yoy}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-gray-600">No prior-year values available yet.</p>
        )}
      </SectionCard>

      {data.outstanding_validation_errors.length > 0 && (
        <SectionCard
          title="Validation Issues"
          subtitle={`${data.outstanding_validation_errors.length} issue(s) found`}
        >
          <div className="mb-4 flex flex-wrap gap-2">
            <span className="rounded-full bg-red-100 px-3 py-1 text-xs ui-text-strong text-red-800">
              {data.outstanding_validation_errors.filter((item) => item.severity === 'error').length} errors
            </span>
            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs ui-text-strong text-amber-800">
              {data.outstanding_validation_errors.filter((item) => item.severity !== 'error').length} warnings
            </span>
          </div>

          <div className="space-y-3">
            {(showAllValidationIssues ? data.outstanding_validation_errors : data.outstanding_validation_errors.slice(0, 4)).map((errorItem) => (
              <div
                key={errorItem.id}
                className={`rounded-lg border p-3 ${errorItem.severity === 'error' ? 'border-red-200 bg-red-50' : 'border-yellow-200 bg-yellow-50'}`}
              >
                <div>
                  <p className="ui-text-strong">
                    {errorItem.severity === 'error' ? 'Error' : 'Warning'}: {errorItem.field_label}
                  </p>
                  <p className="text-sm text-gray-700">{errorItem.error_message}</p>
                  <p className="mt-1 text-xs text-gray-600">Section: {errorItem.section}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            {data.outstanding_validation_errors.length > 4 ? (
              <Button
                onClick={() => setShowAllValidationIssues((current) => !current)}
                variant="secondary"
              >
                {showAllValidationIssues ? 'Show Less' : 'Show All Issues'}
              </Button>
            ) : null}
            <Button
              onClick={() => navigate(`/company/submission?cycleId=${cycleId}`)}
              variant="secondary"
            >
              Fix Issues
            </Button>
          </div>
      </SectionCard>
      )}

      <SectionCard title="Data Preview" subtitle="Review-ready and audit-friendly field detail">
        <div className="space-y-6">
          {data.all_entered_data.map((section) => (
            <div key={section.section} className="border border-gray-200 rounded-lg p-4">
              <div className="flex justify-between items-center mb-4">
                <h3 className="ui-text-display ui-text-strong text-gray-800">{section.section}</h3>
                <span className="text-sm ui-text-strong text-blue-600">{section.completion_percent}% complete</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2 mb-4">
                <div
                  className="bg-blue-500 h-2 rounded-full"
                  style={{ width: `${section.completion_percent}%` }}
                ></div>
              </div>
              <div className="space-y-3 max-h-[32rem] overflow-y-auto">
                {section.fields.map((field) => (
                  <FieldReviewCard
                    key={fieldToken(section.section, field.field_key)}
                    sectionName={section.section}
                    field={field}
                    sourceReferences={sourceReferences}
                    setSourceReferences={setSourceReferences}
                    clarificationDrafts={clarificationDrafts}
                    setClarificationDrafts={setClarificationDrafts}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      <NarrativeSummaryCard
        title="Company Confirmation Letter"
        subtitle="Read-only narrative for the latest approved submission"
        data={narrative.data}
        loading={narrative.loading}
        error={narrative.error}
        onRefresh={narrative.refresh}
      />

      <SectionCard title="Submission Declaration">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h3 className="ui-text-strong text-gray-800 mb-4">Certification</h3>
          <p className="text-gray-700 mb-4">
            I confirm that the ESG data submitted in this form is accurate, complete, and reflects the best available information from our organization.
            The data has been verified and approved for submission.
          </p>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={agreedToTerms}
              onChange={(e) => setAgreedToTerms(e.target.checked)}
              className="w-5 h-5 rounded border-gray-300 focus:ring-2 focus:ring-blue-500"
            />
            <span className="ui-text-strong text-gray-800">I confirm that the information is accurate to the best of my knowledge</span>
          </label>
        </div>
      </SectionCard>

      <div className="col-span-1 lg:col-span-full flex gap-4 justify-between">
        <Button
          onClick={() => navigate(`/company/submission?cycleId=${cycleId}`)}
          variant="secondary"
        >
          Back to Edit
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!agreedToTerms || !data.can_submit || submitting}
          variant="primary"
        >
          {submitting ? 'Submitting...' : 'Submit Submission'}
        </Button>
      </div>

      {!data.can_submit && (
        <div className="col-span-1 lg:col-span-full p-4 bg-yellow-100 border border-yellow-300 rounded-lg">
          <p className="ui-text-strong text-yellow-800">Cannot submit yet - resolve all required errors first.</p>
        </div>
      )}
    </div>
  )
}

function fieldToken(sectionName, fieldKey) {
  return `${sectionName}::${fieldKey}`
}

function AuditMetric({ title, value, tone }) {
  const tones = {
    blue: 'bg-blue-50 border-blue-200 text-blue-700',
    amber: 'bg-amber-50 border-amber-200 text-amber-700',
    red: 'bg-red-50 border-red-200 text-red-700',
  }
  return (
    <div className={`rounded-lg border p-4 ${tones[tone] || tones.blue}`}>
      <p className="text-sm ui-text-strong">{title}</p>
      <p className="ui-text-display mt-1">{value}</p>
    </div>
  )
}

function FieldReviewCard({
  sectionName,
  field,
  sourceReferences,
  setSourceReferences,
  clarificationDrafts,
  setClarificationDrafts,
}) {
  const token = fieldToken(sectionName, field.field_key)
  const sourceValue = sourceReferences[token] || ''
  const clarificationValue = clarificationDrafts[token] || ''
  const lowConfidence = ['low', 'not available'].includes(String(field.confidence_level || '').toLowerCase())
  const exportReady = field.supports_reporting !== false
  const required = field.required === true
  const priorYearValue = (field.prior_year_value ?? '').toString().trim()
  const hasPriorYear = priorYearValue !== ''
  const effectiveYoy =
    field.yoy_variance_percent !== null && field.yoy_variance_percent !== undefined
      ? Number(field.yoy_variance_percent)
      : computeYoyPercent(field.value, field.prior_year_value)

  return (
    <div className="grid grid-cols-1 gap-4 rounded bg-gray-50 p-3 border border-gray-200">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <p className="text-sm ui-text-strong text-gray-700">{field.field_label}</p>
          <p className="text-xs text-gray-500 mt-1">Backend Key: {field.field_key}</p>
          <p className="text-xs text-gray-500 mt-1">Subsection: {field.subsection || 'General'}</p>
          <p className="text-sm text-gray-600 mt-2">Value: {field.value || '(not entered)'}</p>
          <p className="text-sm text-gray-600 mt-1">Previous Year: {hasPriorYear ? field.prior_year_value : '(not available)'}</p>
        </div>
        <div className="space-y-1 text-sm text-gray-600">
          <p>Confidence: <span className="ui-text-strong">{field.confidence_level || 'n/a'}</span></p>
          <p>Unit: <span className="ui-text-strong">{field.unit || 'n/a'}</span></p>
          <p>Required: <span className="ui-text-strong">{required ? 'Yes' : 'No'}</span></p>
          <p>Export Ready: <span className={`ui-text-strong ${exportReady ? 'text-green-700' : 'text-gray-500'}`}>{exportReady ? 'Yes' : 'No'}</span></p>
          <p>Last Updated: <span className="ui-text-strong">{field.last_updated_at ? new Date(field.last_updated_at).toLocaleString() : 'n/a'}</span></p>
          {effectiveYoy !== null ? (
            <p>
              YoY Change:{' '}
              <span className={`ui-text-strong ${Math.abs(effectiveYoy) >= 30 ? 'text-amber-700' : 'text-gray-700'}`}>
                {effectiveYoy > 0 ? '+' : ''}
                {effectiveYoy}%
              </span>
            </p>
          ) : null}
          {lowConfidence ? <p className="text-amber-700 ui-text-strong">Low confidence data-quality warning</p> : null}
        </div>
      </div>

      {field.helper_text ? (
        <div className="rounded border border-gray-200 bg-white p-2 text-xs text-gray-600">
          Helper: {field.helper_text}
        </div>
      ) : null}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs ui-text-strong uppercase tracking-wide text-gray-500 mb-1">
            Source Reference (Placeholder)
          </label>
          <input
            type="text"
            value={sourceValue}
            onChange={(e) => setSourceReferences((prev) => ({ ...prev, [token]: e.target.value }))}
            placeholder="e.g. utility_invoice_2026_q2.pdf"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs ui-text-strong uppercase tracking-wide text-gray-500 mb-1">
            Clarification Request Stub (Placeholder)
          </label>
          <textarea
            value={clarificationValue}
            onChange={(e) => setClarificationDrafts((prev) => ({ ...prev, [token]: e.target.value }))}
            rows={2}
            placeholder="Reviewer clarification placeholder for this field."
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {field.validation_errors?.length > 0 ? (
        <div className="space-y-1">
          {field.validation_errors.map((errorItem) => (
            <p
              key={errorItem.id}
              className={`text-xs ui-text-strong ${errorItem.severity === 'error' ? 'text-red-700' : 'text-amber-700'}`}
            >
              {errorItem.error_message}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function computeYoyPercent(currentValue, previousValue) {
  const current = toNumber(currentValue)
  const previous = toNumber(previousValue)
  if (current === null || previous === null || previous === 0) return null
  return Number((((current - previous) / previous) * 100).toFixed(2))
}

function toNumber(value) {
  if (value === null || value === undefined) return null
  const parsed = Number(String(value).replace(/,/g, '').trim())
  return Number.isFinite(parsed) ? parsed : null
}

