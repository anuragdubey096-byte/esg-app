import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import DataTable from '../components/DataTable'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import StatusBadge from '../components/StatusBadge'
import useCollaborationWorkspace from '../hooks/useCollaborationWorkspace'
import useDashboardData, { getLatestSubmission, normalizeStatus } from '../hooks/useDashboardData'
import useExternalContextFeed from '../hooks/useExternalContextFeed'
import useLiveActivity from '../hooks/useLiveActivity'
import useNarrativeLifecycle from '../hooks/useNarrativeLifecycle'
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

function normalizeSectorLabel(value) {
  const cleaned = String(value || '').trim()
  return cleaned || ''
}

function buildSectorNewsOptions(companies, summary) {
  const sectors = new Set()
  ;(companies || []).forEach((company) => {
    const sector = normalizeSectorLabel(company?.sector)
    if (sector) sectors.add(sector)
  })
  ;(summary?.underperforming_sectors || []).forEach((sector) => {
    const cleaned = normalizeSectorLabel(sector)
    if (cleaned) sectors.add(cleaned)
  })
  return ['All Sectors', ...Array.from(sectors).sort((left, right) => left.localeCompare(right))]
}

function formatNewsPublishedAt(value) {
  if (!value) return 'Just now'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return 'Recently updated'
  return parsed.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export default function OverviewPage() {
  const { user } = useOutletContext()
  const { companies, summary, loading, error } = useDashboardData(user)
  const narrative = useNarrativeSummary({ user, audience: 'lp', tone: 'board-ready', enabled: Boolean(user) })
  const liveActivity = useLiveActivity({ user, limit: 8, enabled: Boolean(user) })
  const externalNews = useExternalContextFeed({ user, limit: 12, enabled: Boolean(user) })
  const narrativeOps = useNarrativeLifecycle({ user })
  const role = String(user?.role || '').toLowerCase()
  const isManager = role === 'manager'
  const isCompany = role === 'company'
  const primaryCompany = companies?.[0] || null
  const primarySubmission = getLatestSubmission(primaryCompany)
  const primaryCycleId = primarySubmission?.cycle_id || null
  const collaboration = useCollaborationWorkspace({ user, companyId: primaryCompany?.id || null })
  const [fieldKey, setFieldKey] = useState('scope_1_emissions')
  const [fieldValue, setFieldValue] = useState('')
  const [editHeadline, setEditHeadline] = useState('')
  const [editSummary, setEditSummary] = useState('')
  const [newsSector, setNewsSector] = useState('All Sectors')
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
    return buildFallbackSummary(companies)
  }, [companies, summary])
  const statusBreakdown = managerSummary.status_breakdown || {}
  const cycleBanner = managerSummary.cycle_banner || {}
  const sectorNewsOptions = useMemo(() => buildSectorNewsOptions(companies, summary), [companies, summary])
  const visibleNewsItems = useMemo(() => {
    const items = Array.isArray(externalNews.items) ? externalNews.items : []
    if (newsSector === 'All Sectors') return items
    const targetSector = newsSector.toLowerCase()
    return items.filter((item) => {
      const tags = Array.isArray(item?.sector_tags) ? item.sector_tags : []
      return tags.some((tag) => String(tag || '').toLowerCase() === targetSector)
    })
  }, [externalNews.items, newsSector])

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
    if (!sectorNewsOptions.includes(newsSector)) {
      setNewsSector('All Sectors')
    }
  }, [newsSector, sectorNewsOptions])

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

      <SectionCard title="Sectoral Live ESG News" subtitle="Live ESG headlines grouped with sector tags for all roles">
        <div className="news-premium-shell">
          <div className="news-premium-toolbar">
            <label className="news-premium-control">
              <span>Sector</span>
              <select value={newsSector} onChange={(event) => setNewsSector(event.target.value)}>
                {sectorNewsOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>
            <button className="button news-premium-refresh" type="button" onClick={() => externalNews.reload()} disabled={externalNews.loading}>
              {externalNews.loading ? 'Refreshing...' : 'Refresh Feed'}
            </button>
          </div>
          <div className="news-premium-meta">
            <span className="news-premium-pill">Sources {externalNews.meta.source_count}</span>
            <span className="news-premium-pill">{externalNews.meta.fallback_used ? 'Fallback Mode' : 'Live Mode'}</span>
            <span className="news-premium-pill">Updated {formatNewsPublishedAt(externalNews.meta.generated_at)}</span>
          </div>
          {externalNews.loading ? <p>Loading latest ESG headlines...</p> : null}
          {externalNews.error ? <p>{externalNews.error}</p> : null}
          {!externalNews.loading && !externalNews.error ? (
            <>
              <ul className="news-premium-grid">
                {visibleNewsItems.map((item, index) => {
                  const sectorTags = (Array.isArray(item.sector_tags) && item.sector_tags.length ? item.sector_tags : ['General ESG']).slice(0, 3)
                  const priorityLabel = String(item.priority || 'medium').toLowerCase()
                  const isFeatured = index === 0
                  return (
                    <li key={item.id || `${item.title}-${item.published_at}`} className={`news-premium-item ${isFeatured ? 'featured' : ''}`}>
                      <div className="news-premium-item-top">
                        <span className={`news-priority-chip ${priorityLabel === 'high' ? 'high' : 'medium'}`}>
                          {isFeatured ? 'Featured' : priorityLabel === 'high' ? 'High Priority' : 'Watch'}
                        </span>
                        <span className="news-source-chip">{item.source_label || 'External ESG feed'}</span>
                      </div>
                      {item.source_url ? (
                        <a className="news-title-link" href={item.source_url} target="_blank" rel="noreferrer">
                          {item.title || 'ESG update'}
                        </a>
                      ) : (
                        <p className="news-title-link static">{item.title || 'ESG update'}</p>
                      )}
                      <p className="news-summary">{item.summary || 'No summary available.'}</p>
                      <div className="news-chip-row">
                        {sectorTags.map((sectorTag) => (
                          <span key={`${item.id || item.title}-${sectorTag}`} className="news-sector-chip">{sectorTag}</span>
                        ))}
                      </div>
                      <div className="news-item-foot">
                        <p className="news-timestamp">{formatNewsPublishedAt(item.published_at)}</p>
                        {item.source_url ? (
                          <a className="news-read-link" href={item.source_url} target="_blank" rel="noreferrer">
                            Read full article
                          </a>
                        ) : (
                          <span className="news-read-link disabled">Source unavailable</span>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ul>
              {!visibleNewsItems.length ? <p className="news-empty">No live news items are tagged for this sector right now.</p> : null}
            </>
          ) : null}
        </div>
      </SectionCard>

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
