import { useEffect, useLayoutEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Dashboard from './Dashboard'
import LoginPage from './LoginPage'
import LPLayout from './layouts/LPLayout'
import CompanyLayout from './layouts/CompanyLayout'
import LPDashboardPage from './pages/LPDashboardPage'
import LPMetricsPage from './pages/LPMetricsPage'
import LPReportsPage from './pages/LPReportsPage'
import CompanyDashboardPage from './pages/CompanyDashboardPage'
import CompanySubmissionPage from './pages/CompanySubmissionPage'
import CompanySubmissionReviewPage from './pages/CompanySubmissionReviewPage'
import CompanyActionPlansPage from './pages/CompanyActionPlansPage'
import CompanyHistoricalDataPage from './pages/CompanyHistoricalDataPage'
import { ExperienceProvider } from './contexts/ExperienceContext'

export default function App() {
  const [user, setUser] = useState(null)
  const normalizedRole = String(user?.role || '').toLowerCase()
  const isLP = normalizedRole === 'investor'
  const isCompany = normalizedRole === 'company'

  return (
    <ExperienceProvider>
      {!user ? (
        <LoginPage onLogin={setUser} />
      ) : !isLP && !isCompany ? (
        <Dashboard user={user} onLogout={() => setUser(null)} />
      ) : (
        <BrowserRouter>
          <ScrollToTop />
          <Routes>
            {/* LP (Limited Partner) Routes */}
            {isLP && (
              <Route path="/" element={<LPLayout user={user} onLogout={() => setUser(null)} />}>
                <Route index element={<Navigate to="/lp/dashboard" replace />} />
                <Route path="lp/dashboard" element={<LPDashboardPage />} />
                <Route path="lp/metrics" element={<LPMetricsPage />} />
                <Route path="lp/reports" element={<LPReportsPage />} />
                <Route path="*" element={<Navigate to="/lp/dashboard" replace />} />
              </Route>
            )}

            {/* Company (Portfolio Company) Routes */}
            {isCompany && (
              <Route path="/" element={<CompanyLayout user={user} onLogout={() => setUser(null)} />}>
                <Route index element={<Navigate to="/company/dashboard" replace />} />
                <Route path="company/dashboard" element={<CompanyDashboardPage />} />
                <Route path="company/submission" element={<CompanySubmissionPage />} />
                <Route path="company/submission/review" element={<CompanySubmissionReviewPage />} />
                <Route path="company/action-plans" element={<CompanyActionPlansPage />} />
                <Route path="company/historical" element={<CompanyHistoricalDataPage />} />
                <Route path="*" element={<Navigate to="/company/dashboard" replace />} />
              </Route>
            )}

          </Routes>
        </BrowserRouter>
      )}
    </ExperienceProvider>
  )
}

function ScrollToTop() {
  const location = useLocation()

  useEffect(() => {
    if ('scrollRestoration' in window.history) {
      window.history.scrollRestoration = 'manual'
    }
  }, [])

  useLayoutEffect(() => {
    const pageContainer = document.querySelector('.page-container')
    if (pageContainer) {
      pageContainer.scrollTop = 0
    }
    window.scrollTo(0, 0)
    document.documentElement.scrollTop = 0
    document.body.scrollTop = 0
  }, [location.pathname])

  return null
}
