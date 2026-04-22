import { useEffect, useState } from 'react'
import { API_BASE_URL } from '../lib/api'

export default function useNewsletterSummary({ user, audience, tone = 'board-ready', enabled = true } = {}) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshToken, setRefreshToken] = useState(0)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState('')

  useEffect(() => {
    let active = true

    const fetchNewsletter = async () => {
      if (!enabled || !user?.role || !audience) {
        setData(null)
        setError('')
        setLoading(false)
        return
      }

      setLoading(true)
      setError('')
      try {
        const response = await fetch(`${API_BASE_URL}/newsletter/generate`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-User-Role': user?.role || '',
            'X-User-Email': user?.email || '',
          },
          body: JSON.stringify({
            audience,
            tone,
            force_refresh: false,
          }),
        })

        const payload = await response.json().catch(() => ({}))
        if (!response.ok) {
          throw new Error(payload.detail || `Failed to load newsletter digest (${response.status})`)
        }

        if (active) {
          setData(payload)
        }
      } catch (err) {
        if (active) {
          setError(err.message || 'Unable to load newsletter digest.')
          setData(null)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    fetchNewsletter()
    return () => {
      active = false
    }
  }, [audience, enabled, refreshToken, tone, user?.email, user?.role])

  const refresh = () => setRefreshToken((current) => current + 1)

  const exportNewsletter = async () => {
    if (!enabled || !user?.role || !audience) {
      throw new Error('Newsletter export is unavailable.')
    }

    setExporting(true)
    setExportError('')
    try {
      const response = await fetch(`${API_BASE_URL}/newsletter/export`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': user?.role || '',
          'X-User-Email': user?.email || '',
        },
        body: JSON.stringify({
          audience,
          tone,
          force_refresh: false,
        }),
      })

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail || `Failed to export newsletter digest (${response.status})`)
      }

      if (payload.download_url) {
        const link = document.createElement('a')
        link.href = `${API_BASE_URL}${payload.download_url}`
        if (payload.file_name) {
          link.download = payload.file_name
        }
        link.rel = 'noopener noreferrer'
        document.body.appendChild(link)
        link.click()
        link.remove()
      }

      return payload
    } catch (err) {
      setExportError(err.message || 'Unable to export newsletter digest.')
      throw err
    } finally {
      setExporting(false)
    }
  }

  const sendNewsletter = async () => {
    if (!enabled || !user?.role || !audience) {
      throw new Error('Newsletter delivery is unavailable.')
    }

    setSending(true)
    setSendError('')
    try {
      const response = await fetch(`${API_BASE_URL}/newsletter/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': user?.role || '',
          'X-User-Email': user?.email || '',
        },
        body: JSON.stringify({
          audience,
          tone,
          force_refresh: false,
          dry_run: false,
          recipient_emails: [],
        }),
      })

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload.detail || `Failed to send newsletter digest (${response.status})`)
      }

      return payload
    } catch (err) {
      setSendError(err.message || 'Unable to send newsletter digest.')
      throw err
    } finally {
      setSending(false)
    }
  }

  return { data, loading, error, refresh, exportNewsletter, exporting, exportError, sendNewsletter, sending, sendError }
}
