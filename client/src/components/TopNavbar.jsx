import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useExperience } from '../contexts/ExperienceContext'
import { useOptionalLiveUpdates } from '../contexts/LiveUpdatesContext'
import { API_BASE_URL } from '../lib/api'
import { Button } from './ui'

function formatRoleLabel(role) {
  const value = String(role || 'manager').toLowerCase()
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function normalizeSearchResults(payload) {
  if (Array.isArray(payload)) return payload
  if (payload && Array.isArray(payload.results)) return payload.results
  return []
}

function SearchResult({ result, onSelect }) {
  return (
    <button
      type="button"
      className="search-result"
      onMouseDown={(event) => event.preventDefault()}
      onClick={() => onSelect(result)}
    >
      <span className="search-result-type">{result.type || 'Result'}</span>
      <strong className="search-result-title">{result.title}</strong>
      {result.subtitle ? <span className="search-result-subtitle">{result.subtitle}</span> : null}
    </button>
  )
}

export default function TopNavbar({ title, user, onLogout, onMenuToggle }) {
  const navigate = useNavigate()
  const { appearance, activeBrand, toggleAppearance } = useExperience()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const searchRef = useRef(null)
  const notificationsRef = useRef(null)
  const liveUpdates = useOptionalLiveUpdates()

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (searchRef.current && !searchRef.current.contains(event.target)) {
        setSearchOpen(false)
      }
      if (notificationsRef.current && !notificationsRef.current.contains(event.target)) {
        setNotificationsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [])

  useEffect(() => {
    const trimmed = query.trim()
    if (trimmed.length < 2) {
      setResults([])
      setSearchLoading(false)
      setSearchError('')
      return
    }

    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setSearchLoading(true)
      setSearchError('')
      try {
        const response = await fetch(`${API_BASE_URL}/search/global?q=${encodeURIComponent(trimmed)}&limit=6`, {
          headers: {
            'x-user-role': user?.role || '',
            'x-user-email': user?.email || '',
          },
          signal: controller.signal,
        })
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}))
          throw new Error(payload.detail || 'Search failed')
        }
        const payload = await response.json()
        if (!controller.signal.aborted) {
          setResults(normalizeSearchResults(payload))
          setSearchOpen(true)
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setResults([])
          setSearchError(error.message || 'Search failed')
          setSearchOpen(true)
        }
      } finally {
        if (!controller.signal.aborted) {
          setSearchLoading(false)
        }
      }
    }, 240)

    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [query, user?.email, user?.role])

  const resultSummary = useMemo(() => {
    if (searchLoading) return 'Searching...'
    if (searchError) return searchError
    if (!query.trim()) return 'Search across pages, companies, and action plans.'
    if (!results.length) return 'No matches found.'
    return `${results.length} result${results.length === 1 ? '' : 's'}`
  }, [query, results.length, searchError, searchLoading])

  const handleSelectResult = (result) => {
    const nextPath = result.path || result.href || '/'
    setQuery('')
    setResults([])
    setSearchOpen(false)
    navigate(nextPath)
  }

  const handleNotificationsToggle = () => {
    const nextOpen = !notificationsOpen
    setNotificationsOpen(nextOpen)
    if (nextOpen) {
      liveUpdates?.markNotificationsRead?.()
    }
  }

  const connectionLabel = {
    connected: 'Live',
    connecting: 'Connecting',
    disconnected: 'Reconnecting',
    error: 'Offline',
    idle: 'Idle',
  }[liveUpdates?.connectionState || 'idle']

  return (
    <header className="top-navbar">
      <div className="brand-block">
        <Button
          variant="ghost"
          className="ui-nav-menu-button"
          type="button"
          onClick={onMenuToggle}
          aria-label="Open navigation"
        >
          Menu
        </Button>
        <div className="brand-logo">{activeBrand.shortName}</div>
        <div className="brand-copy">
          <h1>{activeBrand.label}</h1>
          <p>{title} | {activeBrand.tagline}</p>
        </div>
      </div>

      <div className="top-actions">
        <div className="experience-controls">
          <Button
            variant="secondary"
            type="button"
            onClick={toggleAppearance}
            className="theme-toggle"
          >
            {appearance === 'dark' ? 'Light mode' : 'Dark mode'}
          </Button>
        </div>

        <div className={`search-shell ${searchOpen ? 'open' : ''}`} ref={searchRef}>
          <label className="search-wrap" htmlFor="global-search">
            <span>Search</span>
            <input
              id="global-search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setSearchOpen(true)
              }}
              onFocus={() => setSearchOpen(true)}
              placeholder="Search companies, pages, plans..."
              autoComplete="off"
            />
          </label>

          {searchOpen ? (
            <div className="search-dropdown" role="listbox" aria-label="Global search results">
              <div className="search-summary">{resultSummary}</div>
              <div className="search-results">
                {results.map((result) => (
                  <SearchResult key={`${result.type || 'result'}-${result.path || result.title}`} result={result} onSelect={handleSelectResult} />
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="relative" ref={notificationsRef}>
          <Button
            variant="secondary"
            className="ui-icon-button"
            type="button"
            aria-label="Notifications"
            onClick={handleNotificationsToggle}
          >
            N
            <span className={`dot ${liveUpdates?.unreadCount ? 'opacity-100' : 'opacity-0'}`} />
          </Button>

          {notificationsOpen ? (
            <div className="absolute right-0 top-14 z-50 w-[min(420px,calc(100vw-2rem))] rounded-3xl border border-slate-200 bg-white p-4 shadow-2xl">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm ui-text-strong text-[color:var(--ui-text-strong)]">Activity Feed</p>
                  <p className="text-xs uppercase tracking-wide text-slate-500">{connectionLabel}</p>
                </div>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs ui-text-strong text-slate-600">
                  {liveUpdates?.recentEvents?.length || 0} recent
                </span>
              </div>

              <div className="mt-4 max-h-[420px] space-y-3 overflow-y-auto pr-1">
                {(liveUpdates?.recentEvents || []).length ? (
                  liveUpdates.recentEvents.map((item) => (
                    <article key={item.id} className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm ui-text-strong text-[color:var(--ui-text-strong)]">{item.title}</p>
                          <p className="mt-1 text-sm text-[color:var(--ui-text)]">{item.message}</p>
                        </div>
                        <span className="text-xs uppercase tracking-wide text-slate-500">
                          {new Date(item.created_at || Date.now()).toLocaleTimeString()}
                        </span>
                      </div>
                    </article>
                  ))
                ) : (
                  <p className="text-sm text-slate-500">No live events yet.</p>
                )}
              </div>
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

        <Button variant="secondary" type="button" onClick={onLogout}>
          Logout
        </Button>
      </div>
    </header>
  )
}
