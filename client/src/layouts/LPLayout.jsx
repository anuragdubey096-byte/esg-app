import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import SkipLink from '../components/SkipLink'
import Sidebar from '../components/Sidebar'
import TopNavbar from '../components/TopNavbar'
import { Button } from '../components/ui'
import { getAllowedNavItems } from '../dashboardNavigation'

export default function LPLayout({ user, onLogout }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const location = useLocation()
  const navItems = useMemo(
    () =>
      getAllowedNavItems('investor').map((item) => ({
        ...item,
        to:
          item.to === '/overview'
            ? '/lp/dashboard'
            : item.to === '/analytics'
              ? '/lp/metrics'
              : item.to === '/reports'
                ? '/lp/reports'
                : item.to,
      })),
    []
  )

  const pageTitle = useMemo(() => {
    const matched = navItems.find((item) => location.pathname.startsWith(item.to))
    return matched?.title || 'Investor Portal'
  }, [location.pathname, navItems])

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
      <SkipLink targetId="primary-content" />
      <Sidebar
        collapsed={collapsed}
        items={navItems}
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
        <main id="primary-content" tabIndex="-1" className="page-container">
          <Outlet context={{ user }} />
        </main>
      </div>
    </div>
  )
}
