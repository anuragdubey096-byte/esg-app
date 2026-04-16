export default function Card({
  title,
  subtitle,
  actions,
  header,
  footer,
  children,
  className = '',
  bodyClassName = '',
}) {
  const resolvedHeader =
    header || title || subtitle || actions ? (
      <div className="ui-card-header">
        <div>
          {title ? <h3 className="ui-card-title">{title}</h3> : null}
          {subtitle ? <p className="ui-card-subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="ui-card-actions">{actions}</div> : null}
      </div>
    ) : null

  return (
    <section className={`ui-card ${className}`.trim()}>
      {resolvedHeader}
      {header ? <div className="ui-card-custom-header">{header}</div> : null}
      <div className={`ui-card-body ${bodyClassName}`.trim()}>{children}</div>
      {footer ? <div className="ui-card-footer">{footer}</div> : null}
    </section>
  )
}

