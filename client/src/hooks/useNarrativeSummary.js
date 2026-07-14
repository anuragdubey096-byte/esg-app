import { useCallback, useEffect, useMemo, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL
const NARRATIVE_TIMEOUT_MS = 10000

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
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), NARRATIVE_TIMEOUT_MS)

    try {
      const response = await fetch(`${BACKEND_URL}/narrative/summary?${query}`, {
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
        signal: controller.signal,
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Narrative request failed (${response.status})`)
      }
      const payload = await response.json()
      setData(payload)
    } catch (requestError) {
      setError(
        requestError?.name === 'AbortError'
          ? 'Narrative generation timed out. Dashboard data is still available.'
          : requestError.message || 'Unable to load narrative summary.',
      )
    } finally {
      window.clearTimeout(timeoutId)
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
