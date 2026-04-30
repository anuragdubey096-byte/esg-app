import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { API_BASE_URL } from '../../lib/api'

function normalizeRole(role) {
  const normalized = String(role || '').trim().toLowerCase()
  if (normalized === 'admin') return 'manager'
  return normalized
}

export default function AgentChat({ user: userProp = null }) {
  const outletContext = useOutletContext() || {}
  const user = userProp || outletContext.user || null

  const role = useMemo(() => normalizeRole(user?.role), [user?.role])
  const userEmail = String(user?.email || '').trim().toLowerCase()

  const [isOpen, setIsOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [history, setHistory] = useState([])
  const [errorMessage, setErrorMessage] = useState('')

  const canSend = !isLoading && Boolean(inputValue.trim()) && Boolean(role)

  async function sendMessage() {
    const message = inputValue.trim()
    if (!message || isLoading || !role) return

    const nextHistory = [...history, { role: 'user', content: message }]
    setHistory(nextHistory)
    setInputValue('')
    setErrorMessage('')
    setIsLoading(true)

    try {
      const response = await fetch(`${API_BASE_URL}/agent/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-user-role': role,
          'x-user-email': userEmail,
        },
        body: JSON.stringify({
          message,
          conversation_history: history,
          role,
        }),
      })

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(payload?.detail || 'Unable to fetch agent response.')
      }

      const returnedHistory = Array.isArray(payload?.conversation_history) ? payload.conversation_history : null
      if (returnedHistory) {
        setHistory(returnedHistory)
      } else {
        const assistantText = String(payload?.response || '').trim() || 'No response.'
        setHistory([...nextHistory, { role: 'assistant', content: assistantText }])
      }
    } catch (error) {
      setHistory([
        ...nextHistory,
        {
          role: 'assistant',
          content: `I could not process that request right now. ${String(error?.message || '')}`.trim(),
        },
      ])
      setErrorMessage(String(error?.message || 'Something went wrong.'))
    } finally {
      setIsLoading(false)
    }
  }

  function onKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      sendMessage()
    }
  }

  return (
    <div style={{ position: 'fixed', right: '1rem', bottom: '1rem', zIndex: 60 }}>
      {isOpen ? (
        <div
          style={{
            width: 'min(420px, calc(100vw - 2rem))',
            height: 'min(620px, calc(100vh - 6rem))',
            border: '1px solid #dbe7f3',
            borderRadius: '14px',
            background: 'var(--surface-1, #ffffff)',
            boxShadow: '0 18px 44px rgba(15, 23, 42, 0.16)',
            display: 'grid',
            gridTemplateRows: 'auto 1fr auto',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              borderBottom: '1px solid #dbe7f3',
              padding: '0.75rem 0.85rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '0.75rem',
              background: 'rgba(255,255,255,0.95)',
            }}
          >
            <div>
              <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.93rem' }}>ESG Agent</div>
              <div style={{ color: '#64748b', fontSize: '0.78rem' }}>
                Role: {role || 'unknown'}
              </div>
            </div>
            <button className="icon-button" type="button" onClick={() => setIsOpen(false)} aria-label="Close chat">
              x
            </button>
          </div>

          <div
            style={{
              overflowY: 'auto',
              padding: '0.8rem',
              display: 'grid',
              alignContent: 'start',
              gap: '0.55rem',
              background: 'linear-gradient(180deg, #fbfdff, #f7fbff)',
            }}
          >
            {history.length === 0 ? (
              <div
                style={{
                  color: '#64748b',
                  border: '1px dashed #cbd5e1',
                  borderRadius: '10px',
                  padding: '0.65rem 0.7rem',
                  fontSize: '0.85rem',
                }}
              >
                Ask for submission data, variance checks, portfolio metrics, or ESG report support.
              </div>
            ) : null}

            {history.map((item, index) => {
              const isUser = item.role === 'user'
              return (
                <div
                  key={`${item.role}-${index}`}
                  style={{
                    justifySelf: isUser ? 'end' : 'start',
                    maxWidth: '88%',
                    borderRadius: '11px',
                    padding: '0.55rem 0.68rem',
                    fontSize: '0.86rem',
                    lineHeight: 1.4,
                    whiteSpace: 'pre-wrap',
                    border: isUser ? '1px solid #bfdbfe' : '1px solid #dbe7f3',
                    background: isUser ? '#e8f1ff' : '#ffffff',
                    color: '#1e293b',
                  }}
                >
                  {String(item.content || '')}
                </div>
              )
            })}

            {isLoading ? (
              <div
                style={{
                  justifySelf: 'start',
                  borderRadius: '11px',
                  border: '1px solid #dbe7f3',
                  background: '#ffffff',
                  color: '#486581',
                  padding: '0.55rem 0.68rem',
                  fontSize: '0.85rem',
                }}
              >
                Agent is analyzing your request...
              </div>
            ) : null}
          </div>

          <div style={{ borderTop: '1px solid #dbe7f3', padding: '0.7rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.55rem', alignItems: 'end' }}>
              <textarea
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                onKeyDown={onKeyDown}
                placeholder={role ? 'Ask the ESG agent...' : 'User role unavailable'}
                rows={2}
                disabled={isLoading || !role}
                style={{
                  resize: 'none',
                  border: '1px solid #cbd5e1',
                  borderRadius: '10px',
                  padding: '0.6rem 0.68rem',
                  fontFamily: 'inherit',
                  fontSize: '0.86rem',
                  outline: 'none',
                }}
              />
              <button className="button" type="button" onClick={sendMessage} disabled={!canSend}>
                Send
              </button>
            </div>
            {errorMessage ? (
              <div style={{ marginTop: '0.45rem', color: '#b45309', fontSize: '0.77rem' }}>{errorMessage}</div>
            ) : null}
          </div>
        </div>
      ) : (
        <button
          className="button"
          type="button"
          onClick={() => setIsOpen(true)}
          style={{
            borderRadius: '999px',
            padding: '0.72rem 1.05rem',
            boxShadow: '0 12px 30px rgba(15, 23, 42, 0.2)',
          }}
        >
          ESG Agent
        </button>
      )}
    </div>
  )
}
