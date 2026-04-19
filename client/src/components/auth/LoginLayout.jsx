import BrandingPanel from './BrandingPanel'

export default function LoginLayout({ children }) {
  return (
    <div className="app-login-shell">
      <div className="app-login-stage">
        <div className="app-login-brand-pane">
          <BrandingPanel />
        </div>
        <div className="app-login-form-pane">
          <div className="app-login-form-inner">{children}</div>
        </div>
      </div>
    </div>
  )
}
