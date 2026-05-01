import { useState } from 'react'
import Button from './Button'
import InputField from './InputField'
import MFAComponent from './MFAComponent'
import PasswordField from './PasswordField'

function validateCredentials({ email, password }) {
  const errors = {}
  if (!email.trim()) {
    errors.email = 'Email is required.'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
    errors.email = 'Please enter a valid email address.'
  }

  if (!password.trim()) {
    errors.password = 'Password is required.'
  }

  return errors
}

function validateEmailOnly(email) {
  if (!email.trim()) return 'Email is required to reset password.'
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
    return 'Please enter a valid email address.'
  }
  return ''
}

export default function LoginForm({ authenticate, onForgotPassword, onSsoSignIn, onAuthenticated }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState({})
  const [authError, setAuthError] = useState('')
  const [infoMessage, setInfoMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isForgotSubmitting, setIsForgotSubmitting] = useState(false)
  const [ssoProviderLoading, setSsoProviderLoading] = useState('')
  const [mfaLoading, setMfaLoading] = useState(false)
  const [step, setStep] = useState('credentials')
  const [pendingUser, setPendingUser] = useState(null)

  const handleSubmit = async (event) => {
    event.preventDefault()
    const validationErrors = validateCredentials({ email, password })
    setErrors(validationErrors)
    setAuthError('')
    setInfoMessage('')

    if (Object.keys(validationErrors).length > 0) return

    setIsSubmitting(true)
    try {
      const result = await authenticate({ email: email.trim(), password })
      if (!result?.user) throw new Error('Invalid email or password')

      if (result.mfaRequired) {
        setPendingUser(result.user)
        setStep('mfa')
      } else {
        onAuthenticated(result.user)
      }
    } catch (error) {
      setAuthError(error.message || 'Invalid email or password')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleMfaVerify = async (code) => {
    setMfaLoading(true)
    setAuthError('')
    setInfoMessage('')
    try {
      await new Promise((resolve) => setTimeout(resolve, 800))
      if (code !== '123456') throw new Error('Invalid verification code')
      onAuthenticated(pendingUser)
    } catch (error) {
      setAuthError(error.message || 'Invalid verification code')
    } finally {
      setMfaLoading(false)
    }
  }

  const handleForgotPassword = async () => {
    const emailError = validateEmailOnly(email)
    if (emailError) {
      setErrors((current) => ({ ...current, email: emailError }))
      return
    }

    setErrors((current) => ({ ...current, email: '' }))
    setAuthError('')
    setInfoMessage('')
    setIsForgotSubmitting(true)
    try {
      const message = await onForgotPassword({ email: email.trim() })
      setInfoMessage(message)
    } catch (error) {
      setAuthError(error.message || 'Unable to process forgot password request.')
    } finally {
      setIsForgotSubmitting(false)
    }
  }

  const handleSsoClick = async (provider) => {
    setAuthError('')
    setInfoMessage('')
    setSsoProviderLoading(provider)
    try {
      const user = await onSsoSignIn(provider)
      onAuthenticated(user)
    } catch (error) {
      setAuthError(error.message || 'SSO sign-in failed.')
    } finally {
      setSsoProviderLoading('')
    }
  }

  return (
    <div className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-[0_20px_45px_rgba(15,23,42,0.12)] md:p-8">
      {step === 'credentials' ? (
        <>
          <div className="mb-6 space-y-2">
            <p className="inline-flex items-center rounded-full border border-cyan-100 bg-cyan-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.11em] text-cyan-700">
              Secure Sign In
            </p>
            <h2 className="text-2xl font-semibold text-slate-900 md:text-[1.75rem]">Welcome back</h2>
            <p className="text-sm text-slate-500">Sign in to continue your ESG reporting workflow.</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <InputField
              id="email"
              label="Email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@company.com"
              autoComplete="email"
              error={errors.email}
            />

            <PasswordField
              id="password"
              label="Password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter your password"
              error={errors.password}
            />

            <div className="text-right">
              <button
                type="button"
                onClick={handleForgotPassword}
                disabled={isForgotSubmitting || isSubmitting || Boolean(ssoProviderLoading)}
                className="text-sm font-semibold text-cyan-700 hover:text-cyan-600 disabled:cursor-not-allowed disabled:opacity-70"
              >
                {isForgotSubmitting ? 'Sending reset link...' : 'Forgot password?'}
              </button>
            </div>

            {authError ? (
              <p className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
                {authError}
              </p>
            ) : null}

            {infoMessage ? (
              <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700">
                {infoMessage}
              </p>
            ) : null}

            <Button type="submit" loading={isSubmitting} disabled={isForgotSubmitting || Boolean(ssoProviderLoading)}>
              {isSubmitting ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>

          <div className="my-5 flex items-center gap-3">
            <div className="h-px flex-1 bg-slate-200" />
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">OR CONTINUE WITH</span>
            <div className="h-px flex-1 bg-slate-200" />
          </div>

          <div className="grid gap-2">
            <button
              type="button"
              onClick={() => handleSsoClick('google')}
              disabled={Boolean(ssoProviderLoading) || isSubmitting || isForgotSubmitting}
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:-translate-y-[1px] hover:border-cyan-300 hover:bg-cyan-50/50"
            >
              {ssoProviderLoading === 'google' ? 'Connecting to Google...' : 'Continue with Google'}
            </button>
            <button
              type="button"
              onClick={() => handleSsoClick('microsoft')}
              disabled={Boolean(ssoProviderLoading) || isSubmitting || isForgotSubmitting}
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:-translate-y-[1px] hover:border-cyan-300 hover:bg-cyan-50/50"
            >
              {ssoProviderLoading === 'microsoft' ? 'Connecting to Microsoft...' : 'Continue with Microsoft'}
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="mb-6 space-y-2">
            <p className="inline-flex items-center rounded-full border border-cyan-100 bg-cyan-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.11em] text-cyan-700">
              Extra Security
            </p>
            <h2 className="text-2xl font-semibold text-slate-900">Multi-factor authentication</h2>
            <p className="text-sm text-slate-500">Enter the code sent to your email</p>
          </div>
          {authError ? (
            <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
              {authError}
            </p>
          ) : null}
          <MFAComponent
            onVerify={handleMfaVerify}
            onBack={() => {
              setStep('credentials')
              setPendingUser(null)
              setAuthError('')
            }}
            loading={mfaLoading}
          />
        </>
      )}

      <footer className="mt-7 text-center text-xs text-slate-500">
        <a href="#" className="font-medium hover:text-slate-700">Privacy Policy</a>
        <span className="mx-2">|</span>
        <a href="#" className="font-medium hover:text-slate-700">Terms of Service</a>
      </footer>
    </div>
  )
}
