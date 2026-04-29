import SectionCard from './SectionCard'

function severityTone(severity) {
  if (severity === 'high') return 'border-rose-200 bg-rose-50 text-rose-900'
  if (severity === 'medium') return 'border-amber-200 bg-amber-50 text-amber-900'
  return 'border-slate-200 bg-slate-50 text-slate-700'
}

export default function AnomalySummaryCard({
  title = 'Anomaly Watchlist',
  subtitle = 'Approved-data anomaly detection and recommended follow-up',
  data,
  loading = false,
  error = '',
  maxItems = 5,
}) {
  const items = Array.isArray(data?.items) ? data.items.slice(0, maxItems) : []
  const severityCounts = data?.severity_counts || {}

  return (
    <SectionCard title={title} subtitle={subtitle}>
      {loading ? <p className="text-sm text-slate-500">Scanning approved data for anomalies...</p> : null}
      {error ? <p className="text-sm text-rose-700">{error}</p> : null}
      {!loading && !error ? (
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4">
            <p className="text-sm ui-text-strong text-[color:var(--ui-text-strong)]">{data?.headline || 'No anomaly summary available'}</p>
            <p className="mt-2 text-sm text-[color:var(--ui-text)]">{data?.summary || data?.message || 'No approved-data anomaly summary is available yet.'}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
              <span className="rounded-full border border-rose-200 bg-rose-50 px-3 py-1">High {severityCounts.high || 0}</span>
              <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1">Medium {severityCounts.medium || 0}</span>
              <span className="rounded-full border border-slate-200 bg-white px-3 py-1">Low {severityCounts.low || 0}</span>
            </div>
          </div>

          {!items.length ? <p className="text-sm text-slate-500">{data?.message || 'No anomalies are currently flagged.'}</p> : null}

          {items.length ? (
            <div className="space-y-3">
              {items.map((item) => (
                <article key={item.id} className={`rounded-2xl border px-4 py-4 ${severityTone(item.severity)}`}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-sm ui-text-strong">{item.metric_name}</p>
                      <p className="mt-1 text-xs uppercase tracking-wide opacity-70">
                        {item.company_name ? `${item.company_name} | ` : ''}
                        {item.severity} severity
                      </p>
                    </div>
                    <p className="text-sm ui-text-strong">{item.current_value}</p>
                  </div>
                  <p className="mt-2 text-sm">{item.rationale}</p>
                  <p className="mt-2 text-xs ui-text-strong">Recommended action: {item.recommendation}</p>
                </article>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </SectionCard>
  )
}
