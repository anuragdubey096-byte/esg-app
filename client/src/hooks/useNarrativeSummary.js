import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../lib/api'
import { DEFAULT_REPORT_VIEW } from '../lib/portalOptions'

export default function useNarrativeSummary({ user, audience, companyId, tone = DEFAULT_REPORT_VIEW.narrativeTone, enabled = true } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshToken, setRefreshToken] = useState(0)

  useEffect(() => {
    let active = true

    const fetchNarrative = async () => {
      if (!enabled || !user?.role || !audience) {
        setData(null)
        setError('')
        setLoading(false)
        return
      }

      setLoading(true)
      setError('')
      try {
        const params = new URLSearchParams({ audience, tone })
        if (companyId !== undefined && companyId !== null) {
          params.set('company_id', String(companyId))
        }
    const response = await fetch(`${API_BASE_URL}/narrative/summary?${params.toString()}`, {
          headers: {
            'X-User-Role': user?.role || '',
            'X-User-Email': user?.email || '',
            'Content-Type': 'application/json',
          },
        })

        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(payload.detail || `Failed to load narrative summary (${response.status})`)
        }

        if (active) {
          setData(payload)
        }
      } catch (err) {
        if (active) {
          setError(err.message || 'Unable to load narrative summary.')
          setData(null)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    fetchNarrative()
    return () => {
      active = false
    }
  }, [audience, companyId, enabled, refreshToken, tone, user?.email, user?.role])

  const refresh = () => setRefreshToken((current) => current + 1)

  const generate = async ({ audience: nextAudience = audience, companyId: nextCompanyId = companyId, tone: nextTone = tone, forceRefresh = false } = {}) => {
      const response = await fetch(`${API_BASE_URL}/narrative/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Role': user?.role || '',
        'X-User-Email': user?.email || '',
      },
      body: JSON.stringify({
        audience: nextAudience,
        company_id: nextCompanyId,
        tone: nextTone,
        force_refresh: forceRefresh,
      }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.detail || `Failed to generate narrative summary (${response.status})`)
    }
    setData(payload)
    return payload
  }

  const update = async (narrativeId, patch) => {
      const response = await fetch(`${API_BASE_URL}/narrative/${narrativeId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Role': user?.role || '',
        'X-User-Email': user?.email || '',
      },
      body: JSON.stringify(patch),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.detail || `Failed to update narrative summary (${response.status})`)
    }
    setData(payload)
    return payload
  }

  const approve = async (narrativeId, approved = true) => {
      const response = await fetch(`${API_BASE_URL}/narrative/${narrativeId}/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Role': user?.role || '',
        'X-User-Email': user?.email || '',
      },
      body: JSON.stringify({ approved }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.detail || `Failed to approve narrative summary (${response.status})`)
    }
    setData(payload)
    return payload
  }

  const exportNarrative = async (narrativeId) => {
      const response = await fetch(`${API_BASE_URL}/narrative/${narrativeId}/export`, {
      headers: {
        'X-User-Role': user?.role || '',
        'X-User-Email': user?.email || '',
      },
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.detail || `Failed to export narrative summary (${response.status})`)
    }
    return payload
  }

  return { data, loading, error, refresh, generate, update, approve, exportNarrative }
}
