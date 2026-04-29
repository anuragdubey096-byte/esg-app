import SectionCard from './SectionCard'

export default function CollaborationPanel({
  collaboration,
  activeSection = '',
  conflictMessage = '',
}) {
  const activeSections = Array.isArray(collaboration?.active_sections) ? collaboration.active_sections : []
  const activeSession = activeSections.find((item) => item.section === activeSection) || null

  return (
    <SectionCard
      title="Live Collaboration"
      subtitle="Soft section ownership helps avoid overlapping edits"
    >
      {conflictMessage ? (
        <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {conflictMessage}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">Active section</p>
          <p className="mt-2 text-base ui-text-strong text-[color:var(--ui-text-strong)]">{activeSection || 'No section selected'}</p>
          <p className="mt-2 text-sm text-[color:var(--ui-text)]">
            {activeSession
              ? activeSession.is_you
                ? 'You currently hold the edit claim for this section.'
                : `${activeSession.owner_name || activeSession.owner_email} currently holds this section.`
              : 'No active owner for this section right now.'}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
          <p className="text-xs uppercase tracking-wide text-slate-500">Claimed sections</p>
          {activeSections.length ? (
            <div className="mt-3 space-y-2">
              {activeSections.map((session) => (
                <div key={`${session.section}-${session.id}`} className="rounded-xl border border-slate-200 px-3 py-2">
                  <p className="text-sm ui-text-strong text-[color:var(--ui-text-strong)]">{session.section}</p>
                  <p className="text-sm text-[color:var(--ui-text)]">
                    {session.is_you ? 'You' : session.owner_name || session.owner_email}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-500">No sections are actively claimed.</p>
          )}
        </div>
      </div>
    </SectionCard>
  )
}
