export default function KpiCard({ title, value, trend, trendLabel }) {
  const hasNumericTrend = typeof trend === 'number'
  return (
    <article className="kpi-card">
      <p className="kpi-title">{title}</p>
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
