import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import SectionCard from '../components/SectionCard'
import DataTable from '../components/DataTable'
import { API_BASE_URL } from '../lib/api'

const BACKEND_URL = API_BASE_URL

export default function NewsletterOpsPage() {
  const { user } = useOutletContext()
  const [audience, setAudience] = useState(String(user?.role || '').toLowerCase() === 'investor' ? 'investor' : 'manager')
  const [tone, setTone] = useState('board-ready')
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const runAction = async (path, method = 'POST') => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`${BACKEND_URL}${path}`, {
        method,
        headers: {
          'x-user-role': user?.role || '',
          'x-user-email': user?.email || '',
        },
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.detail || `Request failed (${response.status})`)
      }
      const data = await response.json()
      setPayload(data)
    } catch (requestError) {
      setPayload(null)
      setError(requestError.message || 'Newsletter request failed.')
    } finally {
      setLoading(false)
    }
  }

  const highlightRows = useMemo(
    () =>
      (payload?.highlights || []).map((item, index) => ({
        id: index + 1,
        highlight: item,
      })),
    [payload],
  )

  return (
    <div className="page-grid">
      <SectionCard title="Newsletter Operations" subtitle="Phase 6 compatibility routes for generate/export/send">
        <div className="action-row">
          <label>
            Audience
            <select value={audience} onChange={(event) => setAudience(event.target.value)}>
              <option value="manager">Manager</option>
              <option value="investor">Investor</option>
            </select>
          </label>
          <label>
            Tone
            <input value={tone} onChange={(event) => setTone(event.target.value)} />
          </label>
        </div>
        <div className="action-row">
          <button className="button" type="button" onClick={() => runAction(`/newsletter/generate?audience=${audience}&tone=${encodeURIComponent(tone)}`)} disabled={loading}>
            {loading ? 'Working...' : 'Generate'}
          </button>
          <button className="button" type="button" onClick={() => runAction(`/newsletter/export?audience=${audience}&tone=${encodeURIComponent(tone)}`)} disabled={loading}>
            Export
          </button>
          <button className="button good" type="button" onClick={() => runAction(`/newsletter/send?audience=${audience}&tone=${encodeURIComponent(tone)}&dry_run=true`)} disabled={loading}>
            Send Dry Run
          </button>
        </div>
        {error ? <p>{error}</p> : null}
      </SectionCard>

      <SectionCard title="Cron Trigger" subtitle="Temporarily disabled">
        <p>Cron newsletter trigger is disabled for now.</p>
      </SectionCard>

      <SectionCard title="Newsletter Preview" subtitle="Latest generated payload">
        {payload ? (
          <>
            <p><strong>{payload.subject_line || 'No subject'}</strong></p>
            <p>{payload.summary || 'No summary available.'}</p>
            <p>Status: {payload.delivery_status || 'generated'}</p>
            {payload.download_url ? (
              <p><a href={`${BACKEND_URL}${payload.download_url}`} target="_blank" rel="noreferrer">Open Export</a></p>
            ) : null}
          </>
        ) : (
          <p>Run one of the actions above to load preview data.</p>
        )}
      </SectionCard>

      <SectionCard title="Highlights" subtitle="Narrative highlights for distribution">
        <DataTable
          columns={[{ key: 'highlight', label: 'Highlight', sortable: false }]}
          rows={highlightRows}
          pageSize={6}
          emptyMessage="No highlights yet."
        />
      </SectionCard>
    </div>
  )
}
