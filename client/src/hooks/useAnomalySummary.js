import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

export default function useAnomalySummary({ user, companyId, enabled = true, companyScoped = false } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshToken, setRefreshToken] = useState(0)

  useEffect(() => {
    let active = true

    const loadSummary = async () => {
      if (!enabled || !user?.role) {
        setData(null)
        setError('')
        setLoading(false)
        return
      }

      setLoading(true)
      setError('')
      try {
        const path = companyScoped
          ? '/company/anomalies'
          : companyId !== undefined && companyId !== null
            ? `/anomalies/summary?company_id=${companyId}`
            : '/anomalies/summary'
        const response = await fetch(`${API_BASE_URL}${path}`, {
          headers: {
            'X-User-Role': user?.role || '',
            'X-User-Email': user?.email || '',
          },
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(payload.detail || `Failed to load anomaly summary (${response.status})`)
        }
        if (active) {
          setData(payload)
        }
      } catch (err) {
        if (active) {
          setError(err.message || 'Unable to load anomaly summary.')
          setData(null)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadSummary()
    return () => {
      active = false
    }
  }, [companyId, companyScoped, enabled, refreshToken, user?.email, user?.role])

  const refresh = () => setRefreshToken((current) => current + 1)

  return { data, loading, error, refresh }
}
