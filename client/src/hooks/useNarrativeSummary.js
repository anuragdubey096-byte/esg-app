import { useCallback, useEffect, useMemo, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

export default function useNarrativeSummary({
  user,
  audience = 'lp',
  tone = 'board-ready',
  companyId = null,
  enabled = true,
}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const query = useMemo(() => {
    const params = new URLSearchParams()
    params.set('audience', audience)
    params.set('tone', tone)
    if (companyId != null) params.set('company_id', String(companyId))
    return params.toString()
  }, [audience, companyId, tone])

  const refresh = useCallback(async () => {
    if (!enabled) return

    setLoading(true)
    setError('')

    try {
      const response = await fetch(`${BACKEND_URL}/narrative/summary?${query}`, {
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Narrative request failed (${response.status})`)
      }
      const payload = await response.json()
      setData(payload)
    } catch (requestError) {
      setData(null)
      setError(requestError.message || 'Unable to load narrative summary.')
    } finally {
      setLoading(false)
    }
  }, [enabled, query, user?.email, user?.role])

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    data,
    loading,
    error,
    refresh,
  }
}
