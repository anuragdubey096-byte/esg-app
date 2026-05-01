import { useState } from 'react'
import Button from './Button'
import InputField from './InputField'

export default function MFAComponent({ onVerify, onBack, loading }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (event) => {
    event.preventDefault()
    const trimmed = code.trim()
    if (!/^\d{6}$/.test(trimmed)) {
      setError('Please enter a valid 6-digit code.')
      return
    }
    setError('')
    onVerify(trimmed)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="rounded-xl border border-cyan-100 bg-cyan-50/80 px-3 py-2 text-sm text-cyan-700">
        Enter the code sent to your email.
      </div>

      <InputField
        id="mfa_code"
        label="Verification code"
        value={code}
        onChange={(event) => setCode(event.target.value)}
        placeholder="123456"
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
