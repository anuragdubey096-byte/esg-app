export default function SectionCard({ title, subtitle, children, actions, className = '', ...sectionProps }) {
  return (
    <section className={`section-card ${className}`.trim()} {...sectionProps}>
      <div className="section-card-header">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions ? <div>{actions}</div> : null}
      </div>
      {children}
    </section>
  )
}
