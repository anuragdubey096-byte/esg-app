export default function SubmissionConfirmDialog({ companyName, onCancel, onConfirm, submitting }) {
  return (
    <div className="submission-dialog-backdrop" role="presentation">
      <section
        className="submission-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="submission-confirm-title"
        aria-describedby="submission-confirm-description"
      >
        <p className="submission-progress-eyebrow">Final confirmation</p>
        <h3 id="submission-confirm-title">Submit this ESG report?</h3>
        <p id="submission-confirm-description">
          You are submitting the current reporting-cycle data for <strong>{companyName}</strong>. The form will be locked until a manager requests resubmission.
        </p>
        <div className="submission-dialog-actions">
          <button type="button" onClick={onCancel} disabled={submitting}>Go back</button>
          <button type="button" className="confirm" onClick={onConfirm} disabled={submitting} autoFocus>
            {submitting ? 'Submitting...' : 'Confirm submission'}
          </button>
        </div>
      </section>
    </div>
  )
}
