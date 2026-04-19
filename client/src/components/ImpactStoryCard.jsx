import SectionCard from './SectionCard'
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

function ListBlock({ title, items }) {
  if (!Array.isArray(items) || !items.length) return null
  return (
    <div className="space-y-2">
      <p className="ui-text-strong text-[color:var(--ui-text)]">{title}</p>
      <div className="space-y-2">
        {items.map((item) => (
          <div key={item} className="rounded-lg border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-3 py-2 text-sm leading-6 text-[color:var(--ui-text)]">
            {item}
          </div>
        ))}
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
  const metricInsights = Array.isArray(story.metric_insights) ? story.metric_insights : []

  return (
    <SectionCard title={title} subtitle={subtitle}>
      <div className="space-y-6">
        <div className="space-y-3">
          {story.headline ? <h3 className="ui-text-display text-[color:var(--ui-text)]">{story.headline}</h3> : null}
          {story.summary ? <p className="text-sm leading-6 text-[color:var(--ui-text)]">{story.summary}</p> : null}
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
          <ListBlock title={NARRATIVE_UI_COPY.impactStory.highlightsTitle} items={highlights} />
          <ListBlock title={NARRATIVE_UI_COPY.impactStory.watchoutsTitle} items={watchouts} />
          <ListBlock title={NARRATIVE_UI_COPY.impactStory.nextStepsTitle} items={recommendations} />
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
