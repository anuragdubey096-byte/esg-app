import { useCallback, useEffect, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

export default function useExternalContextFeed({ user, limit = 10, enabled = true }) {
  const [items, setItems] = useState([])
  const [meta, setMeta] = useState({ generated_at: null, source_count: 0, fallback_used: true })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!enabled || !user) return null
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${BACKEND_URL}/external-context/feed?limit=${encodeURIComponent(limit)}`, {
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `External context request failed (${response.status})`)
      }
      const payload = await response.json()
      setItems(Array.isArray(payload.items) ? payload.items : [])
      setMeta({
        generated_at: payload.generated_at || null,
        source_count: Number(payload.source_count || 0),
        fallback_used: Boolean(payload.fallback_used),
      })
      return payload
    } catch (requestError) {
      setItems([])
      setMeta({ generated_at: null, source_count: 0, fallback_used: true })
      setError(requestError.message || 'Unable to load external ESG feed.')
      return null
    } finally {
      setLoading(false)
    }
  }, [enabled, limit, user])

  useEffect(() => {
    load()
  }, [load])

  return {
    items,
    meta,
    loading,
    error,
    reload: load,
  }
}
