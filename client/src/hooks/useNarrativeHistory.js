import { useCallback, useEffect, useMemo, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

export default function useNarrativeHistory({
  user,
  audience = 'lp',
  companyId = null,
  limit = 5,
  enabled = true,
}) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const query = useMemo(() => {
    const params = new URLSearchParams()
    params.set('audience', audience)
    params.set('limit', String(limit))
    if (companyId != null) params.set('company_id', String(companyId))
    return params.toString()
  }, [audience, companyId, limit])

  const refresh = useCallback(async () => {
    if (!enabled) return
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${BACKEND_URL}/narrative/history?${query}`, {
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Narrative history request failed (${response.status})`)
      }
      const payload = await response.json()
      setItems(Array.isArray(payload.items) ? payload.items : [])
    } catch (requestError) {
      setItems([])
      setError(requestError.message || 'Unable to load narrative history.')
    } finally {
      setLoading(false)
    }
  }, [enabled, query, user?.email, user?.role])

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    items,
    loading,
    error,
    refresh,
  }
}

