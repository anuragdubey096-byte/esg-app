import { BRAND_PROFILES, DEFAULT_APPEARANCE, DEFAULT_BRAND_ID } from './portalConfig'
import {
  FOUNDATION_COMPONENT_SIZES,
  FOUNDATION_EFFECTS,
  FOUNDATION_LAYOUT,
  FOUNDATION_RADIUS,
  FOUNDATION_SHADOWS,
  FOUNDATION_SPACING,
  FOUNDATION_TYPOGRAPHY,
} from './foundation'
export { BRAND_PROFILES, DEFAULT_APPEARANCE, DEFAULT_BRAND_ID } from './portalConfig'

const EXPERIENCE_STORAGE_KEY = 'esg.experience.v1'
const FILTER_PRESET_STORAGE_PREFIX = 'esg.filter-presets.v1'
const LAST_FILTER_STORAGE_PREFIX = 'esg.last-filters.v1'

function canUseStorage() {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function safeReadJson(storageKey, fallback) {
  if (!canUseStorage()) return fallback
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return fallback
    return JSON.parse(raw)
  } catch {
    return fallback
  }
}

function safeWriteJson(storageKey, value) {
  if (!canUseStorage()) return
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(value))
  } catch {
    // Ignore storage errors. The UI still works without persistence.
  }
}

function applyCssVariables(root, variables) {
  Object.entries(variables).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    root.style.setProperty(key, String(value))
  })
}

export function getBrandProfile(brandId) {
  return BRAND_PROFILES.find((profile) => profile.id === brandId) || BRAND_PROFILES[0]
}

export function getAppearance(value) {
  return String(value || '').toLowerCase() === 'dark' ? 'dark' : 'light'
}

export function loadExperienceState() {
  const stored = safeReadJson(EXPERIENCE_STORAGE_KEY, null)
  const appearance = getAppearance(stored?.appearance)

  return {
    appearance,
    brandId: DEFAULT_BRAND_ID,
  }
}

export function persistExperienceState(state) {
  safeWriteJson(EXPERIENCE_STORAGE_KEY, {
    appearance: getAppearance(state?.appearance),
    brandId: DEFAULT_BRAND_ID,
  })
}

export function buildThemeTokens(brandId, appearance) {
  const profile = getBrandProfile(brandId)
  const appearanceKey = getAppearance(appearance)
  return profile?.themeTokens?.[appearanceKey] || getBrandProfile(DEFAULT_BRAND_ID)?.themeTokens?.[appearanceKey] || {}
}

export function applyThemeTokens(brandId, appearance) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const theme = getAppearance(appearance)
  const profile = getBrandProfile(brandId)
  const tokens = buildThemeTokens(profile.id, theme)

  applyCssVariables(root, {
    '--ui-font-family-base': FOUNDATION_TYPOGRAPHY.fontFamily,
    '--ui-font-caption-base': FOUNDATION_TYPOGRAPHY.caption,
    '--ui-font-body-sm-base': FOUNDATION_TYPOGRAPHY.bodySm,
    '--ui-font-body-base': FOUNDATION_TYPOGRAPHY.body,
    '--ui-font-section-base': FOUNDATION_TYPOGRAPHY.section,
    '--ui-font-display-base': FOUNDATION_TYPOGRAPHY.display,
    '--ui-line-height-body-base': FOUNDATION_TYPOGRAPHY.bodyLineHeight,
    '--ui-line-height-heading-base': FOUNDATION_TYPOGRAPHY.headingLineHeight,
    '--ui-space-1-base': FOUNDATION_SPACING[1],
    '--ui-space-2-base': FOUNDATION_SPACING[2],
    '--ui-space-3-base': FOUNDATION_SPACING[3],
    '--ui-space-4-base': FOUNDATION_SPACING[4],
    '--ui-space-6-base': FOUNDATION_SPACING[6],
    '--ui-space-8-base': FOUNDATION_SPACING[8],
    '--ui-space-12-base': FOUNDATION_SPACING[12],
    '--ui-page-max-base': FOUNDATION_LAYOUT.pageMax,
    '--ui-page-pad-base': FOUNDATION_LAYOUT.pagePad,
    '--ui-radius-sm-base': FOUNDATION_RADIUS.sm,
    '--ui-radius-md-base': FOUNDATION_RADIUS.md,
    '--ui-radius-lg-base': FOUNDATION_RADIUS.lg,
    '--ui-control-radius-base': FOUNDATION_RADIUS.control,
    '--ui-shadow-card-base': FOUNDATION_SHADOWS.card,
    '--ui-shadow-elevated-base': FOUNDATION_SHADOWS.elevated,
    '--ui-shadow-modal-base': FOUNDATION_SHADOWS.modal,
    '--ui-shadow-stage-base': FOUNDATION_SHADOWS.stage,
    '--ui-shadow-brand-mark-base': FOUNDATION_SHADOWS.brandMark,
    '--ui-panel-glow-blur-base': FOUNDATION_EFFECTS.panelGlowBlur,
    '--ui-button-spinner-size-base': FOUNDATION_COMPONENT_SIZES.buttonSpinner,
    '--ui-mini-legend-dot-size-base': FOUNDATION_COMPONENT_SIZES.miniLegendDot,
  })

  root.dataset.theme = theme
  root.dataset.brand = profile.id
  root.style.colorScheme = theme
  Object.entries(tokens).forEach(([key, value]) => {
    root.style.setProperty(key, value)
  })
}

export function loadSavedFilterPresets(scope) {
  return safeReadJson(`${FILTER_PRESET_STORAGE_PREFIX}:${scope}`, [])
}

export function saveSavedFilterPresets(scope, presets) {
  safeWriteJson(`${FILTER_PRESET_STORAGE_PREFIX}:${scope}`, presets)
}

export function upsertSavedFilterPreset(scope, preset) {
  const presets = loadSavedFilterPresets(scope)
  const existingIndex = presets.findIndex((item) => item.id === preset.id)
  const nextPresets = existingIndex >= 0
    ? presets.map((item) => (item.id === preset.id ? preset : item))
    : [preset, ...presets]
  saveSavedFilterPresets(scope, nextPresets)
  return nextPresets
}

export function removeSavedFilterPreset(scope, presetId) {
  const presets = loadSavedFilterPresets(scope).filter((item) => item.id !== presetId)
  saveSavedFilterPresets(scope, presets)
  return presets
}

export function loadLastFilterState(scope) {
  return safeReadJson(`${LAST_FILTER_STORAGE_PREFIX}:${scope}`, null)
}

export function saveLastFilterState(scope, filters) {
  safeWriteJson(`${LAST_FILTER_STORAGE_PREFIX}:${scope}`, filters)
}

export function createFilterPresetId(prefix = 'preset') {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function sanitizeFilterPresetName(value) {
  return String(value || '').trim().replace(/\s+/g, ' ')
}
