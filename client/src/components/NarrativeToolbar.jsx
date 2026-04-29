import { Button, SelectInput } from './ui'
import { DEFAULT_REPORT_VIEW, NARRATIVE_TONE_OPTIONS } from '../lib/portalOptions'

export default function NarrativeToolbar({
  tone = DEFAULT_REPORT_VIEW.narrativeTone,
  onToneChange,
  onGenerate,
  onSave,
  onApprove,
  onExport,
  loading = false,
  canEdit = false,
  generateLabel = 'Generate',
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <SelectInput label="Tone" value={tone} onChange={(event) => onToneChange?.(event.target.value)}>
        {NARRATIVE_TONE_OPTIONS.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </SelectInput>
      {onGenerate ? (
        <Button variant="secondary" onClick={onGenerate} disabled={loading}>
          {loading ? 'Generating...' : generateLabel}
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
