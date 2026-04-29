import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

const LiveUpdatesContext = createContext(null)

function normalizeBaseUrl() {
  if (typeof window === 'undefined') return ''
  if (API_BASE_URL.startsWith('http://') || API_BASE_URL.startsWith('https://')) {
    return API_BASE_URL
  }
  return `${window.location.origin}${API_BASE_URL.startsWith('/') ? API_BASE_URL : `/${API_BASE_URL}`}`
}

function buildWebSocketUrl(user, lastEventId) {
  if (!user || typeof window === 'undefined') return ''
  const httpBase = normalizeBaseUrl()
  if (!httpBase) return ''
  const wsBase = httpBase.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:')
  const params = new URLSearchParams({
    role: user.role || '',
    email: user.email || '',
    last_event_id: String(lastEventId || 0),
  })
  return `${wsBase}/ws/live?${params.toString()}`
}

function addUniqueEvent(events, nextEvent, limit = 20) {
  const filtered = events.filter((item) => item.id !== nextEvent.id)
  return [nextEvent, ...filtered].slice(0, limit)
}

function addToast(toasts, nextToast) {
  const filtered = toasts.filter((item) => item.id !== nextToast.id)
  return [nextToast, ...filtered].slice(0, 5)
}

function buildToast({
  id,
  title = 'Update',
  message = '',
  severity = 'info',
  timeLabel,
}) {
  return {
    id: id || `toast-${Date.now()}-${Math.round(Math.random() * 10000)}`,
    title,
    message,
    severity,
    timeLabel: timeLabel || new Date().toLocaleTimeString(),
  }
}

