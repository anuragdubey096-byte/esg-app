import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import RouteLoadingState from './components/RouteLoadingState'
import { getAllowedNavItems, getDefaultDashboardPath } from './dashboardNavigation'
import AdminLayout from './layouts/AdminLayout'

const ActionPlansPage = lazy(() => import('./pages/ActionPlansPage'))
const AdminSettingsPage = lazy(() => import('./pages/AdminSettingsPage'))
const AlertsRisksPage = lazy(() => import('./pages/AlertsRisksPage'))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'))
const AnomalyIntelPage = lazy(() => import('./pages/AnomalyIntelPage'))
const InvestorAnalyticsPage = lazy(() => import('./pages/InvestorAnalyticsPage'))
const InvestorOverviewPage = lazy(() => import('./pages/InvestorOverviewPage'))
const LPInsightsPage = lazy(() => import('./pages/LPInsightsPage'))
const NewsletterOpsPage = lazy(() => import('./pages/NewsletterOpsPage'))
const OverviewPage = lazy(() => import('./pages/OverviewPage'))
const PortfolioOnboardingPage = lazy(() => import('./pages/PortfolioOnboardingPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const ReviewHubPage = lazy(() => import('./pages/ReviewHubPage'))
const SubmissionsPage = lazy(() => import('./pages/SubmissionsPage'))
const StrategyPage = lazy(() => import('./pages/StrategyPage'))
const CompanyAnalyticsPage = lazy(() => import('./pages/CompanyAnalyticsPage'))

function withRouteLoading(element) {
  return <Suspense fallback={<RouteLoadingState />}>{element}</Suspense>
}

export default function Dashboard({ user, onLogout }) {
  const allowedNavItems = getAllowedNavItems(user?.role)
  const defaultPath = getDefaultDashboardPath(user?.role)
  const normalizedRole = String(user?.role || '').toLowerCase()
  const isInvestor = normalizedRole === 'investor'
  const isCompany = normalizedRole === 'company'
  const pageByPath = {
    '/overview': isInvestor ? <InvestorOverviewPage /> : <OverviewPage />,
    '/submissions': <SubmissionsPage />,
    '/review-hub': <ReviewHubPage />,
    '/analytics': isInvestor ? <InvestorAnalyticsPage /> : (isCompany ? <CompanyAnalyticsPage /> : <AnalyticsPage />),
    '/alerts-risks': <AlertsRisksPage />,
    '/action-plans': <ActionPlansPage />,
    '/reports': <ReportsPage />,
    '/lp-insights': <LPInsightsPage />,
    '/newsletter-ops': <NewsletterOpsPage />,
    '/anomaly-intel': <AnomalyIntelPage />,
    '/admin-settings': <AdminSettingsPage />,
    '/portfolio-onboarding': <PortfolioOnboardingPage />,
    '/strategy': <StrategyPage />,
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AdminLayout user={user} onLogout={onLogout} navItems={allowedNavItems} />}>
          <Route index element={<Navigate to={defaultPath} replace />} />
          {allowedNavItems.map((item) => (
            <Route key={item.to} path={item.to.replace(/^\//, '')} element={withRouteLoading(pageByPath[item.to])} />
          ))}
        </Route>
        <Route path="*" element={<Navigate to={defaultPath} replace />} />
      </Routes>
    </BrowserRouter>
  )
}
