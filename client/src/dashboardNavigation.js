const PORTAL_NAV_CONFIG = {
  manager: [
    {
      to: '/overview',
      label: 'Overview',
      icon: 'O',
      title: 'Overview Dashboard',
    },
    {
      to: '/review-hub',
      label: 'Review Hub',
      icon: 'R',
      title: 'Review Hub',
    },
    {
      to: '/submissions',
      label: 'Submissions',
      icon: 'S',
      title: 'Submission Tracking',
    },
    {
      to: '/analytics',
      label: 'Analytics',
      icon: 'A',
      title: 'ESG Analytics',
    },
    {
      to: '/alerts-risks',
      label: 'Alerts & Risks',
      icon: '!',
      title: 'Alerts & Risks',
    },
    {
      to: '/action-plans',
      label: 'Action Plans',
      icon: 'P',
      title: 'Action Plan Tracker',
    },
    {
      to: '/reports',
      label: 'Reports',
      icon: 'D',
      title: 'Reports',
    },
  ],
  investor: [
    {
      to: '/overview',
      label: 'Portfolio Dashboard',
      icon: 'P',
      title: 'Portfolio ESG Dashboard',
    },
    {
      to: '/analytics',
      label: 'ESG Metrics',
      icon: 'M',
      title: 'Detailed ESG Metrics',
    },
    {
      to: '/reports',
      label: 'Reports',
      icon: 'R',
      title: 'ESG Reports Library',
    },
  ],
  company: [
    {
      to: '/company/dashboard',
      label: 'Dashboard',
      icon: 'D',
      title: 'Submission Status & Progress',
    },
    {
      to: '/company/submission',
      label: 'ESG Data',
      icon: 'E',
      title: 'Complete ESG Data Entry',
    },
    {
      to: '/company/action-plans',
      label: 'Action Plans',
      icon: 'A',
      title: 'ESG Improvement Initiatives',
    },
    {
      to: '/company/historical',
      label: 'Historical Data',
      icon: 'H',
      title: 'Historical Submissions & YoY Reference',
    },
  ],
}

export function normalizeDashboardRole(role) {
  const value = String(role || '').toLowerCase()
  if (value === 'manager' || value === 'investor' || value === 'company') return value
  return 'manager'
}

export function getAllowedNavItems(role) {
  const normalizedRole = normalizeDashboardRole(role)
  return PORTAL_NAV_CONFIG[normalizedRole] || PORTAL_NAV_CONFIG.manager
}

export function getDefaultDashboardPath(role) {
  return getAllowedNavItems(role)[0]?.to || '/overview'
}

export function getDashboardTitle(pathname, role) {
  const navItems = getAllowedNavItems(role)
  const matched = navItems.find((item) => pathname.startsWith(item.to))
  if (matched) return matched.title

  const fallback = Object.values(PORTAL_NAV_CONFIG)
    .flat()
    .find((item) => pathname.startsWith(item.to))
  return fallback?.title || 'Overview Dashboard'
}

export const NAV_ITEMS = PORTAL_NAV_CONFIG.manager
export { PORTAL_NAV_CONFIG }
