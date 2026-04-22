import { useMemo } from 'react'
import { useOutletContext } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import DataTable from '../components/DataTable'
import ImpactStoryCard from '../components/ImpactStoryCard'
import KpiCard from '../components/KpiCard'
import NewsletterCard from '../components/NewsletterCard'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useDashboardData, { getLatestSubmission, normalizeStatus } from '../hooks/useDashboardData'
import useNewsletterSummary from '../hooks/useNewsletterSummary'
import { API_BASE_URL } from '../lib/api'
import { STATUS_COLORS } from '../lib/foundation'
import { UI_LABELS } from '../lib/uiLabels'
import { Button } from '../components/ui'

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
  const { companies, summary, loading, error, refresh } = useDashboardData(user)
  const newsletter = useNewsletterSummary({
    user,
    audience: 'manager',
    tone: 'board-ready',
    enabled: Boolean(user),
  })

  const managerSummary = useMemo(() => {
    if (summary && typeof summary === 'object' && summary.status_breakdown) {
      return summary
    }
    return buildFallbackSummary(companies)
  }, [companies, summary])
  const statusChartData = useMemo(
    () => Object.keys(STATUS_COLORS).map((label) => ({ name: label, value: Number(managerSummary.status_breakdown?.[label] || 0), color: STATUS_COLORS[label] })),
    [managerSummary.status_breakdown]
  )
  const statusBreakdown = managerSummary.status_breakdown || {}
  const cycleBanner = managerSummary.cycle_banner || {}
  const impactStory = managerSummary.impact_story || null

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
    {
      key: 'actions',
      label: 'Actions',
      render: (row) => (
        <div className="flex items-center gap-3">
          <Button
            type="button"
            className="text-xs text-violet-700 ui-text-strong uppercase tracking-wide hover:underline"
            onClick={async () => {
              const message = window.prompt('Reminder message', 'Please submit ESG data before deadline.')
              if (!message) return
              const response = await fetch(`${API_BASE_URL}/companies/${row.company_id}/reminders`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'x-user-role': user?.role || '',
                  'x-user-email': user?.email || '',
                },
                body: JSON.stringify({ channel: 'email', message }),
              })
              if (!response.ok) {
                const payload = await response.json().catch(() => ({}))
                window.alert(payload.detail || 'Failed to send reminder')
                return
              }
              window.alert('Reminder logged.')
              refresh()
            }}
          >
            Reminder
          </Button>
          {row.submission_id ? (
            <Button
              type="button"
              className="text-xs text-amber-700 ui-text-strong uppercase tracking-wide hover:underline"
              onClick={async () => {
                const reason = window.prompt('Unlock reason', 'Allow correction for closed cycle')
                if (!reason) return
                const response = await fetch(`${API_BASE_URL}/companies/${row.company_id}/unlock`, {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                    'x-user-role': user?.role || '',
                    'x-user-email': user?.email || '',
                  },
                  body: JSON.stringify({ reason, expiry_hours: 24 }),
                })
                if (!response.ok) {
                  const payload = await response.json().catch(() => ({}))
                  window.alert(payload.detail || 'Failed to unlock')
                  return
                }
                window.alert('Company unlocked for 24 hours.')
                refresh()
              }}
            >
              Unlock
            </Button>
          ) : null}
        </div>
      ),
    },
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
        <SectionCard title={UI_LABELS.pages.managerOverview.title} subtitle={UI_LABELS.pages.managerOverview.loadingSubtitle}>
          <p>{UI_LABELS.common.loadingDataFromBackend}</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.managerOverview.title} subtitle={UI_LABELS.pages.managerOverview.errorSubtitle}>
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <SectionCard title="Live Admin Snapshot" subtitle="Backend-fed portfolio state and cycle context">
        <div className="two-col-grid">
          <div className="summary-grid three">
            <article className="summary-box">
              <p>Active Cycle</p>
              <strong>{cycleBanner.active_cycle_year ?? 'N/A'}</strong>
            </article>
            <article className="summary-box">
              <p>Reporting Companies</p>
              <strong>{companies.length || 0}</strong>
            </article>
            <article className="summary-box">
              <p>Progress Rows</p>
              <strong>{(managerSummary.progress_rows || []).length}</strong>
            </article>
            <article className="summary-box">
              <p>Upcoming Deadlines</p>
              <strong>{(managerSummary.upcoming_deadlines || []).length}</strong>
            </article>
            <article className="summary-box">
              <p>Cycle Status</p>
              <strong>{cycleBanner.cycle_status || 'closed'}</strong>
            </article>
            <article className="summary-box">
              <p>Days Remaining</p>
              <strong>{formatDays(cycleBanner.days_remaining)}</strong>
            </article>
          </div>

          <div className="chart-wrap">
            <p className="text-sm ui-text-strong text-slate-700 mb-3">Submission Status Mix</p>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={statusChartData} dataKey="value" nameKey="name" innerRadius={64} outerRadius={102} paddingAngle={3}>
                  {statusChartData.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </SectionCard>

      <ImpactStoryCard
        title="Admin Impact Intelligence"
        subtitle="Plain-English context for the current portfolio"
        story={impactStory}
        maxInsights={4}
      />

      <NewsletterCard
        title="Board Newsletter Draft"
        subtitle="Email-ready digest from live portfolio data"
        data={newsletter.data}
        loading={newsletter.loading}
        error={newsletter.error}
        onRefresh={newsletter.refresh}
        onExport={newsletter.exportNewsletter}
        onSend={newsletter.sendNewsletter}
        exporting={newsletter.exporting}
        sending={newsletter.sending}
      />

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


