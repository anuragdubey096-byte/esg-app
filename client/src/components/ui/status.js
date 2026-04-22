import { STATUS_TONES } from '../../lib/foundation'
import { toTitleCaseWords } from '../../lib/text'

const STATUS_LABELS = {
  'not started': 'Not Started',
  'in progress': 'In Progress',
  submitted: 'Submitted',
  'under review': 'Under Review',
  approved: 'Approved',
  rejected: 'Rejected',
  'resubmission requested': 'Resubmission Required',
  'resubmission required': 'Resubmission Required',
}

export function normalizeStatusLabel(value, { fallback = 'preserve' } = {}) {
  const normalized = String(value || '').trim()
  if (!normalized) return 'Not Started'

  const key = normalized.toLowerCase()
  if (STATUS_LABELS[key]) return STATUS_LABELS[key]
  return fallback === 'title' ? toTitleCaseWords(normalized) : normalized.replace(/\s+/g, ' ')
}

export function normalizeStatusText(value) {
  return normalizeStatusLabel(value, { fallback: 'title' })
}

export function getStatusTone(value) {
  const key = String(value || '').trim().toLowerCase()
  return STATUS_TONES[key] || 'neutral'
}
