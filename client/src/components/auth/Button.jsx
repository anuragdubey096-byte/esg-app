export default function Button({ children, loading, className = '', ...props }) {
  return (
    <button
      {...props}
      className={`inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-600 via-blue-600 to-teal-600 px-4 py-3 text-sm font-semibold text-white shadow-[0_12px_24px_rgba(8,47,73,0.28)] transition hover:-translate-y-[1px] hover:from-cyan-700 hover:via-blue-700 hover:to-teal-600 disabled:cursor-not-allowed disabled:opacity-70 ${className}`}
    >
      {loading ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" />
      ) : null}
      {children}
    </button>
  )
}
