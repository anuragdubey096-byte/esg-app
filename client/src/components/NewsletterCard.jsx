import { useMemo, useState } from 'react'
import SectionCard from './SectionCard'
import EmptyState from './ui/EmptyState'
import { Button, ListSection } from './ui'
import { NARRATIVE_UI_COPY } from '../lib/portalOptions'
import { splitSentences } from '../lib/text'

export default function NewsletterCard({
  title = NARRATIVE_UI_COPY.newsletter.title,
  subtitle = NARRATIVE_UI_COPY.newsletter.subtitle,
  data,
  loading,
  error,
  onRefresh,
  onExport,
  onSend,
  exporting = false,
  sending = false,
}) {
  const [expanded, setExpanded] = useState(false)
  const [copying, setCopying] = useState(false)
  const summaryBlocks = useMemo(() => splitSentences(data?.summary || ''), [data?.summary])

  const metaChips = [
    data?.audience ? `Audience: ${data.audience}` : null,
    data?.tone ? `Tone: ${data.tone}` : null,
    data?.source_company_count ? `${data.source_company_count} companies` : null,
    data?.source_years?.length ? `Years: ${data.source_years.join(', ')}` : null,
    data?.cached ? 'Cached' : null,
    data?.fallback_used ? 'Fallback text' : null,
  ].filter(Boolean)

  const emailCopy = useMemo(() => {
    if (!data?.available) return ''
    const sections = []
    if (data.subject_line) sections.push(`Subject: ${data.subject_line}`)
    if (data.preheader) sections.push(`Preheader: ${data.preheader}`)
    if (data.headline) sections.push(`Headline: ${data.headline}`)
    if (data.summary) sections.push('', 'Summary:', data.summary)
    if (data.highlights?.length) sections.push('', 'Highlights:', ...data.highlights.map((item) => `- ${item}`))
    if (data.watchouts?.length) sections.push('', 'Watchouts:', ...data.watchouts.map((item) => `- ${item}`))
    if (data.recommendations?.length) sections.push('', 'Recommendations:', ...data.recommendations.map((item) => `- ${item}`))
    if (data.call_to_action) sections.push('', 'Call to Action:', data.call_to_action)
    return sections.join('\n').trim()
  }, [data])

  const handleCopy = async () => {
    if (!emailCopy) return
    setCopying(true)
    try {
      await navigator.clipboard.writeText(emailCopy)
      window.alert('Newsletter draft copied to clipboard.')
    } catch {
      window.alert('Unable to copy the newsletter draft on this browser.')
    } finally {
      setCopying(false)
    }
  }

  const handleExport = async () => {
    if (!onExport) return
    try {
      await onExport()
      window.alert('Newsletter export is ready.')
    } catch (err) {
      window.alert(err?.message || 'Unable to export newsletter draft.')
    }
  }

  const handleSend = async () => {
    if (!onSend) return
    try {
      await onSend()
      window.alert('Newsletter email send has been queued or completed.')
    } catch (err) {
      window.alert(err?.message || 'Unable to send newsletter draft.')
    }
  }

  const actions = (
    <div className="flex items-center gap-2">
      {onRefresh ? (
        <Button variant="secondary" onClick={onRefresh} disabled={loading || exporting || sending}>
          Refresh
        </Button>
      ) : null}
      {onExport ? (
        <Button variant="secondary" onClick={handleExport} disabled={loading || exporting || sending}>
          {exporting ? 'Exporting' : 'Export'}
        </Button>
      ) : null}
      {onSend ? (
        <Button variant="secondary" onClick={handleSend} disabled={loading || exporting || sending}>
          {sending ? 'Sending' : 'Send'}
        </Button>
      ) : null}
      <Button variant="ghost" onClick={handleCopy} disabled={!emailCopy || copying || loading || exporting || sending}>
        {copying ? 'Copying' : 'Copy'}
      </Button>
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
            <p className="text-sm">{NARRATIVE_UI_COPY.newsletter.loading}</p>
          </div>
        ) : (
          <p className="text-sm text-[color:var(--ui-text-muted)]">Newsletter draft is ready to open.</p>
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
          <p className="text-sm text-rose-700">{NARRATIVE_UI_COPY.newsletter.error}</p>
        )}
      </SectionCard>
    )
  }

  if (!data?.available) {
    return (
      <SectionCard title={title} subtitle={subtitle} actions={actions}>
        {expanded ? (
          <EmptyState
            title={NARRATIVE_UI_COPY.newsletter.notReadyTitle}
            description={data?.message || NARRATIVE_UI_COPY.newsletter.notReadyDescription}
          />
        ) : (
          <p className="text-sm text-[color:var(--ui-text-muted)]">
            {NARRATIVE_UI_COPY.newsletter.notReadyDescription}
          </p>
        )}
      </SectionCard>
    )
  }

  return (
    <SectionCard title={title} subtitle={subtitle} actions={actions}>
      {!expanded ? (
        <div className="space-y-3">
          {data.subject_line ? <h3 className="ui-text-display text-[color:var(--ui-text)]">{data.subject_line}</h3> : null}
          <p className="text-sm leading-6 text-[color:var(--ui-text)]">
            {splitSentences(data.preheader || data.summary || '')[0] || data.preheader || data.summary}
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

          {data.subject_line ? (
            <div className="rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-[color:var(--ui-text-muted)]">{NARRATIVE_UI_COPY.newsletter.subjectTitle}</p>
              <p className="mt-1 ui-text-strong text-[color:var(--ui-text)]">{data.subject_line}</p>
            </div>
          ) : null}

          {data.preheader ? (
            <div className="rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-[color:var(--ui-text-muted)]">{NARRATIVE_UI_COPY.newsletter.preheaderTitle}</p>
              <p className="mt-1 text-sm leading-6 text-[color:var(--ui-text)]">{data.preheader}</p>
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

          {data.call_to_action ? (
            <div className="rounded-xl border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-4 py-3 text-sm leading-6 text-[color:var(--ui-text)]">
              <p className="text-xs uppercase tracking-wide text-[color:var(--ui-text-muted)]">{NARRATIVE_UI_COPY.newsletter.callToActionTitle}</p>
              <p className="mt-1">{data.call_to_action}</p>
            </div>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-3">
            <ListSection title={NARRATIVE_UI_COPY.newsletter.highlightsTitle} items={data.highlights} />
            <ListSection title={NARRATIVE_UI_COPY.newsletter.watchoutsTitle} items={data.watchouts} />
            <ListSection title={NARRATIVE_UI_COPY.newsletter.nextStepsTitle} items={data.recommendations} />
          </div>
        </div>
      )}
    </SectionCard>
  )
}