function ToastViewport({ toasts, onDismiss }) {
  if (!toasts.length) return null
  return (
    <div
      className="fixed right-4 top-20 z-[80] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-3"
      aria-live="polite"
      aria-atomic="false"
    >
      {toasts.map((toast) => (
        <article
          key={toast.id}
          className={`rounded-2xl border px-4 py-3 shadow-lg backdrop-blur ${
            toast.severity === 'success'
              ? 'border-emerald-200 bg-emerald-50/95'
              : toast.severity === 'warning'
                ? 'border-amber-200 bg-amber-50/95'
                : toast.severity === 'error'
                  ? 'border-red-200 bg-red-50/95'
                  : 'border-slate-200 bg-white/95'
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm ui-text-strong text-[color:var(--ui-text-strong)]">{toast.title}</p>
              <p className="mt-1 text-sm text-[color:var(--ui-text)]">{toast.message}</p>
              <p className="mt-2 text-xs uppercase tracking-wide text-slate-500">{toast.timeLabel}</p>
            </div>
            <button
              type="button"
              className="rounded-full px-2 py-1 text-xs ui-text-strong text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
              onClick={() => onDismiss(toast.id)}
            >
              Dismiss
            </button>
          </div>
        </article>
      ))}
    </div>
  )
}

export function LiveUpdatesProvider({ user, children }) {
  const [recentEvents, setRecentEvents] = useState([])
  const [toasts, setToasts] = useState([])
  const [lastEvent, setLastEvent] = useState(null)
  const [lastEventId, setLastEventId] = useState(0)
  const [connectionState, setConnectionState] = useState('idle')
  const [unreadCount, setUnreadCount] = useState(0)
  const websocketRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const toastTimersRef = useRef({})
  const lastEventIdRef = useRef(0)

  useEffect(() => {
    setRecentEvents([])
    setToasts([])
    setLastEvent(null)
    setLastEventId(0)
    lastEventIdRef.current = 0
    setUnreadCount(0)
  }, [user?.email, user?.role])

  useEffect(() => {
    if (!user) return undefined
    let cancelled = false

    const loadActivity = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/live/activity?limit=12`, {
          headers: {
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          },
        })
        if (!response.ok) return
        const payload = await response.json()
        if (cancelled) return
        const items = Array.isArray(payload?.items) ? payload.items : []
        setRecentEvents(items)
        const highestEventId = items.reduce((maxValue, item) => Math.max(maxValue, Number(item?.id || 0)), 0)
        lastEventIdRef.current = Math.max(lastEventIdRef.current, highestEventId)
        setLastEventId(lastEventIdRef.current)
      } catch {
        // Keep the provider non-blocking if the live endpoint is unavailable.
      }
    }

    loadActivity()
    return () => {
      cancelled = true
    }
  }, [user?.email, user?.role])

  useEffect(() => {
    if (!user) return undefined
    let closedByEffect = false

    const connect = () => {
      if (closedByEffect) return
      const socketUrl = buildWebSocketUrl(user, lastEventIdRef.current)
      if (!socketUrl) return

      setConnectionState('connecting')
      const socket = new WebSocket(socketUrl)
      websocketRef.current = socket

      socket.onopen = () => {
        if (closedByEffect) return
        setConnectionState('connected')
      }

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)
          if (payload?.type !== 'event' || !payload?.event) return
          const nextEvent = payload.event
          setLastEvent(nextEvent)
          lastEventIdRef.current = Math.max(lastEventIdRef.current, Number(nextEvent.id || 0))
          setLastEventId(lastEventIdRef.current)
          setRecentEvents((current) => addUniqueEvent(current, nextEvent))

          if (nextEvent.is_toast && nextEvent.actor_email !== user?.email) {
            const toastId = `event-${nextEvent.id}`
            const toast = {
              id: toastId,
              title: nextEvent.title || 'Live update',
              message: nextEvent.message || 'A new event was recorded.',
              severity: nextEvent.severity || 'info',
              timeLabel: new Date(nextEvent.created_at || Date.now()).toLocaleTimeString(),
            }
            queueToast(toast)
            setUnreadCount((current) => current + 1)
          }
        } catch {
          // Ignore malformed websocket messages.
        }
      }

      socket.onerror = () => {
        setConnectionState('error')
      }

      socket.onclose = () => {
        if (closedByEffect) return
        setConnectionState('disconnected')
        reconnectTimerRef.current = window.setTimeout(connect, 2000)
      }
    }

    connect()
    return () => {
      closedByEffect = true
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current)
      }
      if (websocketRef.current) {
        websocketRef.current.close()
      }
    }
  }, [user])

  useEffect(() => () => {
    Object.values(toastTimersRef.current).forEach((timerId) => {
      window.clearTimeout(timerId)
    })
  }, [])

  const queueToast = (toastInput, durationMs = 5200) => {
    const toast = buildToast(toastInput || {})
    setToasts((current) => addToast(current, toast))
    if (toastTimersRef.current[toast.id]) {
      window.clearTimeout(toastTimersRef.current[toast.id])
    }
    toastTimersRef.current[toast.id] = window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== toast.id))
      delete toastTimersRef.current[toast.id]
    }, durationMs)
    return toast.id
  }

  const dismissToast = (toastId) => {
    if (toastTimersRef.current[toastId]) {
      window.clearTimeout(toastTimersRef.current[toastId])
      delete toastTimersRef.current[toastId]
    }
    setToasts((current) => current.filter((item) => item.id !== toastId))
  }

  const markNotificationsRead = () => {
    setUnreadCount(0)
  }

  const value = useMemo(() => ({
    recentEvents,
    toasts,
    lastEvent,
    lastEventId,
    connectionState,
    unreadCount,
    dismissToast,
    markNotificationsRead,
    notify: queueToast,
  }), [connectionState, lastEvent, lastEventId, recentEvents, toasts, unreadCount])

  return (
    <LiveUpdatesContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismissToast} />
    </LiveUpdatesContext.Provider>
  )
}

export function useLiveUpdates() {
  const value = useContext(LiveUpdatesContext)
  if (!value) {
    throw new Error('useLiveUpdates must be used within a LiveUpdatesProvider')
  }
  return value
}

export function useOptionalLiveUpdates() {
  return useContext(LiveUpdatesContext)
}
