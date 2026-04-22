import { FOUNDATION_CONFIG } from './portalConfig'

const FOUNDATION_TYPOGRAPHY_DEFAULTS = {
  fontFamily: "'Inter', 'Segoe UI', Tahoma, sans-serif",
  caption: '12px',
  bodySm: '13px',
  body: '14px',
  section: '16px',
  display: '18px',
  bodyLineHeight: '1.45',
  headingLineHeight: '1.2',
}

const FOUNDATION_SPACING_DEFAULTS = {
  1: '4px',
  2: '8px',
  3: '12px',
  4: '16px',
  6: '24px',
  8: '32px',
  12: '48px',
}

const FOUNDATION_RADIUS_DEFAULTS = {
  sm: '10px',
  md: '12px',
  lg: '16px',
  control: '10px',
}

const FOUNDATION_SHADOW_DEFAULTS = {
  card: '0 10px 28px rgba(15, 23, 42, 0.08)',
  elevated: '0 24px 48px rgba(15, 23, 42, 0.1)',
  modal: '0 20px 64px rgba(15, 23, 42, 0.25)',
  stage: '0 28px 56px rgba(15, 23, 42, 0.14)',
  brandMark: '0 10px 24px rgba(15, 23, 42, 0.18)',
}

const FOUNDATION_EFFECTS_DEFAULTS = {
  panelGlowBlur: '14px',
}

const FOUNDATION_COMPONENT_SIZES_DEFAULTS = {
  buttonSpinner: '14px',
  miniLegendDot: '10px',
}

const FOUNDATION_LAYOUT_DEFAULTS = {
  pageMax: '1280px',
  pagePad: '32px',
}

const STATUS_TONES_DEFAULTS = {
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

const STATUS_COLORS_DEFAULTS = {
  'Not Started': '#94a3b8',
  'In Progress': '#0ea5e9',
  Submitted: '#f59e0b',
  'Under Review': '#8b5cf6',
  Approved: '#10b981',
  'Resubmission Requested': '#ef4444',
  Rejected: '#f97316',
}

const FOUNDATION_COLORS_DEFAULTS = {
  pageBackground: '#eef2f7',
  border: '#d7e0ea',
  surface: '#ffffff',
  surfaceMuted: '#f7f9fc',
  text: '#0f172a',
  textMuted: '#5b6b7f',
  brandPrimary: '#0f6d63',
  brandPrimaryHover: '#0c5e55',
  brandSecondary: '#2563eb',
  brandAccent: '#0ea5e9',
  brandSuccess: '#10b981',
  brandWarning: '#d97706',
  brandDanger: '#ef4444',
  brandCaution: '#f59e0b',
}

const CHART_COLORS_DEFAULTS = {
  neutral: '#94a3b8',
  info: '#0ea5e9',
  warning: '#f59e0b',
  success: '#10b981',
  danger: '#ef4444',
  caution: '#f97316',
  brand: '#2563eb',
  brandDark: '#0f6d63',
  environmental: '#1D9E75',
  social: '#7F77DD',
  governance: '#BA7517',
  combined: '#378ADD',
  scope1: '#ef4444',
  scope2: '#0ea5e9',
  scope3: '#f59e0b',
  renewable: '#10b981',
  women: '#10b981',
  men: '#0ea5e9',
  nonBinary: '#c084fc',
  pink: '#ec4899',
  purple: '#7c3aed',
  violet: '#a855f7',
}

const FOUNDATION_CONFIG_COLORS = FOUNDATION_CONFIG.colors || {}

export const FOUNDATION_TYPOGRAPHY = {
  ...FOUNDATION_TYPOGRAPHY_DEFAULTS,
  ...(FOUNDATION_CONFIG.typography || {}),
}

export const FOUNDATION_SPACING = {
  ...FOUNDATION_SPACING_DEFAULTS,
  ...(FOUNDATION_CONFIG.spacing || {}),
}

export const FOUNDATION_RADIUS = {
  ...FOUNDATION_RADIUS_DEFAULTS,
  ...(FOUNDATION_CONFIG.radius || {}),
}

export const FOUNDATION_SHADOWS = {
  ...FOUNDATION_SHADOW_DEFAULTS,
  ...(FOUNDATION_CONFIG.shadows || {}),
}

export const FOUNDATION_EFFECTS = {
  ...FOUNDATION_EFFECTS_DEFAULTS,
  ...(FOUNDATION_CONFIG.effects || {}),
}

export const FOUNDATION_COMPONENT_SIZES = {
  ...FOUNDATION_COMPONENT_SIZES_DEFAULTS,
  ...(FOUNDATION_CONFIG.componentSizes || {}),
}

export const FOUNDATION_LAYOUT = {
  ...FOUNDATION_LAYOUT_DEFAULTS,
  ...(FOUNDATION_CONFIG.layout || {}),
}

export const STATUS_TONES = {
  ...STATUS_TONES_DEFAULTS,
  ...(FOUNDATION_CONFIG_COLORS.statusTones || {}),
}

export const STATUS_COLORS = {
  ...STATUS_COLORS_DEFAULTS,
  ...(FOUNDATION_CONFIG_COLORS.statusColors || {}),
}

export const FOUNDATION_COLORS = {
  ...FOUNDATION_COLORS_DEFAULTS,
  ...(FOUNDATION_CONFIG_COLORS.foundationColors || {}),
}

export const CHART_COLORS = {
  ...CHART_COLORS_DEFAULTS,
  ...(FOUNDATION_CONFIG_COLORS.chartColors || {}),
}

export const PILLAR_COLORS = {
  E: CHART_COLORS.environmental,
  S: CHART_COLORS.social,
  G: CHART_COLORS.governance,
  ...(FOUNDATION_CONFIG_COLORS.pillarColors || {}),
}
