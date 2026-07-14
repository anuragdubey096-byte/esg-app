function displayValue(value) {
  if (value === null || value === undefined || value === '') return 'Not provided'
  return String(value)
}

export default function SubmissionReviewScreen({ evidence = [], errors = [], formValues, onBack, onConfirm, sections }) {
  const evidenceByMetric = evidence.reduce((lookup, item) => {
    const key = item.metric_key || 'general'
    if (!lookup[key]) lookup[key] = []
    lookup[key].push(item)
    return lookup
  }, {})

  return (
    <section className="submission-review" aria-labelledby="submission-review-title">
      <header className="submission-review-header">
        <div>
          <p className="submission-progress-eyebrow">Review submission</p>
          <h3 id="submission-review-title">Check your ESG report before sending</h3>
          <p>Confirm reported values, confidence levels, supporting evidence, and validation results.</p>
        </div>
        <button type="button" onClick={onBack}>Back to form</button>
      </header>

      <div className={`submission-review-validation ${errors.length ? 'has-errors' : 'ready'}`}>
        <strong>{errors.length ? `${errors.length} validation items require attention` : 'All required validation checks passed'}</strong>
        {errors.length ? (
          <ul>{errors.slice(0, 8).map((error) => <li key={error}>{error}</li>)}</ul>
        ) : <p>The report is ready for final confirmation.</p>}
      </div>

      <div className="submission-review-sections">
        {sections.map((section) => (
          <article key={section.key}>
            <header>
              <div>
                <span>{section.title.slice(0, 1)}</span>
                <h4>{section.title}</h4>
              </div>
              <strong>{section.fields.length} metrics</strong>
            </header>
            <dl>
              {section.fields.map((field) => (
                <div key={field.name}>
                  <dt>{field.label}</dt>
                  <dd>
                    <strong>{displayValue(formValues[field.name])}</strong>
                    {formValues[`${field.name}_confidence`] ? <small>Confidence: {formValues[`${field.name}_confidence`]}</small> : null}
                    {(evidenceByMetric[field.name] || []).map((item) => (
                      <small className="review-evidence" key={item.id}>Evidence: {item.filename} · {item.status}</small>
                    ))}
                  </dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>

      <section className="submission-review-evidence" aria-labelledby="review-evidence-title">
        <h4 id="review-evidence-title">Evidence summary</h4>
        {evidence.length ? (
          <ul>
            {evidence.map((item) => <li key={item.id}><strong>{item.metric_key.replace(/_/g, ' ')}</strong><span>{item.filename}</span><b>{item.status}</b></li>)}
          </ul>
        ) : <p>No supporting evidence has been uploaded.</p>}
      </section>

      <footer className="submission-review-actions">
        <button type="button" onClick={onBack}>Continue editing</button>
        <button type="button" className="confirm" onClick={onConfirm} disabled={errors.length > 0}>Confirm and submit</button>
      </footer>
    </section>
  )
}
