import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import TopNavbar from '../components/TopNavbar'
import { Button } from '../components/ui'

// LP-specific navigation
const LP_NAV_ITEMS = [
  {
    to: '/lp/dashboard',
    label: 'Portfolio Dashboard',
    icon: 'P',
    title: 'Portfolio ESG Dashboard',
  },
  {
    to: '/lp/metrics',
    label: 'ESG Metrics',
    icon: 'M',
    title: 'Detailed ESG Metrics',
  },
  {
    to: '/lp/reports',
    label: 'Reports',
    icon: 'R',
    title: 'ESG Reports Library',
  },
]

export default function LPLayout({ user, onLogout }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const location = useLocation()

  const pageTitle = useMemo(() => {
    const matched = LP_NAV_ITEMS.find((item) => location.pathname.startsWith(item.to))
    return matched?.title || 'Limited Partner Portal'
  }, [location.pathname])

  useEffect(() => {
    setMobileNavOpen(false)
  }, [location.pathname])

  useLayoutEffect(() => {
    const pageContainer = document.querySelector('.page-container')
    if (pageContainer) {
      pageContainer.scrollTop = 0
    }
    window.scrollTo(0, 0)
  }, [location.pathname])

  const toggleSidebar = () => {
    const isMobileView = typeof window !== 'undefined' && window.matchMedia('(max-width: 960px)').matches
    if (isMobileView) {
      setCollapsed(false)
      setMobileNavOpen((current) => !current)
      return
    }
    setCollapsed((current) => !current)
  }

  return (
    <div className={`admin-shell ${collapsed ? 'collapsed' : ''}`}>
      <Sidebar
        collapsed={collapsed}
        items={LP_NAV_ITEMS}
        mobileOpen={mobileNavOpen}
        onToggle={toggleSidebar}
        onNavigate={() => setMobileNavOpen(false)}
      />
      <Button
        type="button"
        variant="ghost"
        className={`mobile-backdrop ui-backdrop-button ${mobileNavOpen ? 'visible' : ''}`}
        aria-label="Close navigation"
        onClick={() => setMobileNavOpen(false)}
      />
      <div className="admin-main">
        <TopNavbar title={pageTitle} user={user} onLogout={onLogout} onMenuToggle={toggleSidebar} />
        <main className="page-container">
          <Outlet context={{ user }} />
        </main>
      </div>
    </div>
  )
}
