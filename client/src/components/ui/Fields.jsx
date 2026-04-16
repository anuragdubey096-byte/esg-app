import Button from './Button'

export function FieldShell({ label, required, hint, error, children }) {
  return (
    <label className="ui-field">
      <span className="ui-field-label">
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </span>
      {hint ? <span className="ui-field-hint">{hint}</span> : null}
      {children}
      {error ? <span className="ui-field-error">{error}</span> : null}
    </label>
  )
}

export function TextInput({ label, error, hint, ...props }) {
  return (
    <FieldShell label={label} error={error} hint={hint}>
      <input className="ui-input" {...props} />
    </FieldShell>
  )
}

export function SelectInput({ label, error, hint, children, ...props }) {
  return (
    <FieldShell label={label} error={error} hint={hint}>
      <select className="ui-input" {...props}>
        {children}
      </select>
    </FieldShell>
  )
}

export function TextareaInput({ label, error, hint, ...props }) {
  return (
    <FieldShell label={label} error={error} hint={hint}>
      <textarea className="ui-input ui-textarea" {...props} />
    </FieldShell>
  )
}

export function FileUploadField({ label, hint, error, onChange, accept, multiple, disabled }) {
  return (
    <FieldShell label={label} error={error} hint={hint}>
      <input
        type="file"
        className="ui-file-input"
        onChange={onChange}
        accept={accept}
        multiple={multiple}
        disabled={disabled}
      />
    </FieldShell>
  )
}

export function ConfidenceFlagSelector({ label = 'Confidence', value, onChange, options = [] }) {
  return (
    <div className="ui-field">
      <span className="ui-field-label">{label}</span>
      <div className="ui-segmented">
        {options.map((option) => (
          <Button
            key={option}
            type="button"
            variant="secondary"
            className={`ui-segmented-option ${value === option ? 'active' : ''}`}
            onClick={() => onChange(option)}
          >
            {option}
          </Button>
        ))}
      </div>
    </div>
  )
}
