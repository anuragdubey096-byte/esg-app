import { useEffect, useState } from 'react'
import Dashboard from './Dashboard'
import LoginPage from './LoginPage'
import { API_BASE_URL } from './lib/api'

export default function App() {
  const [user, setUser] = useState(null)
  const [checkingSession, setCheckingSession] = useState(true)

  useEffect(() => {
    let active = true
    fetch(`${API_BASE_URL}/auth/me`)
      .then((response) => (response.ok ? response.json() : null))
      .then((sessionUser) => {
        if (active && sessionUser) setUser(sessionUser)
      })
      .finally(() => {
        if (active) setCheckingSession(false)
      })
    return () => { active = false }
  }, [])

  const logout = async () => {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST' })
    } finally {
      setUser(null)
      window.sessionStorage.clear()
    }
  }

  if (checkingSession) {
    return <div className="route-loading-state" role="status">Restoring secure session...</div>
  }

  if (user) {
    return <Dashboard user={user} onLogout={logout} />
  }

  return <LoginPage onLogin={setUser} />
}
