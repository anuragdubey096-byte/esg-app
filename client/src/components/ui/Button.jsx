export default function Button({
  children,
  variant = 'primary',
  loading = false,
  fullWidth = false,
  className = '',
  type = 'button',
  ...props
}) {
  return (
    <button
      type={type}
      {...props}
      className={[
        'ui-button',
        `ui-button-${variant}`,
        fullWidth ? 'ui-button-full' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {loading ? <span className="ui-button-spinner" aria-hidden="true" /> : null}
      <span>{children}</span>
    </button>
  )
}

