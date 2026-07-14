import AppIcon from './AppIcon'

export default function KpiCard({ title, value, trend, trendLabel, icon = 'overview', tone = 'teal' }) {
  const hasNumericTrend = typeof trend === 'number'
  return (
    <article className={`kpi-card kpi-card-${tone}`}>
      <div className="kpi-card-heading">
        <span className="kpi-card-icon"><AppIcon name={icon} size={18} /></span>
        <p className="kpi-title">{title}</p>
      </div>
      <p className="kpi-value">{value}</p>
      {(trend || trendLabel) ? (
        <p className={`kpi-trend ${hasNumericTrend ? (trend >= 0 ? 'positive' : 'negative') : 'neutral'}`}>
          {hasNumericTrend ? `${trend > 0 ? '+' : ''}${trend}%` : ''}
          {trendLabel ? ` ${trendLabel}` : ''}
        </p>
      ) : null}
    </article>
  )
}
