const NAV_ITEMS = [
  {
    to: '/overview',
    label: 'Overview',
    icon: 'overview',
    group: 'Portfolio',
    title: 'Overview Dashboard',
    roles: ['manager', 'investor', 'company'],
  },
  {
    to: '/review-hub',
    label: 'Review Hub',
    icon: 'review',
    group: 'Workflows',
    title: 'Review Hub',
    roles: ['manager'],
  },
  {
    to: '/submissions',
    label: 'Submissions',
    icon: 'submissions',
    group: 'Workflows',
    title: 'Submission Tracking',
    roles: ['manager', 'investor', 'company'],
  },
  {
    to: '/analytics',
    label: 'Analytics',
    icon: 'analytics',
    group: 'Portfolio',
    title: 'ESG Analytics',
    roles: ['manager', 'investor'],
  },
  {
    to: '/alerts-risks',
    label: 'Alerts & Risks',
    icon: 'risks',
    group: 'Workflows',
    title: 'Alerts & Risks',
    roles: ['manager'],
  },
  {
    to: '/action-plans',
    label: 'Action Plans',
    icon: 'actions',
    group: 'Workflows',
    title: 'Action Plan Tracker',
    roles: ['manager', 'company'],
  },
  {
    to: '/reports',
    label: 'Reports',
    icon: 'reports',
    group: 'Reporting',
    title: 'Reports',
    roles: ['manager', 'investor', 'company'],
  },
  {
    to: '/lp-insights',
    label: 'LP Insights',
    icon: 'insights',
    group: 'Portfolio',
    title: 'LP Insights Dashboard',
    roles: ['investor'],
  },
  {
    to: '/newsletter-ops',
    label: 'Newsletter Ops',
    icon: 'newsletter',
    group: 'Reporting',
    title: 'Newsletter Operations',
    roles: ['manager', 'investor'],
  },
  {
    to: '/anomaly-intel',
    label: 'Anomaly Intel',
    icon: 'anomaly',
    group: 'Portfolio',
    title: 'Anomaly Intelligence',
    roles: ['manager', 'investor', 'company'],
  },
  {
    to: '/admin-settings',
    label: 'Cycle Config',
    icon: 'settings',
    group: 'Administration',
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

export function groupNavItems(items = []) {
  return items.reduce((groups, item) => {
    const label = item.group || 'Workspace'
    const existing = groups.find((group) => group.label === label)
    if (existing) {
      existing.items.push(item)
    } else {
      groups.push({ label, items: [item] })
    }
    return groups
  }, [])
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
