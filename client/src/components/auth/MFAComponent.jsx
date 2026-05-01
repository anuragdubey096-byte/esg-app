import { useState } from 'react'
import Button from './Button'
import InputField from './InputField'

export default function MFAComponent({ onVerify, onBack, loading }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (event) => {
    event.preventDefault()
    const trimmed = code.trim()
    if (!/^[A-Za-z0-9-]{6,12}$/.test(trimmed)) {
      setError('Enter a valid authenticator code or backup code.')
      return
    }
    setError('')
    onVerify(trimmed)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="rounded-xl border border-cyan-100 bg-cyan-50/80 px-3 py-2 text-sm text-cyan-700">
        Enter a 6-digit authenticator code or an unused backup code.
      </div>

      <InputField
        id="mfa_code"
        label="Verification code"
        value={code}
        onChange={(event) => setCode(event.target.value)}
        placeholder="123456 or ABC-DEF"
        error={error}
      />

      <div className="flex gap-2">
        <Button type="submit" loading={loading}>
          {loading ? 'Verifying...' : 'Verify Code'}
        </Button>
      </div>

      <button
        type="button"
        onClick={onBack}
        className="text-sm font-semibold text-slate-500 underline underline-offset-4 hover:text-slate-700"
      >
        Back to sign in
      </button>
    </form>
  )
}
