import Card from './ui/Card'

export default function SectionCard({ title, subtitle, children, actions, footer, className = '' }) {
  return (
    <Card
      title={title}
      subtitle={subtitle}
      actions={actions}
      footer={footer}
      className={className}
    >
      {children}
    </Card>
  )
}
