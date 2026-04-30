import { useEffect, useMemo, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import AgentChat from '../components/AgentChat/AgentChat'
import Sidebar from '../components/Sidebar'
import TopNavbar from '../components/TopNavbar'
import { getDashboardTitle } from '../dashboardNavigation'

export default function AdminLayout({ user, onLogout, navItems }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const location = useLocation()

  const pageTitle = useMemo(() => {
    return getDashboardTitle(location.pathname, user?.role)
  }, [location.pathname, user?.role])

  useEffect(() => {
    setMobileNavOpen(false)
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
        items={navItems}
        mobileOpen={mobileNavOpen}
        onToggle={toggleSidebar}
        onNavigate={() => setMobileNavOpen(false)}
      />
      <button
        type="button"
        className={`mobile-backdrop ${mobileNavOpen ? 'visible' : ''}`}
        aria-label="Close navigation"
        onClick={() => setMobileNavOpen(false)}
      />
      <div className="admin-main">
        <TopNavbar title={pageTitle} user={user} onLogout={onLogout} onMenuToggle={toggleSidebar} />
        <main className="page-container">
          <Outlet context={{ user }} />
        </main>
        <AgentChat user={user} />
      </div>
    </div>
  )
}
