const statusClassMap = {
  'Not Started': 'status-critical',
  'In Progress': 'status-warning',
  Submitted: 'status-info',
  'Under Review': 'status-warning',
  Approved: 'status-good',
  Rejected: 'status-critical',
  'Resubmission Requested': 'status-warning',
  'Pending Review': 'status-warning',
  Pass: 'status-good',
  Warning: 'status-warning',
  Fail: 'status-critical',
  Critical: 'status-critical',
  High: 'status-critical',
  Medium: 'status-warning',
  Low: 'status-good',
  Active: 'status-good',
  Closed: 'status-muted',
  Draft: 'status-info',
  Blocked: 'status-critical',
  Complete: 'status-good',
  Planned: 'status-warning',
  'No Plan': 'status-muted',
  Invited: 'status-warning',
}

export default function StatusBadge({ value }) {
  const className = statusClassMap[value] || 'status-muted'
  return <span className={`status-badge ${className}`}>{value}</span>
}
