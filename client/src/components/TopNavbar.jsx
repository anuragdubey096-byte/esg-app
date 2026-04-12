function formatRoleLabel(role) {
  const value = String(role || 'manager').toLowerCase()
  return value.charAt(0).toUpperCase() + value.slice(1)
}

export default function TopNavbar({ title, user, onLogout, onMenuToggle }) {
  return (
    <header className="top-navbar">
      <div className="brand-block">
        <button className="menu-button" type="button" onClick={onMenuToggle} aria-label="Open navigation">
          Menu
        </button>
        <div className="brand-logo">GL</div>
        <div>
          <h1>GreenLedger</h1>
          <p>{title} | Investment Portfolio Intelligence Platform</p>
        </div>
      </div>

      <div className="top-actions">
        <label className="search-wrap" htmlFor="global-search">
          <span>Search</span>
          <input id="global-search" placeholder="Search company, metric, report..." />
        </label>

        <button className="icon-button" type="button" aria-label="Notifications">
          N
          <span className="dot" />
        </button>

        <div className="profile-pill">
          <span className="avatar">{(user?.name || 'A').slice(0, 1).toUpperCase()}</span>
          <div>
            <p>{user?.name || 'Admin User'}</p>
            <small>{formatRoleLabel(user?.role)}</small>
          </div>
        </div>

        <button className="logout-button" type="button" onClick={onLogout}>Logout</button>
      </div>
    </header>
  )
}
