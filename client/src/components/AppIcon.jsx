const ICON_PATHS = {
  overview: ['M4 4h6v6H4z', 'M14 4h6v6h-6z', 'M4 14h6v6H4z', 'M14 14h6v6h-6z'],
  review: ['M9 5h11', 'M9 12h11', 'M9 19h11', 'm3 5 1.5 1.5L7 4', 'm3 12 1.5 1.5L7 11', 'm3 19 1.5 1.5L7 18'],
  submissions: ['M6 2h9l5 5v15H6z', 'M14 2v6h6', 'M9 13h6', 'M9 17h6'],
  analytics: ['M4 20V10', 'M10 20V4', 'M16 20v-7', 'M22 20H2'],
  risks: ['M12 3 2.5 20h19z', 'M12 9v5', 'M12 18h.01'],
  actions: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20', 'm8 12 3 3 5-6'],
  reports: ['M6 2h9l5 5v15H6z', 'M14 2v6h6', 'M9 17v-3', 'M13 17v-6', 'M17 17v-2'],
  insights: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8', 'M22 21v-2a4 4 0 0 0-3-3.87', 'M16 3.13a4 4 0 0 1 0 7.75'],
  newsletter: ['M3 5h18v14H3z', 'm3 7 9 6 9-6'],
  anomaly: ['M3 12h4l2.5-7 5 14 2.5-7H21'],
  settings: ['M4 6h10', 'M18 6h2', 'M4 12h2', 'M10 12h10', 'M4 18h7', 'M15 18h5', 'M14 4v4', 'M6 10v4', 'M11 16v4'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  search: ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16', 'm21 21-4.35-4.35'],
  notifications: ['M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9', 'M10 21h4'],
  collapse: ['m15 18-6-6 6-6'],
  expand: ['m9 18 6-6-6-6'],
}

export default function AppIcon({ name, size = 20, className = '' }) {
  const paths = ICON_PATHS[name] || ICON_PATHS.overview
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
    >
      {paths.map((path) => (
        <path
          key={path}
          d={path}
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.8"
        />
      ))}
    </svg>
  )
}
