import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

export default function useCompanyActiveCycleId(user) {
  const [cycleId, setCycleId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    const fetchActiveCycle = async () => {
      if (user?.role && user.role !== 'company') {
        if (!cancelled) {
          setCycleId(null)
          setError('')
          setLoading(false)
        }
        return
      }

      if (!user?.email) {
        if (!cancelled) {
          setCycleId(null)
          setError('Missing company user context')
          setLoading(false)
        }
        return
      }

      try {
        setLoading(true)
        setError('')
        const response = await fetch(`${API_BASE_URL}/company/dashboard`, {
          headers: {
            'X-User-Role': user?.role || 'company',
            'X-User-Email': user?.email || '',
            'Content-Type': 'application/json',
          },
        })

        if (!response.ok) {
          throw new Error(`Failed to resolve active cycle: ${response.status}`)
        }

        const payload = await response.json()
        const resolvedCycleId = Number(payload?.current_cycle_id || 0)

        if (!cancelled) {
          setCycleId(resolvedCycleId > 0 ? String(resolvedCycleId) : null)
          setError('')
        }
      } catch (err) {
        if (!cancelled) {
          setCycleId(null)
          setError(err instanceof Error ? err.message : 'Unable to resolve active cycle')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    fetchActiveCycle()

    return () => {
      cancelled = true
    }
  }, [user?.email, user?.role])

  return { cycleId, loading, error }
}
