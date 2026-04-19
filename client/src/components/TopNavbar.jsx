import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useExperience } from '../contexts/ExperienceContext'
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
  const { appearance, brandId, activeBrand, brandOptions, setBrandId, toggleAppearance } = useExperience()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const searchRef = useRef(null)

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (searchRef.current && !searchRef.current.contains(event.target)) {
        setSearchOpen(false)
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
          <label className="brand-select-wrap" htmlFor="brand-select">
            <span>Brand</span>
            <select
              id="brand-select"
              value={brandId}
              onChange={(event) => setBrandId(event.target.value)}
            >
              {brandOptions.map((brand) => (
                <option key={brand.id} value={brand.id}>
                  {brand.label}
                </option>
              ))}
            </select>
          </label>

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

        <Button variant="secondary" className="ui-icon-button" type="button" aria-label="Notifications">
          N
          <span className="dot" />
        </Button>

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
