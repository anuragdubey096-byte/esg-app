import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useOutletContext, useSearchParams } from 'react-router-dom'
import ActivityFeedCard from '../components/ActivityFeedCard'
import CollaborationPanel from '../components/CollaborationPanel'
import SectionCard from '../components/SectionCard'
import { Button, ConfidenceFlagSelector, SelectInput, TextareaInput, TextInput } from '../components/ui'
import useCompanyActiveCycleId from '../hooks/useCompanyActiveCycleId'
import { API_BASE_URL } from '../lib/api'
import { UI_LABELS } from '../lib/uiLabels'

const CONFIDENCE_OPTIONS = ['High', 'Medium', 'Low', 'Estimated', 'Not Available', 'Measured']
const DEFAULT_POLICY_OPTIONS = ['Yes', 'No', 'In Progress', 'Not Applicable']

export default function CompanySubmissionPage() {
  const { user } = useOutletContext()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeSection, setActiveSection] = useState('Submission Context')
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  const [lastSavedAt, setLastSavedAt] = useState(null)
  const [collaboration, setCollaboration] = useState(null)
  const [collaborationMessage, setCollaborationMessage] = useState('')

  const requestedCycleId = searchParams.get('cycleId') || ''
  const { cycleId: activeCycleId, loading: cycleLoading, error: cycleError } = useCompanyActiveCycleId(user)
  const cycleId = requestedCycleId || activeCycleId
  const sections = ['Submission Context', 'Environmental', 'Social', 'Governance', 'Supporting Notes']

  const fetchSubmission = async (sectionName) => {
    setLoading(true)
    try {
      const response = await fetch(
        `${API_BASE_URL}/company/submission/${cycleId}?section=${encodeURIComponent(sectionName)}`,
        {
          headers: {
            'X-User-Role': user?.role || 'company',
            'X-User-Email': user?.email || '',
            'Content-Type': 'application/json',
          },
        }
      )

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Failed to fetch submission: ${response.status}`)
      }

      const submissionData = await response.json()
      setData(submissionData)
      setCollaboration(submissionData?.collaboration || null)
      setError(null)
    } catch (err) {
      console.error('Error fetching submission:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!cycleId) return
    fetchSubmission(activeSection)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSection, cycleId, user])

  useEffect(() => {
    if (!cycleId || !data?.submission_id || !activeSection) return undefined
    let cancelled = false

    const claimSection = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/company/submission/${cycleId}/collaboration/claim`, {
          method: 'POST',
          headers: {
            'X-User-Role': user?.role || 'company',
            'X-User-Email': user?.email || '',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ section: activeSection }),
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          if (response.status === 409) {
            if (!cancelled) {
              setCollaborationMessage(payload.detail || 'This section is currently claimed by another active editor.')
            }
            return
          }
          throw new Error(payload.detail || `Failed to claim section (${response.status})`)
        }
        if (!cancelled) {
          setCollaboration(payload)
          setCollaborationMessage('')
        }
      } catch (err) {
        if (!cancelled) {
          setCollaborationMessage(err.message || 'Unable to refresh collaboration state.')
        }
      }
    }

    claimSection()
    const timerId = window.setInterval(claimSection, 30000)

    return () => {
      cancelled = true
      window.clearInterval(timerId)
      fetch(`${API_BASE_URL}/company/submission/${cycleId}/collaboration/release`, {
        method: 'POST',
        headers: {
          'X-User-Role': user?.role || 'company',
          'X-User-Email': user?.email || '',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ section: activeSection, force: false }),
      }).catch(() => {})
    }
  }, [activeSection, cycleId, data?.submission_id, user?.email, user?.role])

  const handleFieldUpdate = async (fieldKey, value, confidenceLevel, explanation = '') => {
    try {
      setSaving(true)
      const response = await fetch(`${API_BASE_URL}/company/submission/${cycleId}`, {
        method: 'POST',
        headers: {
          'X-User-Role': user?.role || 'company',
          'X-User-Email': user?.email || '',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          field_key: fieldKey,
          value: String(value ?? ''),
          confidence_level: confidenceLevel || 'Estimated',
          explanation,
        }),
      })

      if (!response.ok) {
        let detail = 'Failed to save field'
        try {
          const payload = await response.json()
          if (payload?.detail) detail = payload.detail
        } catch {}
        throw new Error(detail)
      }

      setSaveMessage('Saved')
      setLastSavedAt(new Date())
      setTimeout(() => setSaveMessage(''), 1500)
      await fetchSubmission(activeSection)
    } catch (err) {
      console.error('Error saving field:', err)
      setSaveMessage(`Save failed: ${err.message}`)
      setTimeout(() => setSaveMessage(''), 3000)
    } finally {
      setSaving(false)
    }
  }

  const groupedFields = useMemo(() => {
    if (!data?.fields) return {}
    return data.fields.reduce((acc, field) => {
      const group = field.subsection || 'General'
      if (!acc[group]) acc[group] = []
      acc[group].push(field)
      return acc
    }, {})
  }, [data])

  const activeSectionOwner = useMemo(() => {
    const items = Array.isArray(collaboration?.active_sections) ? collaboration.active_sections : []
    return items.find((item) => item.section === activeSection) || null
  }, [activeSection, collaboration?.active_sections])
  const editingBlocked = Boolean(activeSectionOwner && !activeSectionOwner.is_you)

  if (cycleLoading || (loading && Boolean(cycleId))) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.companySubmission.title} subtitle={UI_LABELS.pages.companySubmission.loadingSubtitle}>
          <div className="flex items-center justify-center py-12">
            <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-blue-600" />
          </div>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.companySubmission.title} subtitle={UI_LABELS.pages.companySubmission.errorSubtitle}>
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
            <p className="ui-text-strong">Error: {error}</p>
            <p className="mt-2 text-sm">{UI_LABELS.common.backendServerRunning}</p>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (!cycleId) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.companySubmission.title} subtitle={UI_LABELS.pages.companySubmission.errorSubtitle}>
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
        <SectionCard title={UI_LABELS.pages.companySubmission.title} subtitle={UI_LABELS.pages.companySubmission.noDataSubtitle}>
          <p className="text-gray-600">{UI_LABELS.pages.companySubmission.noDataMessage}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <div className="mb-4 col-span-1 lg:col-span-full">
        <div className="flex gap-2 overflow-x-auto pb-2">
          {sections.map((section) => (
            <Button
              key={section}
              variant={activeSection === section ? 'primary' : 'secondary'}
              onClick={() => setActiveSection(section)}
            >
              {section}
            </Button>
          ))}
        </div>
      </div>

      <SectionCard
        title={data.section}
        subtitle={`${data.completed_fields} of ${data.total_fields} fields completed (${data.completion_percent}%)`}
      >
        <div className="mb-4">
          <div className="h-3 w-full rounded-full bg-gray-200">
            <div
              className="h-3 rounded-full bg-gradient-to-r from-blue-500 to-indigo-600 transition-all"
              style={{ width: `${data.completion_percent}%` }}
            />
          </div>
        </div>

        {data.validation_status !== 'pass' && (
          <div
            className={`mb-2 rounded-lg border-l-4 p-3 ${
              data.validation_status === 'error'
                ? 'border-red-500 bg-red-50'
                : 'border-yellow-500 bg-yellow-50'
            }`}
          >
            <p className="ui-text-strong">
              {data.error_count > 0 ? `${data.error_count} error(s)` : `${data.warning_count} warning(s)`}
            </p>
          </div>
        )}
      </SectionCard>

      <CollaborationPanel
        collaboration={collaboration}
        activeSection={activeSection}
        conflictMessage={collaborationMessage}
      />

      {Object.entries(groupedFields).map(([subsection, fields]) => (
        <SectionCard
          key={subsection}
          title={subsection}
          subtitle={`${fields.length} field(s)`}
        >
          <div className="space-y-5">
            {fields.map((field) => (
              <FieldEntry
                key={field.field_key}
                field={field}
                onUpdate={handleFieldUpdate}
                saving={saving}
                editingBlocked={editingBlocked}
              />
            ))}
          </div>
        </SectionCard>
      ))}

      <ActivityFeedCard
        user={user}
        title="Submission Activity Feed"
        subtitle="Recent edits, submissions, unlocks, and review milestones"
        companyId={data.company_id}
        submissionId={data.submission_id}
      />

      <div className="sticky bottom-0 z-10 col-span-1 rounded-xl border border-gray-200 bg-white/95 p-4 shadow-sm backdrop-blur lg:col-span-full">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="text-sm text-gray-600">
            <p className="font-medium text-gray-800">
              {saveMessage || 'Draft mode: save field-level updates anytime.'}
            </p>
            <p>
              {lastSavedAt
                ? `Last saved at ${lastSavedAt.toLocaleTimeString()}`
                : 'No local save timestamp yet'}
            </p>
          </div>
          <div className="flex gap-3">
            <Button
              onClick={() => navigate('/company/dashboard')}
              variant="secondary"
            >
              Back to Dashboard
            </Button>
            <Button
              onClick={() => navigate(`/company/submission/review?cycleId=${cycleId}`)}
              variant="primary"
            >
              Review and Submit
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function FieldEntry({ field, onUpdate, saving, editingBlocked = false }) {
  const [value, setValue] = useState(field.value ?? '')
  const [confidence, setConfidence] = useState(field.confidence_level || 'Estimated')
  const [explanation, setExplanation] = useState(field.explanation || '')

  useEffect(() => {
    setValue(field.value ?? '')
    setConfidence(field.confidence_level || 'Estimated')
    setExplanation(field.explanation || '')
  }, [field.value, field.confidence_level, field.explanation])

  const hasErrors = field.validation_errors.some((e) => e.severity === 'error')
  const hasWarnings = field.validation_errors.some((e) => e.severity === 'warning')
  const supportsConfidence = Boolean(field.confidence_field)
  const confidenceOptions = field.confidence_options?.length ? field.confidence_options : CONFIDENCE_OPTIONS
  const policyOptions = field.policy_options?.length ? field.policy_options : DEFAULT_POLICY_OPTIONS
  const lowConfidence = confidence === 'Low' || confidence === 'Not Available'

  const handleSave = () => {
    if (field.read_only) return
    onUpdate(field.field_key, value, supportsConfidence ? confidence : 'Estimated', explanation)
  }

  return (
    <div
      className={`rounded-lg border-2 p-4 ${
        hasErrors ? 'border-red-300 bg-red-50' : hasWarnings ? 'border-yellow-300 bg-yellow-50' : 'border-gray-200'
      }`}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <label className="block ui-text-strong text-gray-800">
            {field.field_label} {field.required ? <span className="text-red-600">*</span> : null}
          </label>
          {field.helper_text ? <p className="mt-1 text-sm text-gray-600">{field.helper_text}</p> : null}
          {field.prior_year_value ? (
            <p className="mt-1 text-xs text-gray-500">Prior year: {field.prior_year_value}</p>
          ) : null}
          {field.unit ? <p className="mt-1 text-xs text-gray-500">Unit: {field.unit}</p> : null}
          {field.last_updated_at ? (
            <p className="mt-1 text-xs text-gray-500">Updated: {new Date(field.last_updated_at).toLocaleString()}</p>
          ) : null}
        </div>
        {field.yoy_variance_percent !== null && field.yoy_variance_percent !== undefined ? (
          <span
            className={`rounded-full px-3 py-1 text-xs ui-text-strong ${
              field.yoy_variance_percent > 30 ? 'bg-red-200 text-red-800' : 'bg-yellow-200 text-yellow-800'
            }`}
          >
            {Math.abs(field.yoy_variance_percent)}% change
          </span>
        ) : null}
      </div>

      <div className={`mb-4 grid gap-4 ${supportsConfidence ? 'grid-cols-1 md:grid-cols-3' : 'grid-cols-1 md:grid-cols-2'}`}>
        <ValueInput
          field={field}
          value={value}
          setValue={setValue}
          policyOptions={policyOptions}
        />

        {supportsConfidence ? (
          <ConfidenceFlagSelector
            label="Confidence"
            value={confidence}
            onChange={setConfidence}
            options={confidenceOptions}
          />
        ) : null}

        <div className="flex items-end">
          <Button
            onClick={handleSave}
            disabled={saving || field.read_only || editingBlocked}
            className="w-full rounded-lg bg-blue-600 px-4 py-2 ui-text-strong text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-400"
          >
            {field.read_only ? 'Read Only' : editingBlocked ? 'Claimed by teammate' : saving ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </div>

      {(field.requires_explanation || lowConfidence) && !field.read_only ? (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="mb-2 text-sm ui-text-strong text-amber-800">
            {field.requires_explanation
              ? 'Explain material variance for reviewer clarity.'
              : 'Add optional context when confidence is Low or Not Available.'}
          </p>
          <TextareaInput
            label="Explanation"
            value={explanation}
            onChange={(e) => setExplanation(e.target.value)}
            placeholder="Enter explanation or source note..."
            rows={2}
          />
        </div>
      ) : null}

      {field.validation_errors.length > 0 ? (
        <div className="mt-2 space-y-2">
          {field.validation_errors.map((errorItem) => (
            <p
              key={errorItem.id}
              className={`text-sm ui-text-strong ${
                errorItem.severity === 'error' ? 'text-red-700' : 'text-yellow-700'
              }`}
            >
              {errorItem.error_message}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function ValueInput({ field, value, setValue, policyOptions }) {
  if (field.input_type === 'textarea') {
    return (
      <TextareaInput
        label="Value"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={3}
        disabled={field.read_only}
        placeholder="Enter details"
      />
    )
  }

  if (field.input_type === 'select') {
    return (
      <SelectInput
        label="Value"
        value={value || ''}
        onChange={(e) => setValue(e.target.value)}
        disabled={field.read_only}
      >
        <option value="">Select an option</option>
        {policyOptions.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </SelectInput>
    )
  }

  const isNumeric =
    field.input_type === 'number' ||
    field.input_type === 'integer' ||
    field.input_type === 'percent' ||
    field.input_type === 'currency'

  return (
    <TextInput
      label="Value"
      type={isNumeric ? 'number' : 'text'}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      disabled={field.read_only}
      step={field.input_type === 'integer' ? '1' : 'any'}
      min={isNumeric ? 0 : undefined}
      placeholder={field.unit ? `Enter value (${field.unit})` : 'Enter value'}
    />
  )
}


