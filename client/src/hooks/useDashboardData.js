import { useCallback, useEffect, useMemo, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

const STATUS_TO_UI = {
  'not started': 'Not Started',
  'in progress': 'In Progress',
  submitted: 'Submitted',
  'under review': 'Under Review',
  approved: 'Approved',
  rejected: 'Rejected',
  'resubmission requested': 'Resubmission Requested',
}

function toTitleCase(value) {
  return value
    .split(' ')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function getDashboardPath(user) {
  if (!user) return '/dashboard/manager'
  if (user.role === 'company') return `/dashboard/company/${user.id}`
  return `/dashboard/${user.role}`
}

export function normalizeStatus(status) {
  const normalized = String(status || '').trim().toLowerCase()
  if (!normalized) return 'Not Started'
  return STATUS_TO_UI[normalized] || toTitleCase(normalized)
}

function toYear(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null
  if (numeric <= 0) return null
  return numeric
}

export function getSubmissionReportingYear(submission) {
  if (!submission) return null
  const payload = parseSubmissionPayload(submission)
  const payloadYear = toYear(payload?.reporting_year)
  if (payloadYear) return payloadYear
  const cycleYear = toYear(submission?.cycle?.cycle_year)
  if (cycleYear) return cycleYear
  return null
}

export function getSortedSubmissions(company) {
  if (!Array.isArray(company?.submissions) || !company.submissions.length) return []
  return [...company.submissions].sort((left, right) => {
    const yearLeft = getSubmissionReportingYear(left) || 0
    const yearRight = getSubmissionReportingYear(right) || 0
    if (yearLeft !== yearRight) return yearLeft - yearRight
    return Number(left?.id || 0) - Number(right?.id || 0)
  })
}

export function getLatestSubmission(company) {
  const sorted = getSortedSubmissions(company)
  if (!sorted.length) return null
  return sorted[sorted.length - 1]
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
  if (status === 'Rejected') return 100
  if (status === 'Under Review') return 84
  if (status === 'Submitted') return 72
  if (status === 'Resubmission Requested') return 58
  if (status === 'In Progress') return 45
  return 8
}

function metricNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function metricYes(value) {
  return String(value || '').trim().toLowerCase() === 'yes'
}

function clampScore(value) {
  return Math.max(0, Math.min(100, value))
}

export function calculateESGPillarScores(payload) {
  if (!payload || typeof payload !== 'object') return null
  const scope1 = metricNumber(payload.scope_1_emissions)
  const scope2 = metricNumber(payload.scope_2_location_based)
  const scope3 = metricNumber(payload.scope_3_emissions)
  const energy = metricNumber(payload.total_energy_consumption)
  const renewable = metricNumber(payload.renewable_energy_consumption)
  const renewableRatio = energy > 0 ? renewable / energy : 0
  const femaleRepresentation = metricNumber(payload.female_representation_percent)
  const trifr = metricNumber(payload.trifr)
  const turnover = metricNumber(payload.employee_turnover_rate)
  const independentBoard = metricNumber(payload.independent_board_members_percent)
  const corruptionCases = metricNumber(payload.confirmed_cases_of_corruption)

  const environmental = clampScore(
    30
    + Math.max(0, 35 - ((scope1 + scope2 + scope3) / 60))
    + Math.min(20, metricNumber(payload.reduction_target_percent) * 0.25)
    + Math.min(15, renewableRatio * 100 * 0.2)
  )
  const social = clampScore(
    25
    + Math.min(25, femaleRepresentation * 0.35)
    + Math.max(0, 20 - trifr * 2.5)
    + Math.max(0, 15 - turnover * 0.3)
    + (metricYes(payload.whs_policy_in_place) ? 15 : 0)
  )
  const governance = clampScore(
    (metricYes(payload.esg_policy_in_place) ? 20 : 0)
    + (metricYes(payload.board_level_esg_oversight) ? 20 : 0)
    + (metricYes(payload.cybersecurity_policy_in_place) ? 20 : 0)
    + (metricYes(payload.anti_bribery_corruption_policy) ? 20 : 0)
    + Math.min(20, independentBoard * 0.4)
    - Math.min(10, corruptionCases * 2)
  )
  const composite = clampScore((0.45 * environmental) + (0.30 * social) + (0.25 * governance))
  return { environmental, social, governance, composite }
}

export function calculateESGScore(_status, payload) {
  const scores = calculateESGPillarScores(payload)
  return scores ? Number(scores.composite.toFixed(1)) : null
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
  if (status === 'Resubmission Requested') return 'High'

  const deadlineDate = parseDateString(deadline)
  if (deadlineDate) {
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const diff = Math.ceil((deadlineDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
    if (diff < 0) return 'High'
    if (diff <= 7) return status === 'Not Started' ? 'High' : 'Medium'
  }

  if (esgScore === null || esgScore === undefined || !Number.isFinite(Number(esgScore))) return 'Unknown'
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
      const headers = {
        'x-user-role': user?.role || '',
        'x-user-email': user?.email || '',
      }
      const shouldLoadCycles = ['manager', 'company'].includes(String(user?.role || '').toLowerCase())
      const controller = new AbortController()
      const timeoutId = window.setTimeout(() => controller.abort(), 25000)
      const [dashboardResponse, cycleResponse] = await Promise.all([
        fetch(`${BACKEND_URL}${dashboardPath}`, {
          headers,
          signal: controller.signal,
        }),
        shouldLoadCycles
          ? fetch(`${BACKEND_URL}/cycles`, { headers, signal: controller.signal }).catch(() => null)
          : Promise.resolve(null),
      ]).finally(() => window.clearTimeout(timeoutId))
      if (!dashboardResponse.ok) {
        throw new Error('Failed to load dashboard data from backend.')
      }

      const dashboardData = await dashboardResponse.json()
      if (Array.isArray(dashboardData)) {
        setCompanies(dashboardData)
        setSummary(null)
      } else if (dashboardData && Array.isArray(dashboardData.companies)) {
        setCompanies(dashboardData.companies)
        setSummary(dashboardData.summary || dashboardData)
      } else if (dashboardData && typeof dashboardData === 'object') {
        setCompanies([])
        setSummary(dashboardData)
      } else {
        setCompanies([])
        setSummary(null)
      }

      if (shouldLoadCycles) {
        try {
          if (cycleResponse?.ok) {
            const cycleData = await cycleResponse.json()
            setCycles(Array.isArray(cycleData) ? cycleData : [])
          } else {
            setCycles([])
          }
        } catch {
          setCycles([])
        }
      } else {
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
  }, [dashboardPath, user?.email, user?.role])

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
