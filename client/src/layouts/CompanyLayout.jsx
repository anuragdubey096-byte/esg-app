import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import TopNavbar from '../components/TopNavbar'
import { Button } from '../components/ui'

// Company (Portfolio Company) navigation
const COMPANY_NAV_ITEMS = [
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
]

export default function CompanyLayout({ user, onLogout }) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const location = useLocation()

  const pageTitle = useMemo(() => {
    const matched = COMPANY_NAV_ITEMS.find((item) => location.pathname.startsWith(item.to))
    return matched?.title || 'Company Portal'
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
        items={COMPANY_NAV_ITEMS}
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
