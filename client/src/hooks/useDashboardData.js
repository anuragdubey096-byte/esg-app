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

export function getPreferredCycle(cycles) {
  if (!cycles?.length) return null
  const activeCycle = cycles.find((cycle) => String(cycle.status).toLowerCase() === 'active')
  return activeCycle || cycles[0]
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
