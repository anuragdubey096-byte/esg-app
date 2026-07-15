import { useCallback, useEffect, useMemo, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL
const DASHBOARD_TIMEOUT_MS = 12000
const CYCLES_TIMEOUT_MS = 8000
const CACHE_MAX_AGE_MS = 15 * 60 * 1000
const CACHE_PREFIX = 'esg-dashboard-cache:v1'

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

export function getAvailableReportingYears(submissions = []) {
  return [...new Set(submissions.map(getSubmissionReportingYear).filter(Boolean))]
    .sort((left, right) => right - left)
}

export function getSubmissionForReportingYear(submissions = [], selectedYear = 'Latest') {
  const sorted = getSortedSubmissions({ submissions })
  if (!sorted.length) return null
  if (selectedYear === 'Latest') return sorted[sorted.length - 1]

  const targetYear = toYear(selectedYear)
  if (!targetYear) return null
  return [...sorted].reverse().find(
    (submission) => getSubmissionReportingYear(submission) === targetYear,
  ) || null
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

function getCacheKey(user, dashboardPath) {
  const role = String(user?.role || 'anonymous').toLowerCase()
  const email = String(user?.email || 'unknown').toLowerCase()
  return `${CACHE_PREFIX}:${role}:${email}:${dashboardPath}`
}

function readCache(cacheKey) {
  if (typeof window === 'undefined') return {}
  try {
    const parsed = JSON.parse(window.sessionStorage.getItem(cacheKey) || '{}')
    const now = Date.now()
    return Object.fromEntries(
      Object.entries(parsed).filter(([, entry]) => (
        entry && Number(entry.updatedAt) > 0 && now - Number(entry.updatedAt) <= CACHE_MAX_AGE_MS
      )),
    )
  } catch {
    return {}
  }
}

function updateCache(cacheKey, section, value) {
  if (typeof window === 'undefined') return
  try {
    const current = readCache(cacheKey)
    window.sessionStorage.setItem(cacheKey, JSON.stringify({
      ...current,
      [section]: { value, updatedAt: Date.now() },
    }))
  } catch {
    // Dashboard rendering must never depend on browser storage availability.
  }
}

function normalizeDashboardPayload(payload) {
  if (Array.isArray(payload)) return { companies: payload, summary: null }
  if (payload && Array.isArray(payload.companies)) {
    return { companies: payload.companies, summary: payload.summary || payload }
  }
  if (payload && typeof payload === 'object') return { companies: [], summary: payload }
  return { companies: [], summary: null }
}

function requestErrorMessage(error, sectionLabel) {
  if (error?.name === 'AbortError') return `${sectionLabel} timed out. Retry this section.`
  return error?.message || `Unable to load ${sectionLabel.toLowerCase()}.`
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
  const dashboardPath = useMemo(() => getDashboardPath(user), [user?.id, user?.role])
  const cacheKey = useMemo(
    () => getCacheKey(user, dashboardPath),
    [dashboardPath, user?.email, user?.role],
  )
  const initialCache = useMemo(() => readCache(cacheKey), [cacheKey])
  const initialDashboard = normalizeDashboardPayload(initialCache.dashboard?.value)
  const [companies, setCompanies] = useState(initialDashboard.companies)
  const [cycles, setCycles] = useState(() => initialCache.cycles?.value || [])
  const [summary, setSummary] = useState(initialDashboard.summary)
  const [hasDashboardData, setHasDashboardData] = useState(Boolean(initialCache.dashboard))
  const [sections, setSections] = useState({
    dashboard: {
      loading: !initialCache.dashboard,
      error: '',
      fromCache: Boolean(initialCache.dashboard),
      lastUpdated: initialCache.dashboard?.updatedAt || null,
    },
    cycles: {
      loading: false,
      error: '',
      fromCache: Boolean(initialCache.cycles),
      lastUpdated: initialCache.cycles?.updatedAt || null,
    },
  })

  const requestHeaders = useMemo(() => ({
    'x-user-role': user?.role || '',
    'x-user-email': user?.email || '',
  }), [user?.email, user?.role])

  const loadDashboard = useCallback(async () => {
    setSections((current) => ({
      ...current,
      dashboard: { ...current.dashboard, loading: true, error: '' },
    }))
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), DASHBOARD_TIMEOUT_MS)

    try {
      const response = await fetch(`${BACKEND_URL}${dashboardPath}`, {
        headers: requestHeaders,
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`Dashboard request failed (${response.status}).`)
      const payload = await response.json()
      const normalized = normalizeDashboardPayload(payload)
      setCompanies(normalized.companies)
      setSummary(normalized.summary)
      setHasDashboardData(true)
      updateCache(cacheKey, 'dashboard', payload)
      setSections((current) => ({
        ...current,
        dashboard: {
          loading: false,
          error: '',
          fromCache: false,
          lastUpdated: Date.now(),
        },
      }))
      return payload
    } catch (requestError) {
      const message = requestErrorMessage(requestError, 'Dashboard data')
      setSections((current) => ({
        ...current,
        dashboard: { ...current.dashboard, loading: false, error: message },
      }))
      throw requestError
    } finally {
      window.clearTimeout(timeoutId)
    }
  }, [cacheKey, dashboardPath, requestHeaders])

  const loadCycles = useCallback(async () => {
    const shouldLoadCycles = ['manager', 'company'].includes(String(user?.role || '').toLowerCase())
    if (!shouldLoadCycles) {
      setCycles([])
      setSections((current) => ({
        ...current,
        cycles: { loading: false, error: '', fromCache: false, lastUpdated: null },
      }))
      return []
    }

    setSections((current) => ({
      ...current,
      cycles: { ...current.cycles, loading: true, error: '' },
    }))
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), CYCLES_TIMEOUT_MS)

    try {
      const response = await fetch(`${BACKEND_URL}/cycles`, {
        headers: requestHeaders,
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`Reporting cycles request failed (${response.status}).`)
      const payload = await response.json()
      const nextCycles = Array.isArray(payload) ? payload : []
      setCycles(nextCycles)
      updateCache(cacheKey, 'cycles', nextCycles)
      setSections((current) => ({
        ...current,
        cycles: {
          loading: false,
          error: '',
          fromCache: false,
          lastUpdated: Date.now(),
        },
      }))
      return nextCycles
    } catch (requestError) {
      const message = requestErrorMessage(requestError, 'Reporting cycles')
      setSections((current) => ({
        ...current,
        cycles: { ...current.cycles, loading: false, error: message },
      }))
      throw requestError
    } finally {
      window.clearTimeout(timeoutId)
    }
  }, [cacheKey, requestHeaders, user?.role])

  const refresh = useCallback(async (section = 'all') => {
    if (section === 'dashboard') return loadDashboard().catch(() => null)
    if (section === 'cycles') return loadCycles().catch(() => null)
    return Promise.allSettled([loadDashboard(), loadCycles()])
  }, [loadCycles, loadDashboard])

  useEffect(() => {
    const cached = readCache(cacheKey)
    if (cached.dashboard) {
      const normalized = normalizeDashboardPayload(cached.dashboard.value)
      setCompanies(normalized.companies)
      setSummary(normalized.summary)
      setHasDashboardData(true)
    } else {
      setCompanies([])
      setSummary(null)
      setHasDashboardData(false)
    }
    setCycles(cached.cycles?.value || [])
    setSections({
      dashboard: {
        loading: !cached.dashboard,
        error: '',
        fromCache: Boolean(cached.dashboard),
        lastUpdated: cached.dashboard?.updatedAt || null,
      },
      cycles: {
        loading: false,
        error: '',
        fromCache: Boolean(cached.cycles),
        lastUpdated: cached.cycles?.updatedAt || null,
      },
    })
    refresh()
  }, [cacheKey, refresh])

  const loading = sections.dashboard.loading && !hasDashboardData
  const error = !hasDashboardData ? sections.dashboard.error : ''

  return {
    companies,
    cycles,
    summary,
    loading,
    error,
    refresh,
    retrySection: refresh,
    sections,
    isRefreshing: sections.dashboard.loading && hasDashboardData,
  }
}
