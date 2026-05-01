import LoginForm from './components/auth/LoginForm'
import LoginLayout from './components/auth/LoginLayout'
import { API_BASE_URL } from './lib/api'

const backendUrl = API_BASE_URL

export default function LoginPage({ onLogin }) {
  const authenticate = async ({ email, password }) => {
    try {
      const response = await fetch(`${backendUrl}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })

      if (response.status === 401) {
        throw new Error('Invalid email or password')
      }

      if (!response.ok) {
        throw new Error('Unable to sign in right now. Please try again.')
      }

      const user = await response.json()
      const sessionToken = response.headers.get('x-session-token') || ''
      const authenticatedUser = { ...user, sessionToken }

      const mfaStatusResponse = await fetch(`${backendUrl}/auth/mfa/status`, {
        headers: {
          'x-user-role': authenticatedUser.role || '',
          'x-user-email': authenticatedUser.email || '',
          ...(sessionToken ? { 'x-session-token': sessionToken } : {}),
        },
      })
      const mfaStatus = mfaStatusResponse.ok
        ? await mfaStatusResponse.json().catch(() => ({ required: false, enabled: false }))
        : { required: false, enabled: false }

      return {
        user: authenticatedUser,
        mfaRequired: Boolean(mfaStatus?.required),
        mfaEnabled: Boolean(mfaStatus?.enabled),
      }
    } catch (error) {
      const isNetworkError = error?.name === 'TypeError' || String(error?.message || '').includes('Failed to fetch')
      if (isNetworkError) {
        throw new Error('Database server is unreachable. Please start the backend and try again.')
      }
      throw error
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

    const user = await response.json()
    const sessionToken = response.headers.get('x-session-token') || ''
    return { ...user, sessionToken }
  }

  const setupMfa = async (user) => {
    const response = await fetch(`${backendUrl}/auth/mfa/setup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-user-role': user?.role || '',
        'x-user-email': user?.email || '',
        ...(user?.sessionToken ? { 'x-session-token': user.sessionToken } : {}),
      },
      body: JSON.stringify({ issuer_name: 'ESG Platform' }),
    })
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || 'Unable to initialize MFA setup.')
    }
    return response.json()
  }

  const verifyMfa = async (user, code) => {
    const response = await fetch(`${backendUrl}/auth/mfa/verify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-user-role': user?.role || '',
        'x-user-email': user?.email || '',
        ...(user?.sessionToken ? { 'x-session-token': user.sessionToken } : {}),
      },
      body: JSON.stringify({ code }),
    })
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || 'MFA verification failed.')
    }
    return response.json()
  }

  return (
    <LoginLayout>
      <LoginForm
        authenticate={authenticate}
        onForgotPassword={forgotPassword}
        onSsoSignIn={ssoSignIn}
        onMfaSetup={setupMfa}
        onMfaVerify={verifyMfa}
        onAuthenticated={onLogin}
      />
    </LoginLayout>
  )
}
