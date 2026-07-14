import { Link } from 'react-router-dom'
import AppIcon from './AppIcon'

export default function AttentionInbox({ items = [], role = 'manager' }) {
  const visibleItems = items.slice(0, 5)

  return (
    <section className="attention-inbox" aria-labelledby="attention-inbox-title">
      <header className="attention-inbox-header">
        <div>
          <p className="attention-eyebrow">Priority workspace</p>
          <h2 id="attention-inbox-title">Needs your attention</h2>
          <p>Live actions prioritized for your {role} workspace.</p>
        </div>
        <span className="attention-count" aria-label={`${visibleItems.length} priority items`}>
          {visibleItems.length}
        </span>
      </header>

      {visibleItems.length > 0 ? (
        <ul className="attention-list">
          {visibleItems.map((item) => (
            <li className={`attention-item ${item.tone || 'info'}`} key={item.id}>
              <span className="attention-item-icon">
                <AppIcon name={item.icon || 'actions'} size={19} />
              </span>
              <div className="attention-item-copy">
                <div>
                  <strong>{item.title}</strong>
                  {item.badge ? <span className="attention-badge">{item.badge}</span> : null}
                </div>
                <p>{item.detail}</p>
              </div>
              <Link className="attention-action" to={item.to}>
                {item.actionLabel || 'Open'} <span aria-hidden="true">&rarr;</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="attention-empty">
          <span><AppIcon name="actions" size={22} /></span>
          <div>
            <strong>You are all caught up</strong>
            <p>No immediate actions were found in the current reporting cycle.</p>
          </div>
        </div>
      )}
    </section>
  )
}
