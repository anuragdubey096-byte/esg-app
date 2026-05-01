import BrandingPanel from './BrandingPanel'

export default function LoginLayout({ children }) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 p-3 md:p-6">
      <div className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-cyan-400/20 blur-3xl" />
      <div className="pointer-events-none absolute -right-20 top-16 h-80 w-80 rounded-full bg-blue-500/20 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-28 left-1/3 h-80 w-80 rounded-full bg-teal-400/15 blur-3xl" />

      <div className="mx-auto grid min-h-[calc(100vh-1.5rem)] max-w-7xl overflow-hidden rounded-3xl border border-white/15 bg-white/[0.04] shadow-[0_30px_80px_rgba(2,6,23,0.45)] backdrop-blur-sm md:min-h-[calc(100vh-3rem)] md:grid-cols-12">
        <div className="md:col-span-5">
          <BrandingPanel />
        </div>
        <div className="flex items-center justify-center bg-white/95 p-5 md:col-span-7 md:p-10">
          <div className="w-full max-w-md">{children}</div>
        </div>
      </div>
    </div>
  )
}
