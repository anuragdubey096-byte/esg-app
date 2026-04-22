export default function Card({
  title,
  subtitle,
  actions,
  children,
  className = '',
  bodyClassName = '',
}) {
  const hasHeader = title || subtitle || actions

  return (
    <section className={`ui-card ${className}`.trim()}>
      {hasHeader ? (
        <div className="ui-card-header">
          <div>
            {title ? <h3 className="ui-card-title">{title}</h3> : null}
            {subtitle ? <p className="ui-card-subtitle">{subtitle}</p> : null}
          </div>
          {actions ? <div className="ui-card-actions">{actions}</div> : null}
        </div>
      ) : null}
      <div className={`ui-card-body ${bodyClassName}`.trim()}>{children}</div>
    </section>
  )
}
