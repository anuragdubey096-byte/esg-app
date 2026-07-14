import { useState } from 'react'
import LoginForm from './components/auth/LoginForm'
import LoginLayout from './components/auth/LoginLayout'
import { API_BASE_URL } from './lib/api'

const backendUrl = API_BASE_URL

export default function LoginPage({ onLogin }) {
  const initialResetToken = new URLSearchParams(window.location.search).get('reset_token') || ''
  const [resetToken, setResetToken] = useState(initialResetToken)
  const [newPassword, setNewPassword] = useState('')
  const [resetMessage, setResetMessage] = useState('')

  const completePasswordReset = async (event) => {
    event.preventDefault()
    setResetMessage('Updating password...')
    const response = await fetch(`${backendUrl}/auth/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: resetToken, new_password: newPassword }),
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      setResetMessage(payload.detail || 'Unable to reset password.')
      return
    }
    window.history.replaceState({}, '', window.location.pathname)
    setResetToken('')
    setNewPassword('')
    setResetMessage(payload.message || 'Password updated. Sign in now.')
  }
  const authenticate = async ({ email, password }) => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 20000)
    try {
      const response = await fetch(`${backendUrl}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        signal: controller.signal,
      })

      if (response.status === 401) {
        throw new Error('Invalid email or password')
      }

      if (!response.ok) {
        throw new Error('Unable to sign in right now. Please try again.')
      }

      const user = await response.json()
      return { user, mfaRequired: email.toLowerCase().includes('+mfa') }
    } catch (error) {
      if (error?.name === 'AbortError') {
        throw new Error('Sign in timed out. The server is taking too long to respond; please try again.')
      }
      const isNetworkError = error?.name === 'TypeError' || String(error?.message || '').includes('Failed to fetch')
      if (isNetworkError) {
        throw new Error('Database server is unreachable. Please start the backend and try again.')
      }
      throw error
    } finally {
      window.clearTimeout(timeoutId)
    }
  }

  const forgotPassword = async ({ email }) => {
    const response = await fetch(`${backendUrl}/auth/forgot-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || 'Unable to send reset instructions.')
    }

    const result = await response.json()
    return result.message || 'If an account exists, reset instructions have been sent.'
  }

  const ssoSignIn = async (provider) => {
    const response = await fetch(`${backendUrl}/auth/sso/${provider}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `Unable to sign in with ${provider}.`)
    }

    return response.json()
  }

  return (
    <LoginLayout>
      {resetToken ? (
        <form className="login-form" onSubmit={completePasswordReset}>
          <h2>Set a new password</h2>
          <p>Use at least 10 characters.</p>
          <label>
            New password
            <input type="password" minLength={10} maxLength={256} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required autoComplete="new-password" />
          </label>
          <button type="submit">Update password</button>
          {resetMessage ? <p role="status">{resetMessage}</p> : null}
        </form>
      ) : (
        <>
          <LoginForm
            authenticate={authenticate}
            onForgotPassword={forgotPassword}
            onSsoSignIn={ssoSignIn}
            onAuthenticated={onLogin}
          />
          {resetMessage ? <p role="status">{resetMessage}</p> : null}
        </>
      )}
    </LoginLayout>
  )
}
