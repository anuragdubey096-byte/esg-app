import { useCallback, useMemo, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

function authHeaders(user) {
  return {
    'x-user-role': user?.role || '',
    'x-user-email': user?.email || '',
    'Content-Type': 'application/json',
  }
}

export default function useCollaborationWorkspace({ user, companyId = null }) {
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeSection, setActiveSection] = useState('Environmental')

  const cycleId = useMemo(() => {
    const value = payload?.cycle_id
    return value == null ? null : Number(value)
  }, [payload?.cycle_id])

  const load = useCallback(async (targetCycleId, section = activeSection) => {
    if (!targetCycleId) return null
    setLoading(true)
    setError('')
    try {
      const query = new URLSearchParams()
      query.set('section', section)
      if (companyId != null) query.set('company_id', String(companyId))
      const response = await fetch(`${BACKEND_URL}/company/submission/${targetCycleId}?${query.toString()}`, {
        headers: authHeaders(user),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || `Collaboration load failed (${response.status})`)
      }
      const json = await response.json()
      setPayload(json)
      setActiveSection(section)
      return json
    } catch (requestError) {
      setError(requestError.message || 'Unable to load collaboration workspace.')
      return null
    } finally {
      setLoading(false)
    }
  }, [activeSection, companyId, user])

  const claim = useCallback(async (targetCycleId, section) => {
    if (!targetCycleId) return null
    setLoading(true)
    setError('')
    try {
      const query = companyId != null ? `?company_id=${companyId}` : ''
      const response = await fetch(`${BACKEND_URL}/company/submission/${targetCycleId}/collaboration/claim${query}`, {
        method: 'POST',
        headers: authHeaders(user),
        body: JSON.stringify({ section, lock_mode: 'soft' }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || `Claim failed (${response.status})`)
      }
      return await response.json()
    } catch (requestError) {
      setError(requestError.message || 'Unable to claim section.')
      return null
    } finally {
      setLoading(false)
    }
  }, [companyId, user])

  const release = useCallback(async (targetCycleId, section) => {
    if (!targetCycleId) return null
    setLoading(true)
    setError('')
    try {
      const query = companyId != null ? `?company_id=${companyId}` : ''
      const response = await fetch(`${BACKEND_URL}/company/submission/${targetCycleId}/collaboration/release${query}`, {
        method: 'POST',
        headers: authHeaders(user),
        body: JSON.stringify({ section }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || `Release failed (${response.status})`)
      }
      return await response.json()
    } catch (requestError) {
      setError(requestError.message || 'Unable to release section.')
      return null
    } finally {
      setLoading(false)
    }
  }, [companyId, user])

  const heartbeat = useCallback(async (targetCycleId, section) => {
    if (!targetCycleId) return null
    try {
      const query = companyId != null ? `?company_id=${companyId}` : ''
      const response = await fetch(`${BACKEND_URL}/company/submission/${targetCycleId}/collaboration/heartbeat${query}`, {
        method: 'POST',
        headers: authHeaders(user),
        body: JSON.stringify({ section }),
      })
      if (!response.ok) return null
      return await response.json()
    } catch (_) {
      return null
    }
  }, [companyId, user])

  const updateField = useCallback(async (targetCycleId, fieldKey, value, section = activeSection) => {
    if (!targetCycleId || !fieldKey) return null
    setLoading(true)
    setError('')
    try {
      const query = companyId != null ? `?company_id=${companyId}` : ''
      const response = await fetch(`${BACKEND_URL}/company/submission/${targetCycleId}${query}`, {
        method: 'POST',
        headers: authHeaders(user),
        body: JSON.stringify({ field_key: fieldKey, value, section }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || `Field update failed (${response.status})`)
      }
      await load(targetCycleId, section)
      return await response.json()
    } catch (requestError) {
      setError(requestError.message || 'Unable to update field.')
      return null
    } finally {
      setLoading(false)
    }
  }, [activeSection, companyId, load, user])

  return {
    payload,
    cycleId,
    activeSection,
    setActiveSection,
    loading,
    error,
    load,
    claim,
    release,
    heartbeat,
    updateField,
  }
}
