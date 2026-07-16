import { describe, expect, it } from 'vitest'
import {
  getAllowedNavItems,
  getDefaultDashboardPath,
  normalizeDashboardRole,
} from './dashboardNavigation'

const pathsFor = (role) => getAllowedNavItems(role).map((item) => item.to)

describe('dashboard role routing', () => {
  it('limits manager routes to the manager workspace', () => {
    expect(pathsFor('manager')).toEqual([
      '/overview', '/review-hub', '/submissions', '/analytics', '/strategy',
      '/alerts-risks', '/action-plans', '/reports', '/newsletter-ops',
      '/anomaly-intel', '/portfolio-onboarding', '/admin-settings',
    ])
  })

  it('limits investor routes to portfolio analysis features', () => {
    expect(pathsFor('INVESTOR')).toEqual([
      '/overview', '/submissions', '/analytics', '/strategy', '/reports',
      '/lp-insights', '/newsletter-ops', '/anomaly-intel',
    ])
  })

  it('limits company routes to its reporting workflow', () => {
    expect(pathsFor('company')).toEqual([
      '/overview', '/submissions', '/analytics', '/action-plans', '/reports',
      '/anomaly-intel',
    ])
  })

  it('uses a safe manager fallback and overview landing route', () => {
    expect(normalizeDashboardRole('unexpected-role')).toBe('manager')
    expect(getDefaultDashboardPath('manager')).toBe('/overview')
    expect(getDefaultDashboardPath('investor')).toBe('/overview')
    expect(getDefaultDashboardPath('company')).toBe('/overview')
  })
})
