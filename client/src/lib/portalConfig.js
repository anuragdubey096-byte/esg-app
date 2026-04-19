import portalConfig from './portalConfig.json'

export const PORTAL_CONFIG = portalConfig

export const EXPERIENCE_CONFIG = portalConfig.experience
export const BRAND_PROFILES = EXPERIENCE_CONFIG.brandProfiles
export const DEFAULT_BRAND_ID = EXPERIENCE_CONFIG.defaultBrandId
export const DEFAULT_APPEARANCE = EXPERIENCE_CONFIG.defaultAppearance

export const SEARCH_CONFIG = portalConfig.search
export const PORTAL_SEARCH_PAGE_CATALOG = SEARCH_CONFIG.pageCatalog
export const SEARCH_RANKING = SEARCH_CONFIG.ranking
