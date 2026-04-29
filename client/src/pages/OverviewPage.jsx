import { useMemo } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData, { getLatestSubmission, normalizeStatus } from '../hooks/useDashboardData'
import useNarrativeSummary from '../hooks/useNarrativeSummary'

function formatDays(value) {
  if (value == null) return 'N/A'
  if (value < 0) return `${Math.abs(value)} days overdue`
  return `${value} days remaining`
}

function buildFallbackSummary(companies) {
  const status_breakdown = {
    'Not Started': 0,
    'In Progress': 0,
    'Submitted': 0,
    'Under Review': 0,
    'Approved': 0,
    'Resubmission Requested': 0,
  }

  companies.forEach((company) => {
    const latest = getLatestSubmission(company)
    const status = normalizeStatus(latest?.status || company?.current_status || 'Not Started')
    if (status_breakdown[status] !== undefined) {
      status_breakdown[status] += 1
    }
  })

  return {
    status_breakdown,
    cycle_banner: {
      active_cycle_year: null,
      submission_open_date: null,
      submission_deadline: null,
      days_remaining: null,
      cycle_status: 'closed',
    },
    upcoming_deadlines: [],
    progress_rows: [],
  }
}

export default function OverviewPage() {
  const { user } = useOutletContext()
  const { companies, summary, loading, error } = useDashboardData(user)
  const narrative = useNarrativeSummary({ user, audience: 'lp', tone: 'board-ready', enabled: Boolean(user) })

  const managerSummary = useMemo(() => {
    if (summary && typeof summary === 'object' && summary.status_breakdown) {
      return summary
    }
    return buildFallbackSummary(companies)
  }, [companies, summary])
  const statusBreakdown = managerSummary.status_breakdown || {}
  const cycleBanner = managerSummary.cycle_banner || {}

  const statusCards = [
    'Not Started',
    'In Progress',
    'Submitted',
    'Under Review',
    'Approved',
    'Resubmission Requested',
  ].map((label) => ({
    title: label,
    value: String(statusBreakdown[label] ?? 0),
  }))

  const deadlineColumns = [
    { key: 'company_name', label: 'Company', sortable: true },
    { key: 'asset_class', label: 'Asset Class', sortable: true },
    { key: 'sector', label: 'Sector', sortable: true },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
    { key: 'completion_percent', label: 'Completion %', sortable: true },
    { key: 'days_remaining', label: 'Days Left', sortable: true },
  ]

  const progressColumns = [
    { key: 'company_name', label: 'Company', sortable: true },
    { key: 'asset_class', label: 'Asset Class', sortable: true },
    { key: 'sector', label: 'Sector', sortable: true },
    { key: 'status', label: 'Status', sortable: true, render: (row) => <StatusBadge value={row.status} /> },
    { key: 'completion_percent', label: 'Completion %', sortable: true },
    { key: 'last_activity', label: 'Last Activity', sortable: true },
    { key: 'deadline', label: 'Deadline', sortable: true },
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <span className="text-xs text-slate-600">{Array.isArray(row.actions) ? row.actions.join(' | ') : ''}</span>
      ),
    },
  ]

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="Overview Dashboard" subtitle="Loading ESG overview from database...">
          <p>Loading data from backend.</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="Overview Dashboard" subtitle="Live data unavailable">
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <section className="kpi-grid">
        {statusCards.map((card) => <KpiCard key={card.title} {...card} />)}
      </section>

      <SectionCard title="Cycle Summary" subtitle="Current collection window status">
        <div className="summary-grid three">
          <article className="summary-box">
            <p>Active Cycle</p>
            <strong>{cycleBanner.active_cycle_year ?? 'N/A'}</strong>
          </article>
          <article className="summary-box">
            <p>Window</p>
            <strong>{cycleBanner.submission_open_date || 'N/A'} to {cycleBanner.submission_deadline || 'N/A'}</strong>
          </article>
          <article className="summary-box">
            <p>Status</p>
            <strong>{cycleBanner.cycle_status || 'closed'}</strong>
          </article>
        </div>
        <p className="text-sm text-slate-600 mt-3">{formatDays(cycleBanner.days_remaining)}</p>
      </SectionCard>

      <SectionCard title="AI Portfolio Narrative" subtitle="OpenAI-generated management summary from latest approved portfolio data">
        {narrative.loading ? <p>Generating summary...</p> : null}
        {narrative.error ? <p>{narrative.error}</p> : null}
        {!narrative.loading && !narrative.error && narrative.data ? (
          <>
            <h4>{narrative.data.headline || 'Portfolio Narrative'}</h4>
            <p>{narrative.data.summary || 'No narrative summary available.'}</p>
          </>
        ) : null}
      </SectionCard>

      <SectionCard title="Upcoming Deadlines (Next 7 Days)" subtitle="Only non-submitted companies appear here">
        <DataTable
          columns={deadlineColumns}
          rows={managerSummary.upcoming_deadlines || []}
          pageSize={8}
          emptyMessage="No upcoming deadlines in the next 7 days."
        />
      </SectionCard>

      <SectionCard title="Manager Progress Table" subtitle="Dynamic company-level tracking and available actions">
        <DataTable
          columns={progressColumns}
          rows={managerSummary.progress_rows || []}
          pageSize={10}
          emptyMessage="No company progress rows available."
        />
      </SectionCard>
    </div>
  )
}
