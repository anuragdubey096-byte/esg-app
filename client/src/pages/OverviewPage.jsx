import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import AttentionInbox from '../components/AttentionInbox'
import DataTable from '../components/DataTable'
import ExecutivePageHeader from '../components/ExecutivePageHeader'
import KpiCard from '../components/KpiCard'
import ReportingProgress from '../components/ReportingProgress'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useCollaborationWorkspace from '../hooks/useCollaborationWorkspace'
import useDashboardData, { getDaysToDeadline, getLatestSubmission, getPreferredCycle, normalizeStatus } from '../hooks/useDashboardData'
import useLiveActivity from '../hooks/useLiveActivity'
import useNarrativeLifecycle from '../hooks/useNarrativeLifecycle'
import useNarrativeSummary from '../hooks/useNarrativeSummary'

function formatDays(value) {
  if (value == null) return 'N/A'
  if (value < 0) return `${Math.abs(value)} days overdue`
  return `${value} days remaining`
}

function buildFallbackSummary(companies, cycles = []) {
  const preferredCycle = getPreferredCycle(cycles)
  const status_breakdown = {
    'Not Started': 0,
    'In Progress': 0,
    'Submitted': 0,
    'Under Review': 0,
    'Approved': 0,
    'Rejected': 0,
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
      active_cycle_year: preferredCycle?.cycle_year || null,
      submission_open_date: preferredCycle?.submission_open_date || null,
      submission_deadline: preferredCycle?.submission_deadline || null,
      days_remaining: getDaysToDeadline(cycles),
      cycle_status: preferredCycle?.status || 'closed',
    },
    upcoming_deadlines: [],
    progress_rows: [],
  }
}

function buildOverviewAttentionItems({ cycleBanner, isCompany, isManager, primarySubmission, statusBreakdown, upcomingDeadlines }) {
  const items = []
  const addItem = (item) => items.push(item)

  if (isManager) {
    const reviewCount = Number(statusBreakdown.Submitted || 0) + Number(statusBreakdown['Under Review'] || 0)
    const resubmissionCount = Number(statusBreakdown['Resubmission Requested'] || 0)
    const notStartedCount = Number(statusBreakdown['Not Started'] || 0)

    if (resubmissionCount > 0) {
      addItem({
        id: 'manager-resubmissions',
        title: 'Resubmissions require follow-up',
        detail: `${resubmissionCount} compan${resubmissionCount === 1 ? 'y has' : 'ies have'} requested corrections outstanding.`,
        badge: `${resubmissionCount} open`,
        tone: 'critical',
        icon: 'risks',
        to: '/review-hub',
        actionLabel: 'Review',
      })
    }
    if (reviewCount > 0) {
      addItem({
        id: 'manager-review-queue',
        title: 'Review queue is ready',
        detail: `${reviewCount} submission${reviewCount === 1 ? '' : 's'} are submitted or currently under review.`,
        badge: `${reviewCount} waiting`,
        tone: 'warning',
        icon: 'review',
        to: '/review-hub',
        actionLabel: 'Open queue',
      })
    }
    if (upcomingDeadlines.length > 0) {
      addItem({
        id: 'manager-deadlines',
        title: 'Reporting deadlines approaching',
        detail: `${upcomingDeadlines.length} compan${upcomingDeadlines.length === 1 ? 'y is' : 'ies are'} due within the next seven days.`,
        badge: `${upcomingDeadlines.length} due soon`,
        tone: 'warning',
        icon: 'submissions',
        to: '/submissions',
        actionLabel: 'Track progress',
      })
    }
    if (notStartedCount > 0) {
      addItem({
        id: 'manager-not-started',
        title: 'Collection has not started',
        detail: `${notStartedCount} compan${notStartedCount === 1 ? 'y has' : 'ies have'} not started the current submission.`,
        badge: `${notStartedCount} inactive`,
        tone: 'info',
        icon: 'submissions',
        to: '/submissions',
        actionLabel: 'View companies',
      })
    }
  }

  if (isCompany) {
    const status = normalizeStatus(primarySubmission?.status || 'Not Started')
    if (status === 'Resubmission Requested') {
      addItem({
        id: 'company-resubmission',
        title: 'Corrections requested',
        detail: 'Your latest ESG submission needs updates before it can return to review.',
        badge: 'Action required',
        tone: 'critical',
        icon: 'risks',
        to: '/submissions',
        actionLabel: 'Update submission',
      })
    } else if (status === 'Not Started' || status === 'In Progress') {
      addItem({
        id: 'company-submission',
        title: status === 'Not Started' ? 'Start your ESG submission' : 'Complete your ESG submission',
        detail: 'Continue the current reporting cycle and complete all required evidence fields.',
        badge: status,
        tone: 'warning',
        icon: 'submissions',
        to: '/submissions',
        actionLabel: status === 'Not Started' ? 'Get started' : 'Continue',
      })
    }
    if (
      cycleBanner.days_remaining != null
      && Number.isFinite(Number(cycleBanner.days_remaining))
      && Number(cycleBanner.days_remaining) <= 7
    ) {
      const daysRemaining = Number(cycleBanner.days_remaining)
      addItem({
        id: 'company-deadline',
        title: daysRemaining < 0 ? 'Submission deadline has passed' : 'Submission deadline is close',
        detail: formatDays(daysRemaining),
        badge: daysRemaining < 0 ? 'Overdue' : `${daysRemaining} days left`,
        tone: daysRemaining < 0 ? 'critical' : 'warning',
        icon: 'risks',
        to: '/submissions',
        actionLabel: 'Open submission',
      })
    }
  }

  return items
}

