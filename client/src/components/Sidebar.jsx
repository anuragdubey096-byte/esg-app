import { NavLink } from 'react-router-dom'
import { useExperience } from '../contexts/ExperienceContext'
import { Button } from './ui'

export default function Sidebar({ collapsed, items = [], mobileOpen, onToggle, onNavigate }) {
  const { activeBrand } = useExperience()

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
      <div className="sidebar-top">
        <div className="sidebar-brand">
          <span className="sidebar-brand-mark">{activeBrand.shortName}</span>
          {!collapsed ? (
            <div className="sidebar-brand-copy">
              <span className="sidebar-brand-name">{activeBrand.label}</span>
              <span className="sidebar-brand-tagline">{activeBrand.tagline}</span>
            </div>
          ) : null}
        </div>
        <Button variant="secondary" className="sidebar-toggle" type="button" onClick={onToggle}>
          {collapsed ? '>>' : '<<'}
        </Button>
      </div>
      {!collapsed ? <span className="sidebar-title sidebar-title-spaced">Navigation</span> : null}
      <nav className="sidebar-nav" aria-label="Primary">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            onClick={onNavigate}
          >
            <span className="sidebar-icon">{item.icon}</span>
            {!collapsed ? <span>{item.label}</span> : null}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
