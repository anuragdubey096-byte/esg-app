import { useState } from 'react'
import Dashboard from './Dashboard'
import LoginPage from './LoginPage'

export default function App() {
  const [user, setUser] = useState(null)

  if (user) {
    return <Dashboard user={user} onLogout={() => setUser(null)} />
  }

  return <LoginPage onLogin={setUser} />
}
