import { useEffect, useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import NarrativeSummaryCard from '../components/NarrativeSummaryCard'
import SectionCard from '../components/SectionCard'
import { Button } from '../components/ui'
import useNarrativeSummary from '../hooks/useNarrativeSummary'
import { API_BASE_URL } from '../lib/api'

function normalizeReportType(report) {
  if (report?.report_type) return String(report.report_type).toLowerCase()
  const name = String(report?.report_name || '').toLowerCase()
  if (name.includes('edci')) return 'edci'
  if (name.includes('sfdr')) return 'sfdr'
  return null
}

export default function LPReportsPage() {
  const { user } = useOutletContext()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedYear, setSelectedYear] = useState(null)
  const [message, setMessage] = useState('')
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
        period: report.year ? `FY${report.year}` : 'Current Cycle',
        portfolio: 'All Portfolio Companies',
      })
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
      setMessage(`Download ready: ${payload.file_name}`)
    } catch (err) {
      setMessage(err.message)
    }
  }

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="Reports & Downloads" subtitle="Loading data...">
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="Reports & Downloads" subtitle="Error loading data">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">
            <p className="ui-text-strong">Error: {error}</p>
            <p className="text-sm mt-2">Make sure the backend API is reachable.</p>
          </div>
        </SectionCard>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="page-grid">
        <SectionCard title="Reports & Downloads" subtitle="No data available">
          <p className="text-gray-600">Unable to load reports data.</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <NarrativeSummaryCard
        title="LP Narrative Summary"
        subtitle="Read-only portfolio narrative for investors"
        data={narrative.data}
        loading={narrative.loading}
        error={narrative.error}
        onRefresh={narrative.refresh}
      />

      <SectionCard title="Current Year Reports" subtitle="Download latest LP-ready outputs">
        <div className="space-y-3">
          {availableReports.map((report, idx) => (
            <div
              key={`${report.report_name}-${report.year}-${idx}`}
              className="flex items-center justify-between p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200"
            >
              <div className="flex-1">
                <h3 className="ui-text-strong text-gray-800">{report.report_name}</h3>
                <div className="flex gap-4 mt-2 text-xs text-gray-500">
                  <span>Date: {report.generated_date}</span>
                  <span>Format: {report.format}</span>
                  <span>Year: {report.year}</span>
                </div>
              </div>
              <Button
                onClick={() => handleGenerateAndDownload(report)}
                className="ml-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
              >
                Download
              </Button>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Historical Archives" subtitle="Generated files grouped by year">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-1">
            <label className="block text-sm ui-text-strong text-gray-700 mb-3">Filter by Year</label>
            <div className="space-y-2">
              {years.map((year) => (
                <Button
                  key={year}
                  onClick={() => setSelectedYear(selectedYear === year ? null : year)}
                  className={`w-full px-4 py-3 text-left rounded-lg transition-all font-medium ${
                    selectedYear === year
                      ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
                  <div key={`${report.report_name}-${idx}`} className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h4 className="ui-text-strong text-gray-800">{report.report_name}</h4>
                        <div className="flex gap-4 mt-2 text-xs text-gray-500">
                          <span>Date: {report.generated_date}</span>
                          <span>Format: {report.format}</span>
                        </div>
                      </div>
                      <Button
                        onClick={() => handleGenerateAndDownload(report)}
                        className="ml-4 px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors text-sm font-medium"
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


