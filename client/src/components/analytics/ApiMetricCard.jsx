import { useEffect, useMemo, useState } from 'react'
import { API_BASE_URL } from '../../lib/api'

const RESPONSE_CACHE = new Map()

function toNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function getByPath(source, path) {
  if (!path) return source
  return String(path)
    .split('.')
    .reduce((acc, part) => (acc && acc[part] !== undefined ? acc[part] : undefined), source)
}

function getHeaders(user) {
  return {
    'x-user-role': user?.role || '',
    'x-user-email': user?.email || '',
  }
}

async function fetchEndpoint(endpoint, user) {
  const key = `${user?.role || ''}|${user?.email || ''}|${endpoint}`
  if (!RESPONSE_CACHE.has(key)) {
    RESPONSE_CACHE.set(
      key,
      fetch(`${API_BASE_URL}${endpoint}`, {
        headers: getHeaders(user),
      }).then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        return response.json()
      })
    )
  }
  return RESPONSE_CACHE.get(key)
}

function formatNumber(value, decimals = 1) {
  const numeric = toNumber(value)
  if (numeric === null) return null
  return numeric.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function formatValue(value, valueType, decimals) {
  if (value === null || value === undefined || value === '') return null

  if (valueType === 'text' || valueType === 'status') {
    return String(value)
  }

  const numeric = toNumber(value)
  if (numeric === null) return null

  if (valueType === 'integer') {
    return numeric.toLocaleString(undefined, { maximumFractionDigits: 0 })
  }

  if (valueType === 'percent') {
    const formatted = formatNumber(numeric, decimals)
    return formatted === null ? null : `${formatted}%`
  }

  return formatNumber(numeric, decimals)
}

function normalizeTrend(trend) {
  if (!trend || typeof trend !== 'object') return null
  const direction = String(trend.direction || 'neutral').toLowerCase()
  const percent = toNumber(trend.percent)
  const label = trend.label ? String(trend.label) : ''
  if (!['up', 'down', 'neutral'].includes(direction)) {
    return null
  }
  return { direction, percent, label }
}

export default function ApiMetricCard({
  user,
  title,
  endpoint,
  valuePath,
  selectValue,
  selectTrend,
  unit,
  valueType = 'number',
  decimals = 1,
  emptyLabel = 'No API field available',
}) {
  const [loading, setLoading] = useState(Boolean(endpoint))
  const [error, setError] = useState('')
  const [payload, setPayload] = useState(null)
  const [missingEndpoint, setMissingEndpoint] = useState(false)

  useEffect(() => {
    let alive = true
    if (!endpoint) {
      setMissingEndpoint(true)
      setLoading(false)
      setError('')
      setPayload(null)
      return () => {
        alive = false
      }
    }

    setMissingEndpoint(false)
    setLoading(true)
    setError('')

    fetchEndpoint(endpoint, user)
      .then((json) => {
        if (!alive) return
        setPayload(json)
      })
      .catch((requestError) => {
        if (!alive) return
        setError(requestError?.message || 'Failed to load')
      })
      .finally(() => {
        if (!alive) return
        setLoading(false)
      })

    return () => {
      alive = false
    }
  }, [endpoint, user?.email, user?.role])

  const metricValue = useMemo(() => {
    if (!payload) return null
    if (typeof selectValue === 'function') return selectValue(payload)
    if (valuePath) return getByPath(payload, valuePath)
    return null
  }, [payload, selectValue, valuePath])

  const trend = useMemo(() => {
    if (!payload || typeof selectTrend !== 'function') return null
    return normalizeTrend(selectTrend(payload))
  }, [payload, selectTrend])

  const displayValue = useMemo(() => {
    if (loading) return '--'
    if (error || missingEndpoint) return 'No data'
    const formatted = formatValue(metricValue, valueType, decimals)
    if (!formatted) return 'No data'
    if (!unit || valueType === 'percent' || valueType === 'status') return formatted
    return `${formatted} ${unit}`
  }, [decimals, error, loading, metricValue, missingEndpoint, unit, valueType])

  let metaText = ''
  let metaClass = 'neutral'

  if (loading) {
    metaText = 'Loading...'
    metaClass = 'neutral'
  } else if (error) {
    metaText = 'Failed to load this metric'
    metaClass = 'negative'
  } else if (missingEndpoint) {
    metaText = 'Endpoint unavailable'
    metaClass = 'neutral'
  } else if (displayValue === 'No data') {
    metaText = emptyLabel
    metaClass = 'neutral'
  } else if (trend) {
    const symbol = trend.direction === 'up' ? 'UP' : trend.direction === 'down' ? 'DOWN' : 'FLAT'
    const trendValue = trend.percent === null ? '' : ` ${Math.abs(trend.percent).toFixed(1)}%`
    const trendLabel = trend.label ? ` ${trend.label}` : ''
    metaText = `${symbol}${trendValue}${trendLabel}`.trim()
    metaClass = trend.direction === 'up' ? 'positive' : trend.direction === 'down' ? 'negative' : 'neutral'
  }

  return (
    <article className="kpi-card">
      <p className="kpi-title">{title}</p>
      <p className="kpi-value">{displayValue}</p>
      <p className={`kpi-trend ${metaClass}`}>{metaText}</p>
    </article>
  )
}
