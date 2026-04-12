export default function InputField({
  id,
  label,
  type = 'text',
  value,
  onChange,
  placeholder,
  autoComplete,
  error,
}) {
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        autoComplete={autoComplete}
        className={`w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition focus:ring-2 ${error ? 'border-red-400 focus:border-red-500 focus:ring-red-200' : 'border-slate-300 focus:border-brand-500 focus:ring-brand-100'}`}
      />
      {error ? <p className="text-xs font-medium text-red-600">{error}</p> : null}
    </div>
  )
}
