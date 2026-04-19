import { useState } from 'react'
import { Button } from '../ui'

export default function PasswordField({ id, label, value, onChange, placeholder, error }) {
  const [showPassword, setShowPassword] = useState(false)

  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-medium text-[color:var(--ui-text)]">
        {label}
      </label>
      <div className={`flex items-center rounded-lg border bg-[color:var(--ui-surface)] pr-2 ${error ? 'border-red-400' : 'border-[color:var(--ui-border)]'}`}>
        <input
          id={id}
          type={showPassword ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          autoComplete="current-password"
          className={`w-full rounded-lg bg-transparent px-3 py-2.5 text-sm text-[color:var(--ui-text)] outline-none focus:ring-2 ${error ? 'focus:border-red-500 focus:ring-red-200' : 'focus:border-brand-500 focus:ring-brand-100'}`}
        />
        <Button
          type="button"
          onClick={() => setShowPassword((prev) => !prev)}
          className="rounded-md px-2 py-1 text-xs ui-text-strong text-[color:var(--ui-text-muted)] transition hover:bg-[color:var(--ui-surface-muted)] hover:text-[color:var(--ui-text)]"
          variant="ghost"
        >
          {showPassword ? 'Hide' : 'Show'}
        </Button>
      </div>
      {error ? <p className="text-xs font-medium text-red-600">{error}</p> : null}
    </div>
  )
}

