import { useCallback, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

function authHeaders(user) {
  return {
    'x-user-role': user?.role || '',
    'x-user-email': user?.email || '',
    'Content-Type': 'application/json',
  }
}

export default function useNarrativeLifecycle({ user }) {
  const [record, setRecord] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = useCallback(async ({ audience = 'board', tone = 'board-ready', companyId = null } = {}) => {
    setLoading(true)
    setError('')
    try {
      const query = new URLSearchParams({ audience, tone })
      if (companyId != null) query.set('company_id', String(companyId))
      const response = await fetch(`${BACKEND_URL}/narrative/generate?${query.toString()}`, {
        method: 'POST',
        headers: authHeaders(user),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Narrative generate failed (${response.status})`)
      }
      const payload = await response.json()
      setRecord(payload)
      return payload
    } catch (requestError) {
      setError(requestError.message || 'Unable to generate narrative.')
      return null
    } finally {
      setLoading(false)
    }
  }, [user])

  const fetchById = useCallback(async (narrativeId) => {
    if (!narrativeId) return null
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${BACKEND_URL}/narrative/${narrativeId}`, {
        headers: authHeaders(user),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Narrative fetch failed (${response.status})`)
      }
      const payload = await response.json()
      setRecord(payload)
      return payload
    } catch (requestError) {
      setError(requestError.message || 'Unable to load narrative.')
      return null
    } finally {
      setLoading(false)
    }
  }, [user])

  const update = useCallback(async (narrativeId, updates) => {
    if (!narrativeId) return null
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${BACKEND_URL}/narrative/${narrativeId}`, {
        method: 'PATCH',
        headers: authHeaders(user),
        body: JSON.stringify(updates || {}),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Narrative update failed (${response.status})`)
      }
      const payload = await response.json()
      setRecord(payload)
      return payload
    } catch (requestError) {
      setError(requestError.message || 'Unable to update narrative.')
      return null
    } finally {
      setLoading(false)
    }
  }, [user])

  const approve = useCallback(async (narrativeId) => {
    if (!narrativeId) return null
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${BACKEND_URL}/narrative/${narrativeId}/approve`, {
        method: 'POST',
        headers: authHeaders(user),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Narrative approve failed (${response.status})`)
      }
      const payload = await response.json()
      setRecord(payload)
      return payload
    } catch (requestError) {
      setError(requestError.message || 'Unable to approve narrative.')
      return null
    } finally {
      setLoading(false)
    }
  }, [user])

  const loadHistory = useCallback(async ({ audience = 'lp', companyId = null, limit = 5 } = {}) => {
    setLoading(true)
    setError('')
    try {
      const query = new URLSearchParams({ audience, limit: String(limit) })
      if (companyId != null) query.set('company_id', String(companyId))
      const response = await fetch(`${BACKEND_URL}/narrative/history?${query.toString()}`, {
        headers: authHeaders(user),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Narrative history failed (${response.status})`)
      }
      const payload = await response.json()
      const items = Array.isArray(payload.items) ? payload.items : []
      setHistory(items)
      return items
    } catch (requestError) {
      setHistory([])
      setError(requestError.message || 'Unable to load narrative history.')
      return []
    } finally {
      setLoading(false)
    }
  }, [user])

  return {
    record,
    history,
    loading,
    error,
    generate,
    fetchById,
    update,
    approve,
    loadHistory,
  }
}
