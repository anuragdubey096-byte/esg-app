import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

export default function useGlobalSearch({ user, minChars = 2 }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const trimmed = query.trim()
    if (trimmed.length < minChars) {
      setResults([])
      setLoading(false)
      setError('')
      return
    }

    let cancelled = false
    const timeoutId = setTimeout(async () => {
      setLoading(true)
      setError('')
      try {
        const encoded = encodeURIComponent(trimmed)
        const response = await fetch(`${BACKEND_URL}/search/global?q=${encoded}`, {
          headers: {
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          },
        })

        if (!response.ok) {
          const payload = await response.json().catch(() => ({}))
          throw new Error(payload.detail || `Global search failed (${response.status})`)
        }

        const payload = await response.json()
        if (!cancelled) {
          setResults(Array.isArray(payload.results) ? payload.results : [])
        }
      } catch (requestError) {
        if (!cancelled) {
          setResults([])
          setError(requestError.message || 'Unable to search right now.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, 220)

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
  }, [minChars, query, user?.email, user?.role])

  return {
    query,
    setQuery,
    results,
    loading,
    error,
  }
}
