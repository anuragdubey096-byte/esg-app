import { useEffect, useState } from 'react'
import { TextInput, TextareaInput } from './ui'

function toMultiline(items) {
  return Array.isArray(items) ? items.join('\n') : ''
}

function fromMultiline(value) {
  return String(value || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

export default function NarrativeEditor({ value, onChange, disabled = false }) {
  const [draft, setDraft] = useState(value)

  useEffect(() => {
    setDraft(value)
  }, [value])

  const update = (patch) => {
    const next = { ...draft, ...patch }
    setDraft(next)
    onChange?.(next)
  }

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <TextInput
        label="Headline"
        value={draft.headline || ''}
        onChange={(event) => update({ headline: event.target.value })}
        disabled={disabled}
      />
      <TextareaInput
        label="Summary"
        value={draft.summary || ''}
        onChange={(event) => update({ summary: event.target.value })}
        rows={6}
        disabled={disabled}
      />
      <TextareaInput
        label="Highlights"
        value={toMultiline(draft.highlights)}
        onChange={(event) => update({ highlights: fromMultiline(event.target.value) })}
        rows={4}
        disabled={disabled}
      />
      <TextareaInput
        label="Watchouts"
        value={toMultiline(draft.watchouts)}
        onChange={(event) => update({ watchouts: fromMultiline(event.target.value) })}
        rows={4}
        disabled={disabled}
      />
      <TextareaInput
        label="Next Steps"
        value={toMultiline(draft.recommendations)}
        onChange={(event) => update({ recommendations: fromMultiline(event.target.value) })}
        rows={4}
        disabled={disabled}
      />
    </div>
  )
}
