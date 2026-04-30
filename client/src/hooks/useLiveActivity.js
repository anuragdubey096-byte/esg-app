import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

function toWsBaseUrl(apiBaseUrl) {
  const normalized = String(apiBaseUrl || '').replace(/\/$/, '')
  if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
    return normalized.replace(/^http/i, 'ws')
  }
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const path = normalized.startsWith('/') ? normalized : `/${normalized}`
    return `${protocol}//${window.location.host}${path}`
  }
  return normalized
}

export default function useLiveActivity({ user, limit = 6, enabled = true }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [connectionStatus, setConnectionStatus] = useState('disconnected')

  const socketRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const reconnectAttemptRef = useRef(0)

  const role = String(user?.role || '').toLowerCase()
  const email = String(user?.email || '').toLowerCase()
  const wsUrl = useMemo(() => {
    const base = toWsBaseUrl(BACKEND_URL)
    const query = new URLSearchParams()
    if (role) query.set('role', role)
    if (email) query.set('email', email)
    return `${base}/ws/live?${query.toString()}`
  }, [email, role])

  const mergeEvent = useCallback((event) => {
    if (!event || typeof event !== 'object') return
    setEvents((current) => {
      const byId = new Map()
      for (const row of current || []) {
        byId.set(String(row.id), row)
      }
      byId.set(String(event.id), event)
      const merged = Array.from(byId.values()).sort((a, b) => {
        const aTime = String(a.created_at || '')
        const bTime = String(b.created_at || '')
        return bTime.localeCompare(aTime)
      })
      return merged.slice(0, Math.max(limit, 1))
    })
  }, [limit])

  const refresh = useCallback(async () => {
    if (!enabled) return
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${BACKEND_URL}/live/activity?limit=${limit}`, {
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || `Live activity request failed (${response.status})`)
      }
      const payload = await response.json()
      const rows = Array.isArray(payload.events) ? payload.events : (Array.isArray(payload.items) ? payload.items : [])
      setEvents(rows)
    } catch (requestError) {
      setEvents((current) => (Array.isArray(current) ? current : []))
      setError(requestError.message || 'Unable to load live activity.')
    } finally {
      setLoading(false)
    }
  }, [enabled, limit, user?.email, user?.role])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    if (!enabled || !role) return undefined

    let cancelled = false

    const clearReconnect = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }

    const closeSocket = () => {
      if (socketRef.current) {
        try {
          socketRef.current.close()
        } catch (_) {
          // no-op
        }
        socketRef.current = null
      }
    }

    const connect = () => {
      if (cancelled) return
      clearReconnect()
      closeSocket()
      setConnectionStatus('connecting')

      const socket = new WebSocket(wsUrl)
      socketRef.current = socket

      socket.onopen = () => {
        reconnectAttemptRef.current = 0
        setConnectionStatus('connected')
      }

      socket.onmessage = (messageEvent) => {
        try {
          const payload = JSON.parse(messageEvent.data)
          if (payload?.type === 'event' && payload.event) {
            mergeEvent(payload.event)
          }
          if (payload?.type === 'heartbeat') {
            setConnectionStatus('connected')
          }
        } catch (_) {
          // Ignore malformed frames and keep socket alive
        }
      }

      socket.onerror = () => {
        setConnectionStatus('error')
      }

      socket.onclose = () => {
        if (cancelled) return
        setConnectionStatus('disconnected')
        reconnectAttemptRef.current += 1
        const backoffMs = Math.min(6000, 500 * reconnectAttemptRef.current)
        reconnectTimerRef.current = setTimeout(connect, backoffMs)
      }
    }

    connect()

    return () => {
      cancelled = true
      clearReconnect()
      closeSocket()
      setConnectionStatus('disconnected')
    }
  }, [enabled, mergeEvent, role, wsUrl])

  return {
    events,
    loading,
    error,
    connectionStatus,
    refresh,
  }
}
