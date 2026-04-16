import { useState } from 'react'
import SectionCard from './SectionCard'
import EmptyState from './ui/EmptyState'
import { Button } from './ui'

function splitSentences(text) {
  const value = String(text || '').trim()
  if (!value) return []
  const matches = value.match(/[^.!?]+[.!?]+|[^.!?]+$/g)
  return matches ? matches.map((part) => part.trim()).filter(Boolean) : [value]
}

function buildPreviewSummary(text, sentenceCount = 2) {
  const sentences = splitSentences(text)
  if (!sentences.length) return ''
  if (sentences.length <= sentenceCount) return sentences.join(' ')
  return `${sentences.slice(0, sentenceCount).join(' ')}...`
}

function buildSummaryBlocks(text) {
  const sentences = splitSentences(text)
  if (sentences.length <= 2) return [sentences.join(' ')]

  const blocks = []
  for (let index = 0; index < sentences.length; index += 2) {
    blocks.push(sentences.slice(index, index + 2).join(' '))
  }
  return blocks
}

function SectionList({ title, items }) {
  if (!items?.length) return null
  return (
    <div className="space-y-2">
      <p className="ui-text-strong text-slate-700">{title}</p>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function NarrativeSummaryCard({ title = 'AI ESG Narrative Summary', subtitle = 'Board-ready plain-English summary generated from approved data only', data, loading, error, onRefresh }) {
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
          <div className="flex items-center gap-3 py-4 text-slate-600">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
            <p className="text-sm">Generating narrative from approved submission data...</p>
          </div>
        ) : (
          <p className="text-sm text-slate-600">Narrative summary is ready to open.</p>
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
          <p className="text-sm text-rose-700">Narrative summary could not load.</p>
        )}
      </SectionCard>
    )
  }

  if (!data?.available) {
    return (
      <SectionCard title={title} subtitle={subtitle} actions={actions}>
        {expanded ? (
          <EmptyState
            title="Narrative not ready yet"
            description={data?.message || 'This summary appears after an approved submission is available.'}
          />
        ) : (
          <p className="text-sm text-slate-600">
            Narrative summary will appear after an approved submission is available.
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
          {data.headline ? <h3 className="ui-text-display text-slate-900">{data.headline}</h3> : null}
          <p className="text-sm leading-6 text-slate-700">
            {buildPreviewSummary(data.summary)}
          </p>
          {metaChips.length ? (
            <div className="flex flex-wrap gap-2">
              {metaChips.slice(0, 3).map((chip) => (
                <span key={chip} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs ui-text-strong text-slate-600">
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
                <span key={chip} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs ui-text-strong text-slate-600">
                  {chip}
                </span>
              ))}
            </div>
          ) : null}

          {data.headline ? <h3 className="ui-text-display text-slate-900">{data.headline}</h3> : null}

          <div className="space-y-3">
            {summaryBlocks.map((block) => (
              <p key={block} className="text-sm leading-6 text-slate-700">
                {block}
              </p>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <SectionList title="Highlights" items={data.highlights} />
            <SectionList title="Watchouts" items={data.watchouts} />
            <SectionList title="Next steps" items={data.recommendations} />
          </div>
        </div>
      )}
    </SectionCard>
  )
}
