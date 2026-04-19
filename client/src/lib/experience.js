import { BRAND_PROFILES, DEFAULT_APPEARANCE, DEFAULT_BRAND_ID } from './portalConfig'
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

export function getBrandProfile(brandId) {
  return BRAND_PROFILES.find((profile) => profile.id === brandId) || BRAND_PROFILES[0]
}

export function getAppearance(value) {
  return String(value || '').toLowerCase() === 'dark' ? 'dark' : 'light'
}

export function loadExperienceState() {
  const stored = safeReadJson(EXPERIENCE_STORAGE_KEY, null)
  const appearance = getAppearance(stored?.appearance)
  const brandId = BRAND_PROFILES.some((profile) => profile.id === stored?.brandId)
    ? stored.brandId
    : DEFAULT_BRAND_ID

  return {
    appearance,
    brandId,
  }
}

export function persistExperienceState(state) {
  safeWriteJson(EXPERIENCE_STORAGE_KEY, {
    appearance: getAppearance(state?.appearance),
    brandId: getBrandProfile(state?.brandId).id,
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
