import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useGlobalSearch from '../hooks/useGlobalSearch'
import AppIcon from './AppIcon'
import { API_BASE_URL } from '../lib/api'

function formatRoleLabel(role) {
  const value = String(role || 'manager').toLowerCase()
  return value.charAt(0).toUpperCase() + value.slice(1)
}

export default function TopNavbar({ title, user, onLogout, onMenuToggle }) {
  const navigate = useNavigate()
  const search = useGlobalSearch({ user, minChars: 2 })
  const [searchOpen, setSearchOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [notifications, setNotifications] = useState({ unread_count: 0, items: [] })

  useEffect(() => {
    let active = true
    const load = () => fetch(`${API_BASE_URL}/notifications`)
      .then((response) => (response.ok ? response.json() : { unread_count: 0, items: [] }))
      .then((payload) => { if (active) setNotifications(payload) })
      .catch(() => {})
    load()
    const timer = window.setInterval(load, 60000)
    return () => { active = false; window.clearInterval(timer) }
  }, [user?.id])

  const markNotificationRead = async (item) => {
    if (!item.read) await fetch(`${API_BASE_URL}/notifications/${item.id}/read`, { method: 'PATCH' })
    setNotifications((current) => ({
      unread_count: Math.max(0, current.unread_count - (item.read ? 0 : 1)),
      items: current.items.map((entry) => (entry.id === item.id ? { ...entry, read: true } : entry)),
    }))
    if (item.company_id) navigate('/submissions')
    setNotificationsOpen(false)
  }

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

        <div className="notification-center">
          <button className="icon-button" type="button" aria-label={`${notifications.unread_count} unread notifications`} onClick={() => setNotificationsOpen((value) => !value)}>
            <AppIcon name="notifications" size={19} />
            {notifications.unread_count ? <span className="dot" /> : null}
          </button>
          {notificationsOpen ? (
            <div className="notification-popover" role="dialog" aria-label="Notifications">
              <div className="notification-popover-heading"><strong>Notifications</strong><span>{notifications.unread_count} unread</span></div>
              {notifications.items.length ? (
                <ul>
                  {notifications.items.slice(0, 12).map((item) => (
                    <li key={item.id}>
                      <button type="button" className={item.read ? '' : 'unread'} onClick={() => markNotificationRead(item)}>
                        <strong>{item.title}</strong>
                        <span>{item.message}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : <p>No notifications yet.</p>}
            </div>
          ) : null}
        </div>

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
