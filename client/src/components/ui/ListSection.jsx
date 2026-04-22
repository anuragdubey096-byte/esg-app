export default function ListSection({ title, items }) {
  if (!Array.isArray(items) || !items.length) return null

  return (
    <div className="space-y-2">
      <p className="ui-text-strong text-[color:var(--ui-text)]">{title}</p>
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item}
            className="rounded-lg border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-3 py-2 text-sm leading-6 text-[color:var(--ui-text)]"
          >
            {item}
          </div>
        ))}
      </div>
    </div>
  )
}
