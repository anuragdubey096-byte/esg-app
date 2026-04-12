import { useCallback, useEffect, useMemo, useState } from 'react'

const BACKEND_URL = 'http://127.0.0.1:8000'

const STATUS_TO_UI = {
  'not started': 'Not Started',
  'in progress': 'In Progress',
  submitted: 'Submitted',
  'under review': 'Submitted',
  approved: 'Approved',
  rejected: 'Rejected',
  'resubmission requested': 'In Progress',
}

function toTitleCase(value) {
  return value
    .split(' ')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function getDashboardPath(user) {
  if (!user) return '/dashboard/admin'
  if (user.role === 'company') return `/dashboard/company/${user.id}`
  return `/dashboard/${user.role}`
}

export function normalizeStatus(status) {
  const normalized = String(status || '').trim().toLowerCase()
  if (!normalized) return 'Not Started'
  return STATUS_TO_UI[normalized] || toTitleCase(normalized)
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
  if (status === 'Submitted') return 85
  if (status === 'Rejected') return 72
  if (status === 'In Progress') return 46
  return 8
}

export function calculateESGScore(status, payload) {
  const baseline = {
    'Not Started': 34,
    'In Progress': 52,
    Submitted: 68,
    Approved: 82,
    Rejected: 48,
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
  if (status === 'Rejected') return 'High'

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

  const dashboardPath = useMemo(() => getDashboardPath(user), [user])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const dashboardResponse = await fetch(`${BACKEND_URL}${dashboardPath}`, {
        headers: { 'x-user-role': user?.role || '' }
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
      } else {
        setCompanies([])
        setSummary(null)
      }

      try {
        const cycleResponse = await fetch(`${BACKEND_URL}/cycles`, {
          headers: { 'x-user-role': user?.role || '' }
        })
        if (cycleResponse.ok) {
          const cycleData = await cycleResponse.json()
          setCycles(Array.isArray(cycleData) ? cycleData : [])
        } else {
          setCycles([])
        }
      } catch {
        setCycles([])
      }
    } catch (requestError) {
      setCompanies([])
      setCycles([])
      setSummary(null)
      setError(requestError.message || 'Unable to fetch dashboard data.')
    } finally {
      setLoading(false)
    }
  }, [dashboardPath])

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    companies,
    cycles,
    summary,
    loading,
    error,
    refresh,
  }
}
