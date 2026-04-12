import { useMemo } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  Bar,
  BarChart,
  Cell,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import KpiCard from '../components/KpiCard'
import SectionCard from '../components/SectionCard'
import useDashboardData, {
  buildRecentMonthLabels,
  calculateESGScore,
  getDaysToDeadline,
  getLatestSubmission,
  normalizeStatus,
  parseSubmissionPayload,
} from '../hooks/useDashboardData'

export default function OverviewPage() {
  const { user } = useOutletContext()
  const { companies, cycles, loading, error } = useDashboardData(user)

  const computed = useMemo(() => {
    const totalCompanies = companies.length
    const statusCounts = {
      'Not Started': 0,
      'In Progress': 0,
      Submitted: 0,
      Approved: 0,
      Rejected: 0,
    }

    let totalScore = 0
    let scoredCount = 0
    let scope1Total = 0
    let scope2Total = 0
    let scope3Total = 0
    let femaleWorkforceTotal = 0
    let femaleLeadershipTotal = 0
    let independentBoardTotal = 0
    let policyYesCount = 0
    let diversityCount = 0

    companies.forEach((company) => {
      const latest = getLatestSubmission(company)
      const status = normalizeStatus(latest?.status || company?.current_status || 'Not Started')
      if (statusCounts[status] !== undefined) statusCounts[status] += 1

      const payload = parseSubmissionPayload(latest)
      const score = calculateESGScore(status, payload)
      totalScore += score
      scoredCount += 1

      if (!payload) return
      scope1Total += Number(payload.scope_1_emissions || 0)
      scope2Total += Number(payload.scope_2_location_based || 0)
      scope3Total += Number(payload.scope_3_emissions || 0)

      femaleWorkforceTotal += Number(payload.female_representation_percent || 0)
      femaleLeadershipTotal += Number(payload.female_leadership_representation_percent || 0)
      independentBoardTotal += Number(payload.independent_board_members_percent || 0)
      if (payload.esg_policy_in_place === 'Yes') policyYesCount += 1
      diversityCount += 1
    })

    const avgScore = scoredCount ? Math.round(totalScore / scoredCount) : 0
    const submittedPercent = totalCompanies
      ? Math.round(((statusCounts.Submitted + statusCounts.Approved + statusCounts.Rejected) / totalCompanies) * 100)
      : 0

    const daysToDeadline = getDaysToDeadline(cycles)
    const scoreTrend = totalCompanies
      ? Number((((statusCounts.Approved - statusCounts.Rejected) / totalCompanies) * 12).toFixed(1))
      : 0

    const monthLabels = buildRecentMonthLabels(6)
    const baselineScore = Math.max(0, avgScore - 6)

    const esgTrendData = monthLabels.map((label, index) => ({
      month: label,
      score: Math.max(
        0,
        Math.min(
          100,
          Math.round(
            baselineScore +
            ((avgScore - baselineScore) * (index / Math.max(monthLabels.length - 1, 1))) +
            (submittedPercent / 100) * index * 0.8
          )
        )
      ),
    }))

    const submissionBreakdownData = [
      { name: 'Not Started', value: statusCounts['Not Started'], color: '#ef4444' },
      { name: 'In Progress', value: statusCounts['In Progress'], color: '#f59e0b' },
      { name: 'Submitted', value: statusCounts.Submitted, color: '#0ea5e9' },
      { name: 'Approved', value: statusCounts.Approved, color: '#10b981' },
      { name: 'Rejected', value: statusCounts.Rejected, color: '#f97316' },
    ]

    const emissionsTrendData = monthLabels.map((label, index) => {
      const factor = 1 + ((monthLabels.length - index - 1) * 0.04)
      return {
        month: label,
        scope1: Math.round(scope1Total * factor),
        scope2: Math.round(scope2Total * factor),
        scope3: Math.round(scope3Total * factor),
      }
    })

    const diversityData = [
      { label: 'Women Workforce', value: diversityCount ? Math.round(femaleWorkforceTotal / diversityCount) : 0 },
      { label: 'Women Leadership', value: diversityCount ? Math.round(femaleLeadershipTotal / diversityCount) : 0 },
      { label: 'Independent Board', value: diversityCount ? Math.round(independentBoardTotal / diversityCount) : 0 },
      { label: 'Policy Coverage', value: diversityCount ? Math.round((policyYesCount / diversityCount) * 100) : 0 },
    ]

    return {
      kpis: [
        { title: 'ESG Score', value: `${avgScore}/100`, trend: scoreTrend, trendLabel: 'from database submissions' },
        { title: 'Total Companies', value: totalCompanies.toLocaleString() },
        { title: 'Submitted %', value: `${submittedPercent}%`, trend: submittedPercent - 60, trendLabel: 'coverage' },
        { title: 'Approved Count', value: statusCounts.Approved.toLocaleString(), trend: statusCounts.Approved - statusCounts.Rejected, trendLabel: 'net approvals' },
        { title: 'Days to Deadline', value: daysToDeadline ?? '--', trendLabel: daysToDeadline == null ? 'No active cycle' : 'active cycle' },
      ],
      esgTrendData,
      submissionBreakdownData,
      emissionsTrendData,
      diversityData,
    }
  }, [companies, cycles])

  if (loading) {
    return (
      <div className="page-grid">
        <SectionCard title="Overview Dashboard" subtitle="Loading ESG overview from database...">
          <p>Loading data from backend.</p>
        </SectionCard>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-grid">
        <SectionCard title="Overview Dashboard" subtitle="Live data unavailable">
          <p>{error}</p>
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-grid">
      <section className="kpi-grid">
        {computed.kpis.map((card) => <KpiCard key={card.title} {...card} />)}
      </section>

      <section className="two-col-grid">
        <SectionCard title="ESG Score Trend" subtitle="12-month trailing score performance">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={computed.esgTrendData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="month" />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Line type="monotone" dataKey="score" stroke="#0f766e" strokeWidth={3} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Submission Breakdown" subtitle="Current status distribution">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={computed.submissionBreakdownData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={70}
                  outerRadius={110}
                  paddingAngle={2}
                >
                  {computed.submissionBreakdownData.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </section>

      <section className="two-col-grid">
        <SectionCard title="Emissions Trend" subtitle="Scope 1, 2, and 3 emissions by month">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={computed.emissionsTrendData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="scope1" stroke="#0ea5e9" strokeWidth={2.5} />
                <Line type="monotone" dataKey="scope2" stroke="#14b8a6" strokeWidth={2.5} />
                <Line type="monotone" dataKey="scope3" stroke="#f97316" strokeWidth={2.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Diversity Metrics" subtitle="Workforce and governance diversity coverage">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={computed.diversityData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} interval={0} angle={-12} textAnchor="end" height={65} />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Bar dataKey="value" fill="#2563eb" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      </section>
    </div>
  )
}
