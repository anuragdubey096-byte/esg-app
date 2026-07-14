const STATUS_CONFIG = [
  { key: 'Approved', className: 'approved' },
  { key: 'Rejected', className: 'rejected' },
  { key: 'Submitted', className: 'submitted' },
  { key: 'Under Review', className: 'review' },
  { key: 'In Progress', className: 'progress' },
  { key: 'Resubmission Requested', className: 'resubmission' },
  { key: 'Not Started', className: 'not-started' },
]

function toCount(value) {
  const number = Number(value)
  return Number.isFinite(number) && number > 0 ? number : 0
}

function formatDeadline(daysRemaining) {
  if (daysRemaining == null || !Number.isFinite(Number(daysRemaining))) return 'No deadline set'
  const days = Number(daysRemaining)
  if (days < 0) return `${Math.abs(days)}d overdue`
  if (days === 0) return 'Due today'
  return `${days}d remaining`
}

export default function ReportingProgress({ breakdown = {}, cycleLabel, daysRemaining, role = 'manager', windowLabel }) {
  const statuses = STATUS_CONFIG.map((status) => ({
    ...status,
    count: toCount(breakdown[status.key]),
  }))
  const total = statuses.reduce((sum, status) => sum + status.count, 0)
  const approved = toCount(breakdown.Approved)
  const started = Math.max(0, total - toCount(breakdown['Not Started']))
  const approvedPercent = total > 0 ? Math.round((approved / total) * 100) : 0
  const startedPercent = total > 0 ? Math.round((started / total) * 100) : 0
  const subject = role === 'company' ? 'submission' : 'portfolio'

  return (
    <section className="reporting-progress" aria-labelledby="reporting-progress-title">
      <header className="reporting-progress-header">
        <div>
          <p className="reporting-progress-eyebrow">Current reporting cycle</p>
          <h2 id="reporting-progress-title">{role === 'company' ? 'Submission progress' : 'Portfolio reporting progress'}</h2>
          <p>A live view of where the {subject} sits in the collection and review workflow.</p>
        </div>
        <div className="reporting-cycle-meta">
          <span>{cycleLabel || 'Active cycle'}</span>
          <strong>{formatDeadline(daysRemaining)}</strong>
          {windowLabel ? <small>{windowLabel}</small> : null}
        </div>
      </header>

      <div className="reporting-progress-body">
        <div className="reporting-progress-metrics">
          <article>
            <span>Total</span>
            <strong>{total}</strong>
            <small>{role === 'company' ? 'submission' : 'companies'}</small>
          </article>
          <article>
            <span>Started</span>
            <strong>{startedPercent}%</strong>
            <small>{started} of {total || 0}</small>
          </article>
          <article>
            <span>Approved</span>
            <strong>{approvedPercent}%</strong>
            <small>{approved} complete</small>
          </article>
        </div>

        <div className="reporting-status-panel">
          <div
            className={`reporting-status-track${total === 0 ? ' empty' : ''}`}
            role="img"
            aria-label={total > 0 ? `${approvedPercent}% approved and ${startedPercent}% started` : 'No reporting progress data available'}
          >
            {total > 0 ? statuses.map((status) => (
              status.count > 0 ? (
                <span
                  className={`reporting-status-segment ${status.className}`}
                  key={status.key}
                  style={{ width: `${(status.count / total) * 100}%` }}
                  title={`${status.key}: ${status.count}`}
                />
              ) : null
            )) : <span>No progress data</span>}
          </div>

          <ul className="reporting-status-legend" aria-label="Reporting statuses">
            {statuses.map((status) => (
              <li key={status.key}>
                <span className={`reporting-legend-dot ${status.className}`} aria-hidden="true" />
                <span>{status.key}</span>
                <strong>{status.count}</strong>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
