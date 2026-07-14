export default function RouteLoadingState() {
  return (
    <div className="route-loading" role="status" aria-live="polite" aria-label="Loading dashboard page">
      <div className="route-loading-heading">
        <span />
        <span />
      </div>
      <div className="route-loading-metrics">
        <span />
        <span />
        <span />
      </div>
      <div className="route-loading-panel">
        <span />
        <span />
        <span />
        <span />
      </div>
      <span className="sr-only">Loading dashboard page…</span>
    </div>
  )
}
