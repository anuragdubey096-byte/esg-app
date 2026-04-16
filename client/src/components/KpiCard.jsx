import Card from './ui/Card'

export default function KpiCard({ title, value, trend, trendLabel }) {
  const hasNumericTrend = typeof trend === 'number'
  const trendClass = hasNumericTrend ? (trend >= 0 ? 'positive' : 'negative') : 'neutral'

  return (
    <Card className="ui-kpi-card" bodyClassName="ui-kpi-card-body">
      <p className="kpi-title">{title}</p>
      <p className="kpi-value">{value}</p>
      {trend || trendLabel ? (
        <p className={`kpi-trend ${trendClass}`}>
          {hasNumericTrend ? `${trend > 0 ? '+' : ''}${trend}%` : ''}
          {trendLabel ? ` ${trendLabel}` : ''}
        </p>
      ) : null}
    </Card>
  )
}
