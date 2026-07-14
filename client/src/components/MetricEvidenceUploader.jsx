import { useRef, useState } from 'react'

function formatFileSize(bytes) {
  if (!Number.isFinite(Number(bytes)) || Number(bytes) <= 0) return '0 KB'
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function MetricEvidenceUploader({ disabled = false, evidence = [], metricKey, onRemove, onUpload, required = false }) {
  const inputRef = useRef(null)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')

  const uploadSelectedFile = async () => {
    const file = inputRef.current?.files?.[0]
    if (!file) {
      setMessage('Choose a file first.')
      return
    }
    setUploading(true)
    setMessage('')
    try {
      await onUpload(metricKey, file)
      if (inputRef.current) inputRef.current.value = ''
      setMessage('Upload complete.')
    } catch (error) {
      setMessage(error.message || 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="metric-evidence">
      <div className="metric-evidence-upload">
        <label htmlFor={`evidence-${metricKey}`}>Supporting evidence{required ? ' (required)' : ''}</label>
        <input
          ref={inputRef}
          id={`evidence-${metricKey}`}
          type="file"
          disabled={disabled || uploading}
          accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.png,.jpg,.jpeg"
        />
        <button type="button" disabled={disabled || uploading} onClick={uploadSelectedFile}>
          {uploading ? 'Uploading...' : 'Upload'}
        </button>
      </div>
      {message ? <p className="metric-evidence-message" role="status">{message}</p> : null}
      {evidence.length ? (
        <ul className="metric-evidence-list">
          {evidence.map((item) => (
            <li key={item.id}>
              <span aria-hidden="true">✓</span>
              <div>
                <strong>{item.filename}</strong>
                <small>{formatFileSize(item.file_size)} · {item.status}</small>
              </div>
              <button type="button" disabled={disabled} onClick={() => onRemove(item.id)} aria-label={`Remove ${item.filename}`}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : <small className="metric-evidence-empty">{required ? 'Required evidence not attached' : 'No evidence attached'}</small>}
    </div>
  )
}
