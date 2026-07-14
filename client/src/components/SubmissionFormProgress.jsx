const SAVE_LABELS = {
  dirty: 'Unsaved changes',
  saving: 'Saving draft…',
  saved: 'Draft saved',
  error: 'Save failed',
  idle: 'Ready to edit',
}

export default function SubmissionFormProgress({
  activeKey,
  errorCount = 0,
  lastSavedAt,
  onChange,
  onSave,
  overallPercent = 0,
  saveStatus = 'idle',
  sections = [],
}) {
  return (
    <section className="submission-progress" aria-labelledby="submission-progress-title">
      <header className="submission-progress-header">
        <div>
          <p className="submission-progress-eyebrow">Guided ESG submission</p>
          <h3 id="submission-progress-title">Complete your reporting sections</h3>
          <p>Work through each section, review validation items, and submit when the form is complete.</p>
        </div>
        <div className="submission-save-state">
          <span className={`save-state-dot ${saveStatus}`} aria-hidden="true" />
          <div>
            <strong>{SAVE_LABELS[saveStatus] || SAVE_LABELS.idle}</strong>
            <small>{lastSavedAt ? `Last saved ${lastSavedAt}` : 'Autosaves after a short pause'}</small>
          </div>
          <button type="button" onClick={onSave} disabled={saveStatus === 'saving'}>Save draft</button>
        </div>
      </header>

      <div className="submission-overall-progress">
        <div>
          <span>Overall completion</span>
          <strong>{overallPercent}%</strong>
        </div>
        <div
          className="submission-progress-track"
          role="progressbar"
          aria-label="Overall submission completion"
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={overallPercent}
        >
          <span style={{ width: `${overallPercent}%` }} />
        </div>
        {errorCount > 0 ? <p className="submission-error-count">{errorCount} validation item{errorCount === 1 ? '' : 's'} to resolve</p> : null}
      </div>

      <nav className="submission-stepper" aria-label="ESG form sections">
        <ol>
          {sections.map((section, index) => {
            const isActive = section.key === activeKey
            const isComplete = section.percent === 100
            return (
              <li key={section.key}>
                <button
                  type="button"
                  className={`${isActive ? 'active' : ''}${isComplete ? ' complete' : ''}`}
                  onClick={() => onChange(section.key)}
                  aria-current={isActive ? 'step' : undefined}
                >
                  <span className="submission-step-number">{isComplete ? '✓' : index + 1}</span>
                  <span>
                    <strong>{section.title}</strong>
                    <small>{section.completed} of {section.total} required items</small>
                  </span>
                  <b>{section.percent}%</b>
                </button>
              </li>
            )
          })}
        </ol>
      </nav>
    </section>
  )
}
