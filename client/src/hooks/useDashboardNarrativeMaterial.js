import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

export default function useDashboardNarrativeMaterial({
  user,
  materialType,
  enabled = true,
  forceRefresh = false,
} = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshToken, setRefreshToken] = useState(0)

  useEffect(() => {
    let active = true

    const loadMaterial = async () => {
      if (!enabled || !user?.role || !materialType) {
        setData(null)
        setError('')
        setLoading(false)
        return
      }

      setLoading(true)
      setError('')
      try {
        const params = new URLSearchParams({
          material_type: materialType,
          force_refresh: forceRefresh ? 'true' : 'false',
        })
        const response = await fetch(`${API_BASE_URL}/dashboard/material?${params.toString()}`, {
          headers: {
            'X-User-Role': user?.role || '',
            'X-User-Email': user?.email || '',
          },
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(payload.detail || `Failed to load dashboard material (${response.status})`)
        }
        if (active) {
          setData(payload)
        }
      } catch (err) {
        if (active) {
          setError(err.message || 'Unable to load dashboard material.')
          setData(null)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadMaterial()
    return () => {
      active = false
    }
  }, [enabled, forceRefresh, materialType, refreshToken, user?.email, user?.role])

  const refresh = () => setRefreshToken((current) => current + 1)

  return { data, loading, error, refresh }
}
