export default function ExecutivePageHeader({ eyebrow, title, description, meta = [], actions = null }) {
  return (
    <header className="executive-page-header">
      <div className="executive-page-copy">
        {eyebrow ? <p className="executive-page-eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p className="executive-page-description">{description}</p> : null}
        {meta.length ? (
          <ul className="executive-page-meta" aria-label="Dashboard context">
            {meta.map((item) => (
              <li key={`${item.label}-${item.value}`}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      {actions ? <div className="executive-page-actions">{actions}</div> : null}
    </header>
  )
}
