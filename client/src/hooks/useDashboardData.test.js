import { describe, expect, it } from 'vitest'
import {
  getAvailableReportingYears,
  getSubmissionForReportingYear,
  getSubmissionReportingYear,
} from './useDashboardData'

function submission(id, reportingYear, cycleYear = null) {
  return {
    id,
    cycle: cycleYear ? { cycle_year: cycleYear } : null,
    esg_data: JSON.stringify(reportingYear ? { reporting_year: reportingYear } : {}),
  }
}

describe('company analytics reporting-year selection', () => {
  const submissions = [
    submission(31, 2023),
    submission(9, 2025),
    submission(18, 2024),
    submission(12, 2025),
  ]

  it('lists unique reporting years from newest to oldest', () => {
    expect(getAvailableReportingYears(submissions)).toEqual([2025, 2024, 2023])
  })

  it('selects the newest reporting year regardless of API array order', () => {
    expect(getSubmissionForReportingYear(submissions, 'Latest')?.id).toBe(12)
  })

  it('selects the latest submission within a chosen reporting year', () => {
    expect(getSubmissionForReportingYear(submissions, '2025')?.id).toBe(12)
    expect(getSubmissionForReportingYear(submissions, 2024)?.id).toBe(18)
  })

  it('uses the cycle year when the payload has no reporting year', () => {
    const cycleOnly = submission(44, null, 2022)
    expect(getSubmissionReportingYear(cycleOnly)).toBe(2022)
    expect(getSubmissionForReportingYear([cycleOnly], '2022')).toBe(cycleOnly)
  })

  it('returns null for missing data or an unavailable year', () => {
    expect(getSubmissionForReportingYear([], 'Latest')).toBeNull()
    expect(getSubmissionForReportingYear(submissions, '2021')).toBeNull()
    expect(getSubmissionForReportingYear(submissions, 'invalid')).toBeNull()
  })
})
