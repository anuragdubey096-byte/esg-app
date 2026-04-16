import Button from './Button'

export default function EmptyState({ title, description, actionLabel, onAction, className = '' }) {
  return (
    <div className={`ui-empty-state ${className}`.trim()} role="status" aria-live="polite">
      <div className="ui-empty-state-icon" aria-hidden="true">
        •
      </div>
      <div className="ui-empty-state-copy">
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
      </div>
      {actionLabel && onAction ? (
        <Button variant="secondary" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  )
}

