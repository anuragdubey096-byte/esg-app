import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import SectionCard from '../components/SectionCard'
import KpiCard from '../components/KpiCard'
import { Button } from '../components/ui'
import { API_BASE_URL } from '../lib/api'
import { UI_LABELS } from '../lib/uiLabels'

export default function CompanyDashboardPage() {
  const { user } = useOutletContext()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        setLoading(true)
        const response = await fetch(`${API_BASE_URL}/company/dashboard`, {
          headers: {
            'X-User-Role': user?.role || 'company',
            'X-User-Email': user?.email || '',
            'Content-Type': 'application/json',
          },
        })

        if (!response.ok) {
          throw new Error(`Failed to fetch dashboard: ${response.status}`)
        }

        const dashboardData = await response.json()
        setData(dashboardData)
        setError(null)
      } catch (err) {
        console.error('Error fetching dashboard:', err)
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchDashboard()
  }, [user])

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.companyDashboard.title} subtitle={UI_LABELS.pages.companyDashboard.loadingSubtitle}>
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
        <SectionCard title={UI_LABELS.pages.companyDashboard.title} subtitle={UI_LABELS.pages.companyDashboard.errorSubtitle}>
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
            <p className="ui-text-strong">Error: {error}</p>
            <p className="text-sm mt-2">{UI_LABELS.common.backendApiReachable}</p>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.companyDashboard.title} subtitle={UI_LABELS.pages.companyDashboard.noDataSubtitle}>
          <p className="text-gray-600">{UI_LABELS.pages.companyDashboard.noDataMessage}</p>
        </SectionCard>
      </div>
    )
  }

  const statusColorKey = typeof data.status_color === 'string' ? data.status_color : 'grey'
  const submissionStatus = data.submission_status || 'Not Started'
  const companyName = data.company_name || 'Portfolio Company'
  const deadlineUrgency = data.deadline_urgency || 'green'
  const deadline = data.deadline || 'n/a'
  const hasEditableCycle = Boolean(data.current_cycle_id)
  const daysRemaining = Number(data.days_remaining || 0)
  const overallCompletionPercent = Number(data.overall_completion_percent || 0)
  const completedDataPoints = Number(data.completed_data_points || 0)
  const totalDataPoints = Number(data.total_data_points || 0)
  const sectionBreakdown = data.section_breakdown && typeof data.section_breakdown === 'object' ? data.section_breakdown : {}
  const validationErrorCount = Number(data.outstanding_validation_errors || 0)
  const sectionsRequiringCorrection = Array.isArray(data.sections_requiring_correction) ? data.sections_requiring_correction : []
  const actionItemsInProgress = Number(data.action_items_in_progress || 0)

  const statusColors = {
    grey: 'bg-gray-100 text-gray-800',
    blue: 'bg-blue-100 text-blue-800',
    yellow: 'bg-yellow-100 text-yellow-800',
    green: 'bg-green-100 text-green-800',
    red: 'bg-red-100 text-red-800',
    amber: 'bg-amber-100 text-amber-800',
  }

  const statusEmojis = {
    'NOT STARTED': '🚀',
    'IN PROGRESS': '⚡',
    'SUBMITTED': '✅',
    'APPROVED': '🎉',
    'REJECTED': '❌',
    'RESUBMISSION REQUIRED': '⚠️',
  }

  const urgencyColors = {
    green: 'border-l-4 border-green-500',
    amber: 'border-l-4 border-yellow-500',
    red: 'border-l-4 border-red-500',
  }

  return (
    <div className="page-grid">
      <SectionCard title="Submission Status">
        <div className={`p-6 rounded-lg ${statusColors[statusColorKey] || statusColors.grey} border-2`}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm ui-text-strong opacity-75">Current Status</p>
              <p className="ui-text-display mt-2">
                {statusEmojis[submissionStatus] || ''}
                {' '}
                {submissionStatus}
              </p>
              <p className="text-sm mt-3 opacity-80">For: {companyName}</p>
            </div>
            <Button
              onClick={() => {
                if (!hasEditableCycle) return
                navigate(`/company/submission?cycleId=${data.current_cycle_id}`)
              }}
              disabled={!hasEditableCycle}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 ui-text-strong transition-colors"
            >
              {hasEditableCycle && (submissionStatus === 'NOT STARTED' || submissionStatus === 'IN PROGRESS')
                ? 'Continue Submission'
                : hasEditableCycle
                  ? 'View Submission'
                  : 'Await Active Cycle'}
            </Button>
          </div>
          {!hasEditableCycle ? (
            <p className="mt-4 text-sm opacity-80">
              No active reporting cycle is open for edits right now.
            </p>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard title="Submission Deadline">
        <div className={`p-6 rounded-lg bg-gradient-to-r from-blue-50 to-indigo-50 ${urgencyColors[deadlineUrgency] || urgencyColors.green}`}>
          <div className="flex items-end justify-between">
            <div>
              <p className="text-sm ui-text-strong text-gray-600">Deadline</p>
              <p className="ui-text-display text-gray-800 mt-1">{deadline}</p>
              <p className="ui-text-display ui-text-strong mt-2">
                <span className={`${deadlineUrgency === 'red' ? 'text-red-600' : deadlineUrgency === 'amber' ? 'text-yellow-600' : 'text-green-600'}`}>
                  {daysRemaining} days remaining
                </span>
              </p>
            </div>
            {daysRemaining < 7 && (
              <div className="text-right">
                <div className="inline-block bg-red-500 text-white px-4 py-2 rounded-full ui-text-strong animate-pulse">
                  ⏰ URGENT
                </div>
              </div>
            )}
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Completion Progress" subtitle="Overall submission progress">
        <div className="space-y-4">
          <div>
            <div className="flex justify-between mb-2">
              <span className="ui-text-strong text-gray-700">Overall Progress</span>
              <span className="ui-text-display text-blue-600">{overallCompletionPercent}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div
                className="bg-gradient-to-r from-blue-500 to-indigo-600 h-3 rounded-full transition-all"
                style={{ width: `${overallCompletionPercent}%` }}
              ></div>
            </div>
            <p className="text-sm text-gray-600 mt-2">
              {completedDataPoints} of {totalDataPoints} data points completed
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
            {Object.entries(sectionBreakdown).map(([section, percentage]) => (
              <div key={section} className="p-4 border border-gray-200 rounded-lg hover:border-blue-400 transition-colors">
                <p className="text-sm ui-text-strong text-gray-600">{section}</p>
                <p className="ui-text-display text-blue-600 mt-1">{percentage}%</p>
                <div className="w-full bg-gray-200 rounded-full h-2 mt-3">
                  <div
                    className="bg-blue-500 h-2 rounded-full"
                    style={{ width: `${percentage}%` }}
                  ></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </SectionCard>

      {validationErrorCount > 0 && (
        <SectionCard title="Outstanding Issues">
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
            <p className="ui-text-strong text-amber-900">
              ⚠️ {validationErrorCount} validation error{validationErrorCount !== 1 ? 's' : ''} found
            </p>
            {sectionsRequiringCorrection.length > 0 && (
              <div className="mt-3">
                <p className="text-sm text-amber-800 mb-2">Sections requiring attention:</p>
                <div className="flex flex-wrap gap-2">
                  {[...new Set(sectionsRequiringCorrection)].map((section) => (
                    <span key={section} className="inline-block bg-amber-200 text-amber-900 px-3 py-1 rounded-full text-xs ui-text-strong">
                      {section}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <Button
              onClick={() => navigate('/company/submission')}
              className="mt-4 px-4 py-2 bg-amber-600 text-white rounded hover:bg-amber-700 text-sm ui-text-strong transition-colors"
            >
              Fix Issues
            </Button>
          </div>
        </SectionCard>
      )}

      {actionItemsInProgress > 0 && (
        <SectionCard title="ESG Improvement Initiatives">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="ui-text-strong text-blue-900">
              📋 {actionItemsInProgress} action plan{actionItemsInProgress !== 1 ? 's' : ''} in progress
            </p>
            <Button
              onClick={() => navigate('/company/action-plans')}
              className="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm ui-text-strong transition-colors"
            >
              View Action Plans
            </Button>
          </div>
        </SectionCard>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard
          title="Company"
          value={companyName.split(' ').slice(0, 2).join(' ')}
          subtitle="Portfolio Company"
          trend={null}
        />
        <KpiCard
          title="Cycle Year"
          value={data.current_cycle_year || '—'}
          subtitle="Reporting Period"
          trend={null}
        />
        <KpiCard
          title="Data Fields"
          value={`${completedDataPoints}/${totalDataPoints}`}
          subtitle="Completed"
          trend={null}
        />
        <KpiCard
          title="Status"
          value={submissionStatus.split(' ')[0]}
          subtitle="Current state"
          trend={null}
        />
      </div>
    </div>
  )
}
