import { useState } from 'react'

export default function PasswordField({ id, label, value, onChange, placeholder, error }) {
  const [showPassword, setShowPassword] = useState(false)

  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <div className={`flex items-center rounded-lg border bg-white pr-2 ${error ? 'border-red-400' : 'border-slate-300'}`}>
        <input
          id={id}
          type={showPassword ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          autoComplete="current-password"
          className={`w-full rounded-lg px-3 py-2.5 text-sm text-slate-900 outline-none focus:ring-2 ${error ? 'focus:border-red-500 focus:ring-red-200' : 'focus:border-brand-500 focus:ring-brand-100'}`}
        />
        <button
          type="button"
          onClick={() => setShowPassword((prev) => !prev)}
          className="rounded-md px-2 py-1 text-xs font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
        >
          {showPassword ? 'Hide' : 'Show'}
        </button>
      </div>
      {error ? <p className="text-xs font-medium text-red-600">{error}</p> : null}
    </div>
  )
}
