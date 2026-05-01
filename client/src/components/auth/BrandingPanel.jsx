const highlights = [
  { icon: '01', title: 'Real-time ESG dashboards' },
  { icon: '02', title: 'Data validation & audit trails' },
  { icon: '03', title: 'Investor-ready reporting' },
]

export default function BrandingPanel() {
  return (
    <aside className="relative flex h-full overflow-hidden bg-[radial-gradient(circle_at_18%_0%,rgba(34,211,238,0.25),transparent_35%),linear-gradient(165deg,#06162f_0%,#0b2346_46%,#0f3a56_100%)] p-8 text-white md:p-10">
      <div className="absolute -right-20 top-6 h-56 w-56 rounded-full border border-white/20 bg-white/10 blur-2xl" />
      <div className="absolute -bottom-20 -left-20 h-56 w-56 rounded-full border border-cyan-200/20 bg-cyan-200/10 blur-2xl" />
      <div className="absolute right-8 top-8 h-24 w-24 rounded-2xl border border-white/20 bg-white/5" />

      <div className="relative z-10 flex h-full flex-col">
        <div className="mb-12 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl border border-white/30 bg-white/15 text-sm font-bold tracking-wide">
            GL
          </div>
          <div>
            <p className="text-lg font-semibold">GreenLedger</p>
            <p className="text-sm text-cyan-100/90">ESG Intelligence</p>
          </div>
        </div>

        <div className="space-y-5">
          <p className="inline-flex w-fit items-center rounded-full border border-cyan-200/40 bg-cyan-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-100">
            Sustainability OS
          </p>
          <h1 className="text-3xl font-semibold leading-tight md:text-4xl">
            Unified ESG Intelligence Platform
          </h1>
          <p className="max-w-md text-sm leading-relaxed text-slate-100 md:text-base">
            Collect, validate, and analyze ESG data across your portfolio in real time.
          </p>
        </div>

        <div className="mt-10 grid gap-3">
          {highlights.map((item) => (
            <div key={item.title} className="flex items-center gap-3 rounded-xl border border-white/20 bg-white/10 px-3 py-3 backdrop-blur-sm">
              <span className="grid h-8 w-8 place-items-center rounded-md border border-white/30 bg-white/10 text-xs font-bold tracking-wide text-cyan-100">{item.icon}</span>
              <p className="text-sm font-medium text-slate-100">{item.title}</p>
            </div>
          ))}
        </div>

        <div className="mt-auto pt-8">
          <p className="text-xs uppercase tracking-[0.2em] text-cyan-100/80">Trusted Workflow</p>
          <p className="mt-2 text-sm text-slate-200/90">
            Built for managers, investors, and company teams to collaborate on one ESG source of truth.
          </p>
        </div>
      </div>
    </aside>
  )
}
