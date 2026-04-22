import Card from './ui/Card'

export default function SectionCard({ title, subtitle, children, actions, className = '' }) {
  return (
    <Card
      title={title}
      subtitle={subtitle}
      actions={actions}
      className={className}
    >
      {children}
    </Card>
  )
}
