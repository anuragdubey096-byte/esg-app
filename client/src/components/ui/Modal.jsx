import Button from './Button'

const WIDTH_CLASSES = {
  sm: 'ui-modal-sm',
  md: 'ui-modal-md',
  lg: 'ui-modal-lg',
}

export default function Modal({ open, title, children, footer, onClose, size = 'md' }) {
  if (!open) return null

  return (
    <div className="ui-modal-overlay" role="presentation" onMouseDown={onClose}>
      <div
        className={`ui-modal-shell ${WIDTH_CLASSES[size] || WIDTH_CLASSES.md}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="ui-modal-header">
          <div>
            <h2 className="ui-modal-title">{title}</h2>
          </div>
          <Button variant="ghost" onClick={onClose} aria-label="Close modal">
            Close
          </Button>
        </div>
        <div className="ui-modal-body">{children}</div>
        {footer ? <div className="ui-modal-footer">{footer}</div> : null}
      </div>
    </div>
  )
}

