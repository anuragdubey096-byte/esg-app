import { STATUS_TONES } from '../../lib/foundation'

const STATUS_LABELS = {
  'resubmission requested': 'Resubmission Required',
}

export function normalizeStatusLabel(value) {
  const normalized = String(value || '').trim()
  if (!normalized) return 'Not Started'

  const key = normalized.toLowerCase()
  return STATUS_LABELS[key] || normalized.replace(/\s+/g, ' ')
}

export function getStatusTone(value) {
  const key = String(value || '').trim().toLowerCase()
  return STATUS_TONES[key] || 'neutral'
}
