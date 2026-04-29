import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

export default function useExternalContextFeed({ user, sector, companyId, enabled = true, limit = 6 } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshToken, setRefreshToken] = useState(0)

  useEffect(() => {
    let active = true

    const loadFeed = async () => {
      if (!enabled || !user?.role) {
        setData(null)
        setError('')
        setLoading(false)
        return
      }

      setLoading(true)
      setError('')
      try {
        const params = new URLSearchParams({ limit: String(limit) })
        if (sector) params.set('sector', String(sector))
        if (companyId !== undefined && companyId !== null) {
          params.set('company_id', String(companyId))
        }
        const response = await fetch(`${API_BASE_URL}/external-context/feed?${params.toString()}`, {
          headers: {
            'X-User-Role': user?.role || '',
            'X-User-Email': user?.email || '',
          },
        })
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(payload.detail || `Failed to load external context feed (${response.status})`)
        }
        if (active) {
          setData(payload)
        }
      } catch (err) {
        if (active) {
          setError(err.message || 'Unable to load external context feed.')
          setData(null)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadFeed()
    return () => {
      active = false
    }
  }, [companyId, enabled, limit, refreshToken, sector, user?.email, user?.role])

  const refresh = () => setRefreshToken((current) => current + 1)

  return { data, loading, error, refresh }
}
