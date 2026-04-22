import SectionCard from './SectionCard'
import { ListSection } from './ui'
import { NARRATIVE_UI_COPY } from '../lib/portalOptions'

function formatValue(value, unit) {
  if (value === null || value === undefined || value === '') return 'n/a'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return `${value}${unit ? ` ${unit}` : ''}`
  if (unit === '%') return `${numeric.toFixed(1)}%`
  if (unit === 'tCO2e') return `${numeric.toLocaleString()} tCO2e`
  if (unit === 'rate') return numeric.toFixed(2)
  return `${numeric.toFixed(1)}${unit ? ` ${unit}` : ''}`
}

function formatTrend(value) {
  const numeric = Number(value || 0)
  if (Number.isNaN(numeric)) return 'n/a'
  const prefix = numeric > 0 ? '+' : ''
  return `${prefix}${numeric.toFixed(1)}%`
}

function MiniSeries({ title, items }) {
  if (!Array.isArray(items) || !items.length) return null
  const maxValue = Math.max(...items.map((item) => Number(item.value || 0)), 0)
  return (
    <div className="space-y-2">
      <p className="ui-text-strong text-[color:var(--ui-text)]">{title}</p>
      <div className="space-y-2">
        {items.map((item) => {
          const value = Number(item.value || 0)
          const width = maxValue > 0 ? Math.max((value / maxValue) * 100, 8) : 0
          return (
            <div key={item.label} className="space-y-1 rounded-lg border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-3 py-2">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="ui-text-strong text-[color:var(--ui-text)]">{item.label}</span>
                <span className="text-[color:var(--ui-text-muted)]">{value}</span>
              </div>
              <div className="h-2 rounded-full bg-[color:var(--ui-surface)] overflow-hidden">
                <div className="h-2 rounded-full bg-[color:var(--ui-text)]" style={{ width: `${width}%` }} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function ImpactStoryCard({
  title = NARRATIVE_UI_COPY.impactStory.title,
  subtitle = NARRATIVE_UI_COPY.impactStory.subtitle,
  story,
  maxInsights = 4,
}) {
  if (!story) return null

  const equivalents = Array.isArray(story.equivalents) ? story.equivalents : []
  const highlights = Array.isArray(story.highlights) ? story.highlights : []
  const watchouts = Array.isArray(story.watchouts) ? story.watchouts : []
  const recommendations = Array.isArray(story.recommendations) ? story.recommendations : []
  const benchmarkCallouts = Array.isArray(story.benchmark_callouts) ? story.benchmark_callouts : []
  const benchmarkComparisons = Array.isArray(story.benchmark_comparisons) ? story.benchmark_comparisons : []
  const comparisonRows = Array.isArray(story.comparison_rows) ? story.comparison_rows : []
  const metricInsights = Array.isArray(story.metric_insights) ? story.metric_insights : []
  const chartSeries = story.chart_series || {}
  const statusDistribution = Array.isArray(chartSeries.status_distribution) ? chartSeries.status_distribution : []

  return (
    <SectionCard title={title} subtitle={subtitle}>
      <div className="space-y-6">
        <div className="space-y-3">
          {story.headline ? <h3 className="ui-text-display text-[color:var(--ui-text)]">{story.headline}</h3> : null}
          {story.summary ? <p className="text-sm leading-6 text-[color:var(--ui-text)]">{story.summary}</p> : null}
          {story.trend_summary ? (
            <div className="rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-4 py-3 text-sm leading-6 text-[color:var(--ui-text)]">
              {story.trend_summary}
            </div>
          ) : null}
          {benchmarkCallouts.length ? (
            <div className="flex flex-wrap gap-2">
              {benchmarkCallouts.map((callout) => (
                <span key={callout} className="rounded-full border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] px-3 py-1 text-xs ui-text-strong text-[color:var(--ui-text-muted)]">
                  {callout}
                </span>
              ))}
            </div>
          ) : null}
        </div>

        {benchmarkComparisons.length ? (
          <div className="space-y-3">
            <p className="ui-text-strong text-[color:var(--ui-text)]">Benchmark Comparisons</p>
            <div className="flex flex-wrap gap-2">
              {benchmarkComparisons.slice(0, 4).map((comparison) => (
                <span
                  key={comparison.metric_name}
                  className="rounded-full border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] px-3 py-1 text-xs ui-text-strong text-[color:var(--ui-text-muted)]"
                >
                  {comparison.metric_name}
                  {comparison.status ? `: ${comparison.status}` : ''}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {comparisonRows.length ? (
          <div className="space-y-3">
            <p className="ui-text-strong text-[color:var(--ui-text)]">Current vs Previous</p>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {comparisonRows.slice(0, 6).map((row) => (
                <div key={row.metric_name} className="rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="ui-text-strong text-[color:var(--ui-text)]">{row.metric_name}</p>
                      <p className="text-xs text-[color:var(--ui-text-muted)] mt-1">
                        Current: {formatValue(row.current_value, row.unit)}
                      </p>
                      <p className="text-xs text-[color:var(--ui-text-muted)]">
                        Previous: {formatValue(row.previous_value, row.unit)}
                      </p>
                    </div>
                    <span className="rounded-full border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-2 py-1 text-[11px] ui-text-strong uppercase tracking-wide text-[color:var(--ui-text-muted)]">
                      {formatTrend(row.trend_percent)}
                    </span>
                  </div>
                  {row.narrative ? <p className="mt-3 text-sm leading-6 text-[color:var(--ui-text-muted)]">{row.narrative}</p> : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {statusDistribution.length ? (
          <MiniSeries
            title="Status Mix"
            items={statusDistribution.map((item) => ({ label: item.label || item.name, value: item.value }))}
          />
        ) : null}

        {equivalents.length ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {equivalents.map((equivalent) => (
              <div key={equivalent.label} className="rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] p-4 shadow-sm">
                <p className="text-xs uppercase tracking-wide text-[color:var(--ui-text-muted)]">{equivalent.label}</p>
                <p className="ui-text-display text-[color:var(--ui-text)] mt-2">{formatValue(equivalent.value, equivalent.unit)}</p>
                {equivalent.narrative ? <p className="text-sm leading-6 text-[color:var(--ui-text-muted)] mt-2">{equivalent.narrative}</p> : null}
              </div>
            ))}
          </div>
        ) : null}

        <div className="grid gap-4 lg:grid-cols-3">
          <ListSection title={NARRATIVE_UI_COPY.impactStory.highlightsTitle} items={highlights} />
          <ListSection title={NARRATIVE_UI_COPY.impactStory.watchoutsTitle} items={watchouts} />
          <ListSection title={NARRATIVE_UI_COPY.impactStory.nextStepsTitle} items={recommendations} />
        </div>

        {metricInsights.length ? (
          <div className="space-y-3">
            <p className="ui-text-strong text-[color:var(--ui-text)]">{NARRATIVE_UI_COPY.impactStory.whatDoesThisMean}</p>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {metricInsights.slice(0, maxInsights).map((insight) => (
                <div key={insight.metric_name} className="rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="ui-text-strong text-[color:var(--ui-text)]">{insight.metric_name}</p>
                      <p className="text-xs text-[color:var(--ui-text-muted)] mt-1">
                        {formatValue(insight.current_value, insight.unit)}
                        {insight.benchmark_label ? ` - ${insight.benchmark_label}` : ''}
                      </p>
                    </div>
                    {insight.benchmark_status ? (
                      <span className="rounded-full border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-2 py-1 text-[11px] ui-text-strong uppercase tracking-wide text-[color:var(--ui-text-muted)]">
                        {insight.benchmark_status}
                      </span>
                    ) : null}
                  </div>
                  {insight.real_world_equivalent ? (
                    <p className="mt-3 text-sm leading-6 text-[color:var(--ui-text-muted)]">{insight.real_world_equivalent}</p>
                  ) : null}
                  <p className="mt-3 text-sm leading-6 text-[color:var(--ui-text)]">{insight.tooltip}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </SectionCard>
  )
}
