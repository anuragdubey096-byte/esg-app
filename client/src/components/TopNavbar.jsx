import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useGlobalSearch from '../hooks/useGlobalSearch'
import AppIcon from './AppIcon'

function formatRoleLabel(role) {
  const value = String(role || 'manager').toLowerCase()
  return value.charAt(0).toUpperCase() + value.slice(1)
}

export default function TopNavbar({ title, user, onLogout, onMenuToggle }) {
  const navigate = useNavigate()
  const search = useGlobalSearch({ user, minChars: 2 })
  const [searchOpen, setSearchOpen] = useState(false)

  const visibleResults = useMemo(() => (search.results || []).slice(0, 8), [search.results])

  const handlePickResult = (item) => {
    if (item?.path) {
      navigate(item.path)
      setSearchOpen(false)
      return
    }
    if (item?.type === 'ActionPlan') {
      navigate('/action-plans')
    } else if (item?.type === 'Company') {
      navigate('/submissions')
    }
    setSearchOpen(false)
  }

  return (
    <header className="top-navbar">
      <div className="brand-block">
        <button className="menu-button" type="button" onClick={onMenuToggle} aria-label="Open navigation">
          <AppIcon name="menu" size={20} />
        </button>
        <div className="page-heading">
          <nav className="breadcrumbs" aria-label="Breadcrumb">
            <span>Workspace</span>
            <span aria-hidden="true">/</span>
            <span aria-current="page">{title}</span>
          </nav>
          <h1>{title}</h1>
        </div>
      </div>

      <div className="top-actions">
        <div className="search-panel">
          <label className="search-wrap" htmlFor="global-search">
            <AppIcon name="search" size={17} />
            <input
              id="global-search"
              placeholder="Search company, metric, report..."
              value={search.query}
              onChange={(event) => {
                search.setQuery(event.target.value)
                setSearchOpen(true)
              }}
              onFocus={() => setSearchOpen(true)}
              onBlur={() => setTimeout(() => setSearchOpen(false), 120)}
            />
          </label>
          {searchOpen && search.query.trim().length >= 2 ? (
            <div className="search-results" role="listbox" aria-label="Global search results">
              {search.loading ? <p>Searching...</p> : null}
              {search.error ? <p>{search.error}</p> : null}
              {!search.loading && !search.error && visibleResults.length === 0 ? (
                <p>No matches found.</p>
              ) : null}
              {!search.loading && !search.error && visibleResults.length > 0 ? (
                <ul>
                  {visibleResults.map((item) => (
                    <li key={`${item.type}-${item.id}`}>
                      <button type="button" onMouseDown={() => handlePickResult(item)}>
                        <strong>{item.title || item.name || 'Result'}</strong>
                        <span>{item.subtitle || item.type || 'Result'}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>

        <button className="icon-button" type="button" aria-label="Notifications">
          <AppIcon name="notifications" size={19} />
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
