import { useMemo } from 'react'
import SectionCard from './SectionCard'
import { Button, ListSection } from './ui'

const LIST_LABELS = {
  priority_actions: 'Priority actions',
  watchouts: 'Watchouts',
  highlights: 'Highlights',
  watchlist: 'Watchlist',
  next_steps: 'Next steps',
  sections_to_focus: 'Sections to focus',
  changes: 'Changes',
  attention_items: 'Attention items',
}

const TEXT_FIELD_LABELS = {
  deadline_note: 'Deadline note',
  board_note: 'Board note',
  review_readiness: 'Review readiness',
}

function pickSummary(payload) {
  if (!payload || typeof payload !== 'object') return ''
  return (
    payload.summary
    || payload.status_summary
    || ''
  )
}

export default function DashboardNarrativeMaterialCard({
  title,
  subtitle,
  data,
  loading = false,
  error = '',
  onRefresh,
}) {
  const payload = data?.payload && typeof data.payload === 'object' ? data.payload : {}
  const summary = pickSummary(payload)
  const listEntries = useMemo(
    () => Object.entries(payload).filter(([key, value]) => Array.isArray(value) && LIST_LABELS[key]),
    [payload],
  )
  const textEntries = useMemo(
    () => Object.entries(payload).filter(([key, value]) => typeof value === 'string' && TEXT_FIELD_LABELS[key] && value.trim()),
    [payload],
  )
  const metaChips = [
    data?.source_years?.length ? `Years: ${data.source_years.join(', ')}` : null,
    data?.cached ? 'Cached' : null,
    data?.fallback_used ? 'Fallback text' : null,
  ].filter(Boolean)

  const actions = onRefresh ? (
    <Button variant="secondary" onClick={onRefresh} disabled={loading}>
      Refresh
    </Button>
  ) : null

  return (
    <SectionCard title={title} subtitle={subtitle} actions={actions}>
      {loading ? <p className="text-sm text-slate-500">Generating live narrative material...</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {!loading && !error ? (
        <div className="space-y-4">
          {metaChips.length ? (
            <div className="flex flex-wrap gap-2">
              {metaChips.map((chip) => (
                <span key={chip} className="rounded-full border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] px-3 py-1 text-xs ui-text-strong text-[color:var(--ui-text-muted)]">
                  {chip}
                </span>
              ))}
            </div>
          ) : null}

          {payload.headline ? <h3 className="ui-text-display text-[color:var(--ui-text)]">{payload.headline}</h3> : null}
          {summary ? <p className="text-sm leading-6 text-[color:var(--ui-text)]">{summary}</p> : null}

          {listEntries.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {listEntries.map(([key, value]) => (
                <ListSection key={key} title={LIST_LABELS[key]} items={value} />
              ))}
            </div>
          ) : null}

          {textEntries.length ? (
            <div className="space-y-3">
              {textEntries.map(([key, value]) => (
                <div key={key} className="rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-4 py-3">
                  <p className="text-xs uppercase tracking-wide text-[color:var(--ui-text-muted)]">{TEXT_FIELD_LABELS[key]}</p>
                  <p className="mt-1 text-sm leading-6 text-[color:var(--ui-text)]">{value}</p>
                </div>
              ))}
            </div>
          ) : null}

          {!payload.headline && !summary && !listEntries.length && !textEntries.length ? (
            <p className="text-sm text-[color:var(--ui-text-muted)]">
              {data?.message || 'No narrative material is available for this dashboard context yet.'}
            </p>
          ) : null}
        </div>
      ) : null}
    </SectionCard>
  )
}
