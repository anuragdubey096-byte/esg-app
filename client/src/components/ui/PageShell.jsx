export default function PageShell({ children, className = '' }) {
  return <div className={`ui-page-shell ${className}`.trim()}>{children}</div>
}

