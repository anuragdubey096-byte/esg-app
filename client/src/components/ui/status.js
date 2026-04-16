const STATUS_TONES = {
  'not started': 'neutral',
  'in progress': 'info',
  submitted: 'warning',
  'under review': 'warning',
  approved: 'success',
  rejected: 'danger',
  'resubmission required': 'caution',
  'resubmission requested': 'caution',
  pass: 'success',
  warning: 'warning',
  fail: 'danger',
  active: 'info',
  complete: 'success',
  closed: 'neutral',
  blocked: 'danger',
  invited: 'neutral',
  critical: 'danger',
  high: 'danger',
  medium: 'warning',
  low: 'success',
}

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

