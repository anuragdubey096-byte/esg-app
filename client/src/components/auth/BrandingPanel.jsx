const highlights = [
  { icon: 'D', title: 'Real-time ESG dashboards' },
  { icon: 'V', title: 'Data validation & audit trails' },
  { icon: 'R', title: 'Investor-ready reporting' },
]

export default function BrandingPanel() {
  return (
    <aside className="relative overflow-hidden bg-gradient-to-br from-brand-700 via-brand-600 to-esg-600 p-8 text-white md:p-10">
      <div className="absolute -right-24 -top-24 h-64 w-64 rounded-full bg-white/10 blur-xl" />
      <div className="absolute -bottom-24 -left-24 h-64 w-64 rounded-full bg-emerald-200/20 blur-xl" />

      <div className="relative z-10 flex h-full flex-col">
        <div className="mb-10 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-white/15 text-sm font-bold tracking-wide">
            GL
          </div>
          <div>
            <p className="text-lg font-semibold">GreenLedger</p>
            <p className="text-sm text-white/80">ESG Intelligence</p>
          </div>
        </div>

        <div className="space-y-5">
          <h1 className="text-3xl font-semibold leading-tight md:text-4xl">
            Unified ESG Intelligence Platform
          </h1>
          <p className="max-w-md text-sm leading-relaxed text-white/90 md:text-base">
            Collect, validate, and analyze ESG data across your portfolio in real time.
          </p>
        </div>

        <div className="mt-10 grid gap-3">
          {highlights.map((item) => (
            <div key={item.title} className="flex items-center gap-3 rounded-lg border border-white/20 bg-white/10 px-3 py-3 backdrop-blur-sm">
              <span className="grid h-8 w-8 place-items-center rounded-md bg-white/20 text-sm font-semibold">{item.icon}</span>
              <p className="text-sm font-medium">{item.title}</p>
            </div>
          ))}
        </div>
      </div>
    </aside>
  )
}
