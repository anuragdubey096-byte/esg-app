import BrandingPanel from './BrandingPanel'

export default function LoginLayout({ children }) {
  return (
    <div className="min-h-screen bg-slate-100 p-3 md:p-5">
      <div className="mx-auto grid min-h-[calc(100vh-1.5rem)] max-w-7xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft md:min-h-[calc(100vh-2.5rem)] md:grid-cols-12">
        <div className="md:col-span-5">
          <BrandingPanel />
        </div>
        <div className="flex items-center justify-center p-5 md:col-span-7 md:p-10">
          <div className="w-full max-w-md">{children}</div>
        </div>
      </div>
    </div>
  )
}
