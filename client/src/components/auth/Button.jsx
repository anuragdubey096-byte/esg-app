export default function Button({ children, loading, className = '', ...props }) {
  return (
    <button
      {...props}
      className={`inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-brand-600 to-esg-600 px-4 py-3 text-sm font-semibold text-white shadow-soft transition hover:from-brand-700 hover:to-esg-600 disabled:cursor-not-allowed disabled:opacity-70 ${className}`}
    >
      {loading ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" />
      ) : null}
      {children}
    </button>
  )
}
