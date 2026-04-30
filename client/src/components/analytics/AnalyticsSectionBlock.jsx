import SectionCard from '../SectionCard'
import ApiMetricCard from './ApiMetricCard'

export default function AnalyticsSectionBlock({ title, subtitle, user, metrics }) {
  return (
    <SectionCard title={title} subtitle={subtitle}>
      <section className="kpi-grid">
        {metrics.map((metric) => (
          <ApiMetricCard
            key={metric.title}
            user={user}
            title={metric.title}
            endpoint={metric.endpoint}
            valuePath={metric.valuePath}
            selectValue={metric.selectValue}
            selectTrend={metric.selectTrend}
            unit={metric.unit}
            valueType={metric.valueType}
            decimals={metric.decimals}
            emptyLabel={metric.emptyLabel}
          />
        ))}
      </section>
    </SectionCard>
  )
}
