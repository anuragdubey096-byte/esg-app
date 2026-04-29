import SectionCard from './SectionCard'

function priorityTone(priority) {
  if (priority === 'high') return 'border-rose-200 bg-rose-50/80 text-rose-900'
  if (priority === 'medium') return 'border-amber-200 bg-amber-50/80 text-amber-900'
  return 'border-slate-200 bg-slate-50/80 text-slate-700'
}

export default function ExternalContextFeedCard({
  title = 'Sector & Regulatory Feed',
  subtitle = 'Curated external context shaped by the current portfolio view',
  data,
  loading = false,
  error = '',
}) {
  const items = Array.isArray(data?.items) ? data.items : []

  return (
    <SectionCard title={title} subtitle={subtitle}>
      {loading ? <p className="text-sm text-slate-500">Loading sector and regulatory context...</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {!loading && !error && !items.length ? <p className="text-sm text-slate-500">{data?.message || 'No context items are available yet.'}</p> : null}
      {items.length ? (
        <div className="space-y-3">
          {items.map((item) => (
            <article key={item.id} className={`rounded-2xl border px-4 py-4 ${priorityTone(item.priority)}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-current/20 bg-white/70 px-2 py-1 text-[11px] uppercase tracking-wide">
                      {item.item_type === 'regulation' ? 'Regulation' : item.sector || 'Sector context'}
                    </span>
                    <span className="text-[11px] uppercase tracking-wide opacity-70">{item.priority}</span>
                  </div>
                  <p className="mt-2 text-sm ui-text-strong">{item.title}</p>
                  <p className="mt-2 text-sm">{item.summary}</p>
                </div>
                <span className="text-xs opacity-70">{item.published_at ? new Date(item.published_at).toLocaleDateString() : ''}</span>
              </div>
              {item.impact_hint ? <p className="mt-3 text-xs opacity-80">Impact: {item.impact_hint}</p> : null}
              {item.action_prompt ? <p className="mt-2 text-xs ui-text-strong">Next move: {item.action_prompt}</p> : null}
            </article>
          ))}
        </div>
      ) : null}
    </SectionCard>
  )
}
