import { NavLink } from 'react-router-dom'

export default function Sidebar({ collapsed, items = [], mobileOpen, onToggle, onNavigate }) {
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
      <div className="sidebar-top">
        <span className="sidebar-title">Navigation</span>
        <button className="sidebar-toggle" type="button" onClick={onToggle}>
          {collapsed ? '>>' : '<<'}
        </button>
      </div>
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
