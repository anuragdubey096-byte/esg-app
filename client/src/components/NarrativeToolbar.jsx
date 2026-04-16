import { Button, SelectInput } from './ui'

const TONES = [
  { value: 'board-ready', label: 'Board-ready' },
  { value: 'lp-letter', label: 'LP letter' },
  { value: 'exec-summary', label: 'Exec summary' },
]

export default function NarrativeToolbar({
  tone = 'board-ready',
  onToneChange,
  onGenerate,
  onSave,
  onApprove,
  onExport,
  loading = false,
  canEdit = false,
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <SelectInput label="Tone" value={tone} onChange={(event) => onToneChange?.(event.target.value)}>
        {TONES.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </SelectInput>
      {onGenerate ? (
        <Button variant="secondary" onClick={onGenerate} disabled={loading}>
          {loading ? 'Generating...' : 'Generate'}
        </Button>
      ) : null}
      {canEdit ? (
        <>
          <Button variant="ghost" onClick={onSave} disabled={loading}>
            Save Draft
          </Button>
          <Button variant="primary" onClick={onApprove} disabled={loading}>
            Approve
          </Button>
        </>
      ) : null}
      {onExport ? (
        <Button variant="ghost" onClick={onExport} disabled={loading}>
          Export PDF
        </Button>
      ) : null}
    </div>
  )
}
