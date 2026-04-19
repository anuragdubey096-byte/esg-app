import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import {
  applyThemeTokens,
  BRAND_PROFILES,
  DEFAULT_APPEARANCE,
  DEFAULT_BRAND_ID,
  getAppearance,
  getBrandProfile,
  loadExperienceState,
  persistExperienceState,
} from '../lib/experience'

const ExperienceContext = createContext(null)

export function ExperienceProvider({ children }) {
  const [appearance, setAppearance] = useState(() => loadExperienceState().appearance || DEFAULT_APPEARANCE)
  const [brandId, setBrandId] = useState(() => loadExperienceState().brandId || DEFAULT_BRAND_ID)

  const activeBrand = useMemo(() => getBrandProfile(brandId), [brandId])
  const activeAppearance = getAppearance(appearance)
  const brandOptions = useMemo(() => BRAND_PROFILES.map((profile) => ({
    id: profile.id,
    label: profile.label,
    shortName: profile.shortName,
  })), [])

  useLayoutEffect(() => {
    applyThemeTokens(brandId, activeAppearance)
  }, [activeAppearance, brandId])

  useEffect(() => {
    persistExperienceState({
      appearance: activeAppearance,
      brandId,
    })
  }, [activeAppearance, brandId])

  const value = useMemo(() => ({
    appearance: activeAppearance,
    brandId,
    activeBrand,
    brandOptions,
    setAppearance,
    setBrandId,
    toggleAppearance: () => setAppearance((current) => (getAppearance(current) === 'dark' ? 'light' : 'dark')),
  }), [activeAppearance, activeBrand, brandId, brandOptions])

  return <ExperienceContext.Provider value={value}>{children}</ExperienceContext.Provider>
}

export function useExperience() {
  const value = useContext(ExperienceContext)
  if (!value) {
    throw new Error('useExperience must be used within an ExperienceProvider')
  }
  return value
}
