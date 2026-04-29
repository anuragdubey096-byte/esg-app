import { useEffect, useMemo, useState } from 'react'
import SectionCard from './SectionCard'
import { API_BASE_URL } from '../lib/api'
import { useOptionalLiveUpdates } from '../contexts/LiveUpdatesContext'

function eventMatchesFilters(event, filters) {
  if (!event) return false
  if (filters.companyId && Number(event.company_id) !== Number(filters.companyId)) return false
  if (filters.submissionId && Number(event.submission_id) !== Number(filters.submissionId)) return false
  return true
}

function formatRelativeTime(value) {
  if (!value) return 'Just now'
  const createdAt = new Date(value)
  const diffMs = Date.now() - createdAt.getTime()
  if (Number.isNaN(diffMs) || diffMs < 60_000) return 'Just now'
  const diffMinutes = Math.round(diffMs / 60_000)
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.round(diffHours / 24)
  return `${diffDays}d ago`
}

export default function ActivityFeedCard({
  user,
  title = 'Activity Feed',
  subtitle = 'Recent workflow events',
  companyId = null,
  submissionId = null,
  limit = 6,
}) {
  const liveUpdates = useOptionalLiveUpdates()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (companyId) params.set('company_id', String(companyId))
    if (submissionId) params.set('submission_id', String(submissionId))
    return params.toString()
  }, [companyId, limit, submissionId])

  useEffect(() => {
    let cancelled = false

    const loadFeed = async () => {
      setLoading(true)
      try {
        const response = await fetch(`${API_BASE_URL}/live/activity?${queryString}`, {
          headers: {
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          },
        })
        if (!response.ok) {
          throw new Error('Feed unavailable')
        }
        const payload = await response.json()
        if (!cancelled) {
          setItems(Array.isArray(payload?.items) ? payload.items : [])
        }
      } catch {
        if (!cancelled) setItems([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    loadFeed()
    return () => {
      cancelled = true
    }
  }, [queryString, user?.email, user?.role])

  useEffect(() => {
    const nextEvent = liveUpdates?.lastEvent
    if (!nextEvent || !eventMatchesFilters(nextEvent, { companyId, submissionId })) return
    setItems((current) => {
      const filtered = current.filter((item) => item.id !== nextEvent.id)
      return [nextEvent, ...filtered].slice(0, limit)
    })
  }, [companyId, limit, liveUpdates?.lastEvent, submissionId])

  return (
    <SectionCard title={title} subtitle={subtitle}>
      {loading ? <p className="text-sm text-slate-500">Loading activity…</p> : null}
      {!loading && !items.length ? <p className="text-sm text-slate-500">No recent events yet.</p> : null}
      {items.length ? (
        <div className="space-y-3">
          {items.map((item) => (
            <article key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50/70 px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm ui-text-strong text-[color:var(--ui-text-strong)]">{item.title}</p>
                  <p className="mt-1 text-sm text-[color:var(--ui-text)]">{item.message}</p>
                </div>
                <span className="text-xs uppercase tracking-wide text-slate-500">{formatRelativeTime(item.created_at)}</span>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </SectionCard>
  )
}
