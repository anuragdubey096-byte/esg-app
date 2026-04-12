const statusClassMap = {
  'Not Started': 'status-critical',
  'In Progress': 'status-warning',
  Submitted: 'status-info',
  Approved: 'status-good',
  Rejected: 'status-critical',
  Pass: 'status-good',
  Warning: 'status-warning',
  Fail: 'status-critical',
  Critical: 'status-critical',
  High: 'status-critical',
  Medium: 'status-warning',
  Low: 'status-good',
  Active: 'status-good',
  Closed: 'status-muted',
  Blocked: 'status-critical',
  Complete: 'status-good',
  Invited: 'status-warning',
}

export default function StatusBadge({ value }) {
  const className = statusClassMap[value] || 'status-muted'
  return <span className={`status-badge ${className}`}>{value}</span>
}
