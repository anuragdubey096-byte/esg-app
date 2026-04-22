import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import NarrativeSummaryCard from '../components/NarrativeSummaryCard'
import SectionCard from '../components/SectionCard'
import { Button } from '../components/ui'
import useNarrativeSummary from '../hooks/useNarrativeSummary'
import { API_BASE_URL } from '../lib/api'
import { DEFAULT_REPORT_VIEW, resolveReportFrameworkId } from '../lib/portalOptions'
import { UI_LABELS } from '../lib/uiLabels'

function normalizeReportType(report) {
  return resolveReportFrameworkId(report)
}

export default function LPReportsPage() {
  const { user } = useOutletContext()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedYear, setSelectedYear] = useState(null)
  const [message, setMessage] = useState('')
  const [download, setDownload] = useState(null)
  const narrative = useNarrativeSummary({
    user,
    audience: 'lp',
    tone: 'lp-letter',
    enabled: Boolean(user),
  })

  useEffect(() => {
    const fetchReportsData = async () => {
      try {
        setLoading(true)
        const response = await fetch(`${API_BASE_URL}/lp/reports`, {
          headers: {
            'X-User-Role': user?.role || 'investor',
            'X-User-Email': user?.email || '',
            'Content-Type': 'application/json',
          },
        })

        if (!response.ok) {
          throw new Error(`Failed to fetch reports data: ${response.status}`)
        }

        const reportsData = await response.json()
        setData(reportsData)
        setError(null)
      } catch (err) {
        console.error('Error fetching reports:', err)
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    fetchReportsData()
  }, [user])

  const availableReports = data?.available_reports || []
  const historicalArchive = data?.historical_archive || {}
  const years = useMemo(
    () => Object.keys(historicalArchive).map((y) => parseInt(y, 10)).sort((a, b) => b - a),
    [historicalArchive]
  )

  const handleGenerateAndDownload = async (report) => {
    if (String(report?.download_url || '').startsWith('/exports/')) {
      window.open(`${API_BASE_URL}${report.download_url}`, '_blank', 'noopener,noreferrer')
      return
    }
    const reportType = normalizeReportType(report)
    if (!reportType) {
      setMessage('This report type is not yet wired to export generation in V1.')
      return
    }

    try {
      setMessage(`Generating ${report.report_name}...`)
      const format = String(report.format || 'PDF').toLowerCase() === 'excel' ? 'csv' : 'pdf'
      const query = new URLSearchParams({
        format,
        period: report.year ? `FY${report.year}` : DEFAULT_REPORT_VIEW.period,
        portfolio: DEFAULT_REPORT_VIEW.portfolio,
      })
      if (format === 'pdf' && narrative.data?.status === 'approved' && narrative.data?.narrative_id) {
        query.set('narrative_id', String(narrative.data.narrative_id))
      }
      const response = await fetch(`${API_BASE_URL}/reports/${reportType}/export?${query.toString()}`, {
        headers: {
          'X-User-Role': user?.role || 'investor',
          'X-User-Email': user?.email || '',
        },
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail || 'Failed to generate report export')
      }
      const payload = await response.json()
      const url = `${API_BASE_URL}${payload.download_url}`
      window.open(url, '_blank', 'noopener,noreferrer')
      setDownload(payload)
      setMessage(`Download ready: ${payload.file_name}`)
    } catch (err) {
      setMessage(err.message)
    }
  }

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.lpReports.title} subtitle={UI_LABELS.pages.lpReports.loadingSubtitle}>
          <div className="flex items-center justify-center py-12">
            <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-[color:var(--ui-brand-primary)]" />
          </div>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.lpReports.title} subtitle={UI_LABELS.pages.lpReports.errorSubtitle}>
          <div className="rounded-lg border border-[color:var(--ui-danger-fg)] bg-[color:var(--ui-danger-bg)] p-4 text-[color:var(--ui-danger-fg)]">
            <p className="ui-text-strong">Error: {error}</p>
            <p className="text-sm mt-2">{UI_LABELS.common.backendApiReachable}</p>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="page-grid">
        <SectionCard title={UI_LABELS.pages.lpReports.title} subtitle={UI_LABELS.pages.lpReports.noDataSubtitle}>
          <p className="text-[color:var(--ui-text-muted)]">{UI_LABELS.pages.lpReports.noDataMessage}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <NarrativeSummaryCard
        title="Investor Narrative Summary"
        subtitle="Read-only portfolio narrative for investors"
        data={narrative.data}
        loading={narrative.loading}
        error={narrative.error}
        onRefresh={narrative.refresh}
      />

      <SectionCard title="Current Year Reports" subtitle="Download latest investor-ready outputs">
        <div className="space-y-3">
          {availableReports.map((report, idx) => (
            <div
              key={`${report.report_name}-${report.year}-${idx}`}
              className="flex items-center justify-between rounded-lg border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] p-4"
            >
              <div className="flex-1">
                <h3 className="ui-text-strong text-[color:var(--ui-text)]">{report.report_name}</h3>
                <div className="mt-2 flex gap-4 text-xs text-[color:var(--ui-text-muted)]">
                  <span>Date: {report.generated_date}</span>
                  <span>Format: {report.format}</span>
                  <span>Year: {report.year}</span>
                </div>
              </div>
              <Button
                onClick={() => handleGenerateAndDownload(report)}
                className="ml-4"
              >
                Download
              </Button>
            </div>
          ))}
        </div>
      </SectionCard>

      {download ? (
        <SectionCard
          title="Report Package"
          subtitle="What was included in the generated export"
        >
          <div className="space-y-3">
            <p className="text-sm text-[color:var(--ui-text)]">
              {download.narrative_included
                ? `Narrative insert attached: ${download.narrative_headline || 'Approved narrative'}`
                : 'No narrative insert was attached to this export.'}
            </p>
            {download.impact_headline ? (
              <p className="text-sm text-[color:var(--ui-text)]">
                Impact focus: {download.impact_headline}
              </p>
            ) : null}
            {Array.isArray(download.context_summary) && download.context_summary.length ? (
              <ul className="space-y-2">
                {download.context_summary.map((line) => (
                  <li key={line} className="rounded-lg border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] px-3 py-2 text-sm text-[color:var(--ui-text)]">
                    {line}
                  </li>
                ))}
              </ul>
            ) : null}
            {Array.isArray(download.benchmark_callouts) && download.benchmark_callouts.length ? (
              <div className="flex flex-wrap gap-2">
                {download.benchmark_callouts.map((callout) => (
                  <span key={callout} className="rounded-full border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] px-3 py-1 text-xs ui-text-strong text-[color:var(--ui-text-muted)]">
                    {callout}
                  </span>
                ))}
              </div>
            ) : null}
            {Array.isArray(download.comparison_rows) && download.comparison_rows.length ? (
              <div className="space-y-2">
                <p className="ui-text-strong text-[color:var(--ui-text)]">Current vs previous</p>
                <div className="grid gap-3 md:grid-cols-2">
                  {download.comparison_rows.slice(0, 4).map((row) => (
                    <div key={row.metric_name} className="rounded-lg border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface)] px-3 py-2 text-sm text-[color:var(--ui-text)]">
                      <p className="ui-text-strong">{row.metric_name}</p>
                      <p className="text-xs text-[color:var(--ui-text-muted)]">
                        Current: {row.current_value}
                        {' '}
                        {row.unit || ''}
                      </p>
                      <p className="text-xs text-[color:var(--ui-text-muted)]">
                        Previous: {row.previous_value}
                        {' '}
                        {row.unit || ''}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </SectionCard>
      ) : null}

      <SectionCard title="Historical Archives" subtitle="Generated files grouped by year">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-1">
            <label className="mb-3 block text-sm ui-text-strong text-[color:var(--ui-text)]">Filter by Year</label>
            <div className="space-y-2">
              {years.map((year) => (
                <Button
                  key={year}
                  onClick={() => setSelectedYear(selectedYear === year ? null : year)}
                  className={`w-full px-4 py-3 text-left rounded-lg transition-all font-medium ${
                    selectedYear === year
                      ? 'bg-[color:var(--ui-sidebar-active-bg)] text-[color:var(--ui-sidebar-active-text)] shadow-lg'
                      : 'bg-[color:var(--ui-surface-muted)] text-[color:var(--ui-text)] hover:bg-[color:var(--ui-border)]'
                  }`}
                >
                  {year}
                </Button>
              ))}
            </div>
          </div>
          <div className="lg:col-span-2">
            {selectedYear ? (
              <div className="space-y-3">
                {(historicalArchive[selectedYear] || []).map((report, idx) => (
                  <div key={`${report.report_name}-${idx}`} className="rounded-lg border border-[color:var(--ui-panel-border)] bg-[color:var(--ui-surface-muted)] p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h4 className="ui-text-strong text-[color:var(--ui-text)]">{report.report_name}</h4>
                        <div className="mt-2 flex gap-4 text-xs text-[color:var(--ui-text-muted)]">
                          <span>Date: {report.generated_date}</span>
                          <span>Format: {report.format}</span>
                        </div>
                      </div>
                      <Button
                        onClick={() => handleGenerateAndDownload(report)}
                        className="ml-4"
                      >
                        Download
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12 bg-gray-50 rounded-lg">
                <p className="text-gray-500 text-sm">Select a year to view archived reports</p>
              </div>
            )}
          </div>
        </div>
      </SectionCard>

      {message ? (
        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 text-sm text-gray-700">
          {message}
        </div>
      ) : null}
    </div>
  )
}


