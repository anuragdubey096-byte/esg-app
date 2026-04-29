import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { normalizeStatusText } from '../components/ui/status'
import { useOptionalLiveUpdates } from '../contexts/LiveUpdatesContext'
import { API_BASE_URL } from '../lib/api'

function getDashboardPath(user) {
  if (!user) return '/dashboard/manager'
  if (user.role === 'company') return `/dashboard/company/${user.id}`
  return `/dashboard/${user.role}`
}

const LIVE_REFRESH_EVENT_TYPES = new Set([
  'company_created',
  'company_onboarded',
  'cycle_created',
  'cycle_status_changed',
  'submission_submitted',
  'submission_status_changed',
  'submission_review_logged',
  'action_plan_created',
  'action_plan_updated',
  'action_plan_deleted',
])

export function normalizeStatus(status) {
  return normalizeStatusText(status)
}

export function getLatestSubmission(company) {
  if (!company?.submissions?.length) return null
  return company.submissions[company.submissions.length - 1]
}

export function parseSubmissionPayload(submission) {
  if (!submission?.esg_data) return null
  try {
    const parsed = JSON.parse(submission.esg_data)
    return typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

export function getProgressFromStatus(status) {
  if (status === 'Approved') return 100
  if (status === 'Under Review') return 84
  if (status === 'Submitted') return 85
  if (status === 'Resubmission Required') return 58
  if (status === 'In Progress') return 46
  return 8
}

export function calculateESGScore(status, payload) {
  const baseline = {
    'Not Started': 34,
    'In Progress': 52,
    Submitted: 68,
    'Under Review': 75,
    Approved: 82,
    'Resubmission Required': 48,
    Rejected: 44,
  }[status] || 50

  if (!payload) return baseline

  let score = baseline

  const reductionTarget = Number(payload.reduction_target_percent || 0)
  const femaleRepresentation = Number(payload.female_representation_percent || 0)
  const independentBoard = Number(payload.independent_board_members_percent || 0)
  const trifr = Number(payload.trifr || 0)
  const corruptionCases = Number(payload.confirmed_cases_of_corruption || 0)
  const totalEmissions = Number(payload.total_ghg_emissions || 0)

  score += Math.min(12, reductionTarget * 0.28)
  score += Math.min(10, femaleRepresentation * 0.12)
  score += Math.min(8, independentBoard * 0.1)
  score += Math.max(0, 7 - trifr * 2)
  score += corruptionCases === 0 ? 4 : -Math.min(8, corruptionCases * 2)
  score -= Math.min(10, totalEmissions / 500)

  return Math.max(0, Math.min(100, Math.round(score)))
}

function parseDateString(dateString) {
  if (!dateString) return null
  const parsed = new Date(`${dateString}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function getPreferredCycle(cycles) {
  if (!cycles?.length) return null
  const activeCycle = cycles.find((cycle) => String(cycle.status).toLowerCase() === 'active')
  return activeCycle || cycles[0]
}

export function getDaysToDeadline(cycles) {
  const cycle = getPreferredCycle(cycles)
  const deadline = parseDateString(cycle?.submission_deadline)
  if (!deadline) return null

  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  return Math.ceil((deadline.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
}

export function buildRecentMonthLabels(count = 6) {
  const monthLabels = []
  const now = new Date()
  for (let index = count - 1; index >= 0; index -= 1) {
    const value = new Date(now.getFullYear(), now.getMonth() - index, 1)
    monthLabels.push(value.toLocaleString('en-US', { month: 'short' }))
  }
  return monthLabels
}

export function getRiskLevel({ status, esgScore, deadline }) {
  if (status === 'Approved') return 'Low'
  if (status === 'Resubmission Required' || status === 'Rejected') return 'High'

  const deadlineDate = parseDateString(deadline)
  if (deadlineDate) {
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const diff = Math.ceil((deadlineDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
    if (diff < 0) return 'High'
    if (diff <= 7) return status === 'Not Started' ? 'High' : 'Medium'
  }

  if (esgScore < 55) return 'High'
  if (esgScore < 70) return 'Medium'
  return 'Low'
}

export default function useDashboardData(user) {
  const [companies, setCompanies] = useState([])
  const [cycles, setCycles] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const lastLiveRefreshRef = useRef(0)
  const liveUpdates = useOptionalLiveUpdates()

  const dashboardPath = useMemo(() => getDashboardPath(user), [user])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const headers = {
        'x-user-role': user?.role || '',
        'x-user-email': user?.email || '',
      }
      const cyclesPromise = fetch(`${API_BASE_URL}/cycles`, { headers })
        .then(async (response) => {
          if (!response.ok) return []
          const cycleData = await response.json()
          return Array.isArray(cycleData) ? cycleData : []
        })
        .catch(() => [])

      const dashboardResponse = await fetch(`${API_BASE_URL}${dashboardPath}`, {
        headers,
      })
      if (!dashboardResponse.ok) {
        throw new Error('Failed to load dashboard data from backend.')
      }

      const dashboardData = await dashboardResponse.json()
      if (Array.isArray(dashboardData)) {
        setCompanies(dashboardData)
        setSummary(null)
      } else if (dashboardData && Array.isArray(dashboardData.companies)) {
        setCompanies(dashboardData.companies)
        setSummary(dashboardData)
      } else if (dashboardData && typeof dashboardData === 'object') {
        setCompanies([])
        setSummary(dashboardData)
      } else {
        setCompanies([])
        setSummary(null)
      }

      setLoading(false)
      const cycleData = await cyclesPromise
      setCycles(cycleData)
    } catch (requestError) {
      setCompanies([])
      setCycles([])
      setSummary(null)
      setError(requestError.message || 'Unable to fetch dashboard data.')
      setLoading(false)
    }
  }, [dashboardPath, user?.email, user?.role])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    const nextEvent = liveUpdates?.lastEvent
    if (!nextEvent || !user) return
    const eventType = String(nextEvent?.event_type || '').trim().toLowerCase()
    if (!LIVE_REFRESH_EVENT_TYPES.has(eventType)) return
    const now = Date.now()
    if (now - lastLiveRefreshRef.current < 1200) return
    lastLiveRefreshRef.current = now
    refresh()
  }, [liveUpdates?.lastEvent, refresh, user])

  return {
    companies,
    cycles,
    summary,
    loading,
    error,
    refresh,
  }
}
