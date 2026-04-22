import { useState } from 'react'
import SectionCard from './SectionCard'
import EmptyState from './ui/EmptyState'
import { Button, ListSection } from './ui'
import { NARRATIVE_UI_COPY } from '../lib/portalOptions'
import { buildPreviewSummary, buildSummaryBlocks } from '../lib/text'

export default function NarrativeSummaryCard({
  title = NARRATIVE_UI_COPY.summaryCard.title,
  subtitle = NARRATIVE_UI_COPY.summaryCard.subtitle,
  data,
  loading,
  error,
  onRefresh,
}) {
  const [expanded, setExpanded] = useState(false)
  const summaryBlocks = data?.summary ? buildSummaryBlocks(data.summary) : []
  const actions = (
    <div className="flex items-center gap-2">
      {onRefresh ? (
        <Button variant="secondary" onClick={onRefresh}>
          Refresh
        </Button>
      ) : null}
      <Button variant="ghost" onClick={() => setExpanded((current) => !current)}>
        {expanded ? 'Hide' : 'View'}
      </Button>
    </div>
  )

  if (loading) {
    return (
      <SectionCard title={title} subtitle={subtitle} actions={actions}>
        {expanded ? (
          <div className="flex items-center gap-3 py-4 text-[color:var(--ui-text-muted)]">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-[color:var(--ui-border)] border-t-[color:var(--ui-text)]" />
            <p className="text-sm">{NARRATIVE_UI_COPY.summaryCard.loading}</p>
          </div>
        ) : (
          <p className="text-sm text-[color:var(--ui-text-muted)]">Narrative summary is ready to open.</p>
        )}
      </SectionCard>
    )
  }

  if (error) {
    return (
      <SectionCard title={title} subtitle={subtitle} actions={actions}>
        {expanded ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
            {error}
          </div>
        ) : (
          <p className="text-sm text-rose-700">{NARRATIVE_UI_COPY.summaryCard.error}</p>
        )}
      </SectionCard>
    )
  }

  if (!data?.available) {
    return (
      <SectionCard title={title} subtitle={subtitle} actions={actions}>
        {expanded ? (
          <EmptyState
            title={NARRATIVE_UI_COPY.summaryCard.notReadyTitle}
            description={data?.message || NARRATIVE_UI_COPY.summaryCard.notReadyDescription}
          />
        ) : (
          <p className="text-sm text-[color:var(--ui-text-muted)]">
            {NARRATIVE_UI_COPY.summaryCard.notReadyDescription}
          </p>
        )}
      </SectionCard>
    )
  }

  const metaChips = [
    data.tone ? `Tone: ${data.tone}` : null,
    data.status ? `Status: ${data.status}` : null,
    data.company_name ? data.company_name : null,
    data.source_company_count ? `${data.source_company_count} approved company${data.source_company_count === 1 ? '' : 'ies'}` : null,
    data.source_years?.length ? `Years: ${data.source_years.join(', ')}` : null,
    Array.isArray(data.framework_tags) && data.framework_tags.length ? `Frameworks: ${data.framework_tags.join(', ')}` : null,
    data.cached ? 'Cached' : null,
    data.fallback_used ? 'Fallback text' : null,
  ].filter(Boolean)

  return (
    <SectionCard title={title} subtitle={subtitle} actions={actions}>
      {!expanded ? (
        <div className="space-y-3">
          {data.headline ? <h3 className="ui-text-display text-[color:var(--ui-text)]">{data.headline}</h3> : null}
          <p className="text-sm leading-6 text-[color:var(--ui-text)]">
            {buildPreviewSummary(data.summary)}
          </p>
          {metaChips.length ? (
            <div className="flex flex-wrap gap-2">
              {metaChips.slice(0, 3).map((chip) => (
                <span key={chip} className="rounded-full border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] px-3 py-1 text-xs ui-text-strong text-[color:var(--ui-text-muted)]">
                  {chip}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : (
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

          {data.headline ? <h3 className="ui-text-display text-[color:var(--ui-text)]">{data.headline}</h3> : null}

          <div className="space-y-3">
            {summaryBlocks.map((block) => (
              <p key={block} className="text-sm leading-6 text-[color:var(--ui-text)]">
                {block}
              </p>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <ListSection title={NARRATIVE_UI_COPY.summaryCard.highlightsTitle} items={data.highlights} />
            <ListSection title={NARRATIVE_UI_COPY.summaryCard.watchoutsTitle} items={data.watchouts} />
            <ListSection title={NARRATIVE_UI_COPY.summaryCard.nextStepsTitle} items={data.recommendations} />
          </div>
        </div>
      )}
    </SectionCard>
  )
}
