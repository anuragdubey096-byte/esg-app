export default function SectionLoadState({
  loading = false,
  error = '',
  onRetry,
  loadingMessage = 'Loading this section...',
  cached = false,
}) {
  if (!loading && !error) return null

  return (
    <div
      className={`section-load-state ${error ? 'section-load-state-error' : ''}`}
      role={error ? 'alert' : 'status'}
      aria-live="polite"
    >
      <span>
        {error || (cached ? `${loadingMessage} Showing cached data.` : loadingMessage)}
      </span>
      {error && onRetry ? (
        <button className="button" type="button" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  )
}
