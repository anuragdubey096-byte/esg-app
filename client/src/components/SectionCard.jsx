export default function SectionCard({ title, subtitle, children, actions }) {
  return (
    <section className="section-card">
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
