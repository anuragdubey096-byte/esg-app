import { getStatusTone, normalizeStatusLabel } from './ui/status'

export default function StatusBadge({ value }) {
  const tone = getStatusTone(value)
  const label = normalizeStatusLabel(value)
  return <span className={`status-badge status-${tone}`}>{label}</span>
}
