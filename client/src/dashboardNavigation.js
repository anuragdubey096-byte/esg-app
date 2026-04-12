const NAV_ITEMS = [
  {
    to: '/overview',
    label: 'Overview',
    icon: 'O',
    title: 'Overview Dashboard',
    roles: ['manager', 'investor', 'company'],
  },
  {
    to: '/review-hub',
    label: 'Review Hub',
    icon: 'R',
    title: 'Review Hub',
    roles: ['manager'],
  },
  {
    to: '/submissions',
    label: 'Submissions',
    icon: 'S',
    title: 'Submission Tracking',
    roles: ['manager', 'company'],
  },
  {
    to: '/analytics',
    label: 'Analytics',
    icon: 'A',
    title: 'ESG Analytics',
    roles: ['manager', 'investor'],
  },
  {
    to: '/alerts-risks',
    label: 'Alerts & Risks',
    icon: '!',
    title: 'Alerts & Risks',
    roles: ['manager'],
  },
  {
    to: '/action-plans',
    label: 'Action Plans',
    icon: 'P',
    title: 'Action Plan Tracker',
    roles: ['manager', 'company'],
  },
  {
    to: '/reports',
    label: 'Reports',
    icon: 'D',
    title: 'Reports',
    roles: ['manager', 'investor', 'company'],
  },
  {
    to: '/admin-settings',
    label: 'Cycle Config',
    icon: 'T',
    title: 'Reporting Cycle Configuration',
    roles: ['manager'],
  },
]

export function normalizeDashboardRole(role) {
  const value = String(role || '').toLowerCase()
  if (value === 'manager' || value === 'investor' || value === 'company') return value
  return 'manager'
}

export function getAllowedNavItems(role) {
  const normalizedRole = normalizeDashboardRole(role)
  return NAV_ITEMS.filter((item) => item.roles.includes(normalizedRole))
}

export function getDefaultDashboardPath(role) {
  return getAllowedNavItems(role)[0]?.to || '/overview'
}

export function getDashboardTitle(pathname, role) {
  const navItems = getAllowedNavItems(role)
  const matched = navItems.find((item) => pathname.startsWith(item.to))
  if (matched) return matched.title

  const fallback = NAV_ITEMS.find((item) => pathname.startsWith(item.to))
  return fallback?.title || 'Overview Dashboard'
}

export { NAV_ITEMS }
