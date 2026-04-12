import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AdminLayout from './layouts/AdminLayout'
import ActionPlansPage from './pages/ActionPlansPage'
import AdminSettingsPage from './pages/AdminSettingsPage'
import AlertsRisksPage from './pages/AlertsRisksPage'
import AnalyticsPage from './pages/AnalyticsPage'
import { getAllowedNavItems, getDefaultDashboardPath } from './dashboardNavigation'
import OverviewPage from './pages/OverviewPage'
import ReportsPage from './pages/ReportsPage'
import ReviewHubPage from './pages/ReviewHubPage'
import SubmissionsPage from './pages/SubmissionsPage'

export default function Dashboard({ user, onLogout }) {
  const allowedNavItems = getAllowedNavItems(user?.role)
  const defaultPath = getDefaultDashboardPath(user?.role)
  const pageByPath = {
    '/overview': <OverviewPage />,
    '/submissions': <SubmissionsPage />,
    '/review-hub': <ReviewHubPage />,
    '/analytics': <AnalyticsPage />,
    '/alerts-risks': <AlertsRisksPage />,
    '/action-plans': <ActionPlansPage />,
    '/reports': <ReportsPage />,
    '/admin-settings': <AdminSettingsPage />,
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AdminLayout user={user} onLogout={onLogout} navItems={allowedNavItems} />}>
          <Route index element={<Navigate to={defaultPath} replace />} />
          {allowedNavItems.map((item) => (
            <Route key={item.to} path={item.to} element={pageByPath[item.to]} />
          ))}
        </Route>
        <Route path="*" element={<Navigate to={defaultPath} replace />} />
      </Routes>
    </BrowserRouter>
  )
}
