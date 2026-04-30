import { useCallback, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

export default function useNewsletterPreview({ user, audience = 'investor', tone = 'board-ready' }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const query = new URLSearchParams({ audience, tone })
      const response = await fetch(`${BACKEND_URL}/newsletter/generate?${query.toString()}`, {
        method: 'POST',
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Newsletter request failed (${response.status})`)
      }
      const payload = await response.json()
      setData(payload)
    } catch (requestError) {
      setData(null)
      setError(requestError.message || 'Unable to generate newsletter.')
    } finally {
      setLoading(false)
    }
  }, [audience, tone, user?.email, user?.role])

  return {
    data,
    loading,
    error,
    generate,
  }
}

