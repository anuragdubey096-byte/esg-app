import { NavLink } from 'react-router-dom'
import { groupNavItems } from '../dashboardNavigation'
import AppIcon from './AppIcon'

export default function Sidebar({ collapsed, items = [], mobileOpen, onToggle, onNavigate }) {
  const groups = groupNavItems(items)

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
      <div className="sidebar-top">
        <div className="sidebar-brand" aria-label="GreenLedger workspace">
          <span className="sidebar-brand-mark">GL</span>
          {!collapsed ? (
            <span>
              <strong>GreenLedger</strong>
              <small>ESG Intelligence</small>
            </span>
          ) : null}
        </div>
        <button
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          className="sidebar-toggle"
          type="button"
          onClick={onToggle}
        >
          <AppIcon name={collapsed ? 'expand' : 'collapse'} size={18} />
        </button>
      </div>
      <nav className="sidebar-nav" aria-label="Primary">
        {groups.map((group) => (
          <section
            aria-label={collapsed ? group.label : undefined}
            aria-labelledby={collapsed ? undefined : `nav-${group.label}`}
            className="sidebar-group"
            key={group.label}
          >
            {!collapsed ? <h2 id={`nav-${group.label}`}>{group.label}</h2> : null}
            <div className="sidebar-group-links">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  title={collapsed ? item.label : undefined}
                  className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
                  onClick={onNavigate}
                >
                  <span className="sidebar-icon"><AppIcon name={item.icon} size={19} /></span>
                  {!collapsed ? <span>{item.label}</span> : null}
                </NavLink>
              ))}
            </div>
          </section>
        ))}
      </nav>
    </aside>
  )
}