export default function OverviewPage() {
  const { user } = useOutletContext()
  const { companies, cycles, summary, loading, error } = useDashboardData(user)
  const role = String(user?.role || '').toLowerCase()
  const isManager = role === 'manager'
  const isCompany = role === 'company'
  const primaryCompany = companies?.[0] || null
  const primarySubmission = getLatestSubmission(primaryCompany)
  const primaryCycleId = primarySubmission?.cycle_id || null
  const narrative = useNarrativeSummary({
    user,
    audience: isCompany ? 'company' : 'lp',
    tone: isCompany ? 'company-ready' : 'board-ready',
    companyId: isCompany ? primaryCompany?.id || null : null,
    enabled: Boolean(user) && (!isCompany || Boolean(primaryCompany)),
  })
  const liveActivity = useLiveActivity({ user, limit: 8, enabled: Boolean(user) })
  const narrativeOps = useNarrativeLifecycle({ user })
  const collaboration = useCollaborationWorkspace({ user, companyId: primaryCompany?.id || null })
  const [fieldKey, setFieldKey] = useState('scope_1_emissions')
  const [fieldValue, setFieldValue] = useState('')
  const [editHeadline, setEditHeadline] = useState('')
  const [editSummary, setEditSummary] = useState('')
  const liveSocketBadge = useMemo(() => {
    if (liveActivity.connectionStatus === 'connected') {
      return { label: 'Connected', className: 'status-good' }
    }
    if (liveActivity.connectionStatus === 'error') {
      return { label: 'Connection Error', className: 'status-critical' }
    }
    return { label: 'Reconnecting', className: 'status-warning' }
  }, [liveActivity.connectionStatus])

  const managerSummary = useMemo(() => {
    if (summary && typeof summary === 'object' && summary.status_breakdown) {
      return summary
    }
    return buildFallbackSummary(companies, cycles)
  }, [companies, cycles, summary])
  const statusBreakdown = managerSummary.status_breakdown || {}
  const cycleBanner = managerSummary.cycle_banner || {}
  const upcomingDeadlines = managerSummary.upcoming_deadlines || []
  const attentionItems = buildOverviewAttentionItems({
    cycleBanner,
    isCompany,
    isManager,
    primarySubmission,
    statusBreakdown,
    upcomingDeadlines,
  })
  const overviewMetrics = useMemo(() => {
    const total = Object.values(statusBreakdown).reduce((sum, value) => sum + Number(value || 0), 0)
    const approved = Number(statusBreakdown.Approved || 0)
    const reviewQueue = Number(statusBreakdown.Submitted || 0) + Number(statusBreakdown['Under Review'] || 0)
    const actionRequired = Number(statusBreakdown['Resubmission Requested'] || 0)
      + Number(statusBreakdown.Rejected || 0)
      + Number(statusBreakdown['Not Started'] || 0)
    return {
      total,
      approved,
      reviewQueue,
      actionRequired,
      completion: total ? Math.round((approved / total) * 100) : 0,
    }
  }, [statusBreakdown])

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

  useEffect(() => {
    if (!isCompany || !primaryCycleId) return
    collaboration.load(primaryCycleId, collaboration.activeSection)
  }, [collaboration.activeSection, collaboration.load, isCompany, primaryCycleId])

  useEffect(() => {
    if (!isCompany) return
    narrativeOps.loadHistory({ audience: 'company', companyId: primaryCompany?.id || null, limit: 5 })
  }, [isCompany, narrativeOps, primaryCompany?.id])

  useEffect(() => {
    if (!isCompany || !primaryCycleId) return
    const timer = setInterval(() => {
      collaboration.heartbeat(primaryCycleId, collaboration.activeSection)
    }, 25000)
    return () => clearInterval(timer)
  }, [collaboration.activeSection, collaboration.heartbeat, isCompany, primaryCycleId])

  useEffect(() => {
    if (!narrativeOps.record) return
    setEditHeadline(narrativeOps.record.headline || '')
    setEditSummary(narrativeOps.record.summary || '')
  }, [narrativeOps.record])

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
      <ExecutivePageHeader
        eyebrow={isCompany ? 'Company reporting workspace' : 'Portfolio command center'}
        title={isCompany ? `${primaryCompany?.name || 'Company'} ESG overview` : 'ESG reporting overview'}
        description={isCompany
          ? 'Track reporting readiness, resolve requested actions, and keep your ESG submission moving.'
          : 'Monitor portfolio reporting, focus the review queue, and act on exceptions from one place.'}
        meta={[
          { label: 'Role', value: isCompany ? 'Company contributor' : 'ESG manager' },
          { label: 'Cycle', value: cycleBanner.active_cycle_year || 'Not active' },
          { label: 'Window', value: formatDays(cycleBanner.days_remaining) },
        ]}
      />

      <section className="executive-kpi-grid" aria-label="Executive reporting metrics">
        <KpiCard
          title={isCompany ? 'Submission Status' : 'Portfolio Companies'}
          value={isCompany ? normalizeStatus(primarySubmission?.status || 'Not Started') : overviewMetrics.total}
          trendLabel={isCompany ? 'current reporting state' : 'in the active reporting view'}
        />
        <KpiCard
          title={isCompany ? 'Cycle Timing' : 'Approved'}
          value={isCompany ? formatDays(cycleBanner.days_remaining) : overviewMetrics.approved}
          trendLabel={isCompany ? 'submission window' : `${overviewMetrics.completion}% portfolio completion`}
        />
        <KpiCard
          title={isCompany ? 'Open Actions' : 'Review Queue'}
          value={isCompany ? attentionItems.length : overviewMetrics.reviewQueue}
          trendLabel={isCompany ? 'items requiring attention' : 'submitted or under review'}
        />
        <KpiCard
          title={isCompany ? 'Data Workspace' : 'Action Required'}
          value={isCompany ? (primarySubmission ? 'Active' : 'Not started') : overviewMetrics.actionRequired}
          trendLabel={isCompany ? 'latest submission availability' : 'not started or correction requested'}
        />
      </section>

      <ReportingProgress
        breakdown={statusBreakdown}
        cycleLabel={cycleBanner.active_cycle_year ? `Cycle ${cycleBanner.active_cycle_year}` : null}
        daysRemaining={cycleBanner.days_remaining}
        role={role || 'manager'}
        windowLabel={cycleBanner.submission_open_date && cycleBanner.submission_deadline
          ? `${cycleBanner.submission_open_date} – ${cycleBanner.submission_deadline}`
          : null}
      />

      <AttentionInbox items={attentionItems} role={role || 'manager'} />

      <SectionCard
        title={isCompany ? 'AI Company Narrative' : 'AI Portfolio Narrative'}
        subtitle={isCompany
          ? 'Current company reporting summary based on submitted ESG data'
          : 'Management summary based on latest approved portfolio data'}
      >
        {narrative.loading ? <p>Generating summary...</p> : null}
        {narrative.error ? <p>{narrative.error}</p> : null}
        {!narrative.loading && !narrative.error && narrative.data ? (
          <>
            <h4>{narrative.data.headline || 'Portfolio Narrative'}</h4>
            <p>{narrative.data.summary || 'No narrative summary available.'}</p>
          </>
        ) : null}
      </SectionCard>

      {isManager ? (
        <SectionCard title="Narrative Ops" subtitle="Phase 3 compatibility wiring for generate and approve lifecycle">
          <div className="action-row">
            <button
              className="button"
              type="button"
              onClick={() => narrativeOps.generate({ audience: 'board', tone: 'board-ready' })}
              disabled={narrativeOps.loading}
            >
              {narrativeOps.loading ? 'Processing...' : 'Generate Board Narrative'}
            </button>
            <button
              className="button good"
              type="button"
              onClick={() => narrativeOps.approve(narrativeOps.record?.narrative_id)}
              disabled={narrativeOps.loading || !narrativeOps.record?.narrative_id || narrativeOps.record?.status === 'approved'}
            >
              Approve Latest Narrative
            </button>
          </div>
          {narrativeOps.error ? <p>{narrativeOps.error}</p> : null}
          {narrativeOps.record ? (
            <div className="summary-box">
              <p>Narrative ID</p>
              <strong>{narrativeOps.record.narrative_id}</strong>
              <p>Status: {narrativeOps.record.status || 'generated'}</p>
              <p>{narrativeOps.record.summary || 'No narrative summary available.'}</p>
            </div>
          ) : null}
        </SectionCard>
      ) : null}

      {isCompany ? (
        <SectionCard title="Company Narrative Workspace" subtitle="Generate, edit, and track company narrative history">
          <div className="action-row">
            <button
              className="button"
              type="button"
              onClick={() => narrativeOps.generate({ audience: 'company', tone: 'company-ready', companyId: primaryCompany?.id || null })}
              disabled={narrativeOps.loading}
            >
              {narrativeOps.loading ? 'Working...' : 'Generate Company Narrative'}
            </button>
            <button
              className="button"
              type="button"
              onClick={() => narrativeOps.update(narrativeOps.record?.narrative_id, { headline: editHeadline, summary: editSummary })}
              disabled={narrativeOps.loading || !narrativeOps.record?.narrative_id}
            >
              Save Narrative Edit
            </button>
          </div>
          <div className="filter-bar">
            <label>
              Headline
              <input value={editHeadline} onChange={(event) => setEditHeadline(event.target.value)} />
            </label>
            <label>
              Summary
              <input value={editSummary} onChange={(event) => setEditSummary(event.target.value)} />
            </label>
          </div>
          {narrativeOps.error ? <p>{narrativeOps.error}</p> : null}
          <ul className="mini-legend">
            {(narrativeOps.history || []).map((item) => (
              <li key={item.narrative_id}>
                <span style={{ background: '#0ea5e9' }} />
                <strong>{item.headline || 'Narrative'}</strong> ({item.status || 'generated'})
              </li>
            ))}
          </ul>
        </SectionCard>
      ) : null}

      {isCompany ? (
        <SectionCard title="Collaboration Workspace" subtitle="Claim section ownership, keep heartbeat active, and update fields">
          <div className="action-row">
            <button
              className="button"
              type="button"
              onClick={() => collaboration.claim(primaryCycleId, collaboration.activeSection)}
              disabled={collaboration.loading || !primaryCycleId}
            >
              Claim Section
            </button>
            <button
              className="button warning"
              type="button"
              onClick={() => collaboration.release(primaryCycleId, collaboration.activeSection)}
              disabled={collaboration.loading || !primaryCycleId}
            >
              Release Section
            </button>
            <button
              className="button"
              type="button"
              onClick={() => collaboration.load(primaryCycleId, collaboration.activeSection)}
              disabled={collaboration.loading || !primaryCycleId}
            >
              Refresh Workspace
            </button>
          </div>
          <div className="filter-bar">
            <label>
              Section
              <select value={collaboration.activeSection} onChange={(event) => collaboration.setActiveSection(event.target.value)}>
                <option value="Environmental">Environmental</option>
                <option value="General">General</option>
              </select>
            </label>
            <label>
              Field Key
              <input value={fieldKey} onChange={(event) => setFieldKey(event.target.value)} />
            </label>
            <label>
              Field Value
              <input value={fieldValue} onChange={(event) => setFieldValue(event.target.value)} />
            </label>
            <label>
              Apply
              <button
                className="button"
                type="button"
                onClick={() => collaboration.updateField(primaryCycleId, fieldKey, fieldValue, collaboration.activeSection)}
                disabled={collaboration.loading || !primaryCycleId}
              >
                Update Field
              </button>
            </label>
          </div>
          {collaboration.error ? <p>{collaboration.error}</p> : null}
          <p>
            Active sections: {(collaboration.payload?.collaboration?.active_sections || collaboration.payload?.active_sections || []).length}
          </p>
          <ul className="mini-legend">
            {(collaboration.payload?.fields || []).slice(0, 8).map((field) => (
              <li key={field.field_key}>
                <span style={{ background: '#16a34a' }} />
                <strong>{field.field_label}</strong>: {field.value == null ? 'N/A' : String(field.value)}
              </li>
            ))}
          </ul>
        </SectionCard>
      ) : null}

      {isManager ? (
        <>
          <SectionCard title="Upcoming Deadlines (Next 7 Days)" subtitle="Only non-submitted companies appear here">
            <DataTable
              columns={deadlineColumns}
              rows={upcomingDeadlines}
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
        </>
      ) : null}

      <SectionCard
        title="Live Activity"
        subtitle="Real-time collaboration and submission events"
        actions={<span className={`status-badge ${liveSocketBadge.className}`}>{liveSocketBadge.label}</span>}
      >
        {liveActivity.loading ? <p>Loading live activity...</p> : null}
        {liveActivity.error ? <p>{liveActivity.error}</p> : null}
        {!liveActivity.loading && !liveActivity.error ? (
          <ul className="space-y-2 text-sm text-slate-700">
            {(liveActivity.events || []).slice(0, 8).map((event) => (
              <li key={event.id}>
                <strong>{event.title || 'Activity update'}</strong>
                <p>{event.message || 'No message provided.'}</p>
              </li>
            ))}
          </ul>
        ) : null}
      </SectionCard>
    </div>
  )
}
