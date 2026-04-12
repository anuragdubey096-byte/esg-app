import { ESG_FORM_SECTIONS } from './esgFormConfig'

const metricFields = ESG_FORM_SECTIONS.flatMap((section) =>
  section.fields.filter((field) => field.type !== 'text' && field.type !== 'textarea').map((field) => field.name)
)

const confidenceFields = metricFields.map((field) => `${field}_confidence`)

export function parseESGData(raw) {
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : raw
  } catch {
    return raw
  }
}

export function formatFieldLabel(key) {
  return key
    .replace(/_confidence$/, ' confidence')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export function renderValue(value) {
  if (value === null || value === undefined || value === '') return 'Not provided'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function validateSubmissionData(formValues) {
  const checks = []
  const values = formValues && typeof formValues === 'object' ? formValues : {}

  const missingMetrics = metricFields.filter((field) => {
    const value = values[field]
    return value === null || value === undefined || value === ''
  })

  checks.push({
    label: 'Completeness check',
    status: missingMetrics.length === 0 ? 'pass' : 'fail',
    message:
      missingMetrics.length === 0
        ? 'All required metric fields have values.'
        : `Missing values: ${missingMetrics.slice(0, 5).map(formatFieldLabel).join(', ')}${missingMetrics.length > 5 ? '...' : ''}`,
  })

  const missingConfidence = confidenceFields.filter((field) => !values[field])
  checks.push({
    label: 'Data confidence check',
    status: missingConfidence.length === 0 ? 'pass' : 'fail',
    message:
      missingConfidence.length === 0
        ? 'Every measurable field includes a confidence selection.'
        : `Missing confidence flags: ${missingConfidence.slice(0, 5).map(formatFieldLabel).join(', ')}${missingConfidence.length > 5 ? '...' : ''}`,
  })

  const cautionFlags = confidenceFields.filter((field) => {
    const current = values[field]
    return current === 'Estimated' || current === 'Not Available'
  })
  checks.push({
    label: 'Analyst attention flags',
    status: cautionFlags.length === 0 ? 'pass' : 'warning',
    message:
      cautionFlags.length === 0
        ? 'No estimated or unavailable values were flagged.'
        : `${cautionFlags.length} fields are marked Estimated or Not Available.`,
  })

  const expectedTotal =
    Number(values.scope_1_emissions || 0) +
    Number(values.scope_2_location_based || 0) +
    Number(values.scope_3_emissions || 0)
  const reportedTotal = Number(values.total_ghg_emissions || 0)
  checks.push({
    label: 'GHG consistency',
    status: Math.abs(expectedTotal - reportedTotal) <= 0.01 ? 'pass' : 'fail',
    message:
      Math.abs(expectedTotal - reportedTotal) <= 0.01
        ? 'Total GHG emissions match Scope 1 + Scope 2 + Scope 3.'
        : `Expected ${expectedTotal.toFixed(2)} tCO2e but submission reports ${reportedTotal.toFixed(2)} tCO2e.`,
  })

  const renewable = Number(values.renewable_energy_consumption || 0)
  const totalEnergy = Number(values.total_energy_consumption || 0)
  checks.push({
    label: 'Energy range validation',
    status: renewable <= totalEnergy ? 'pass' : 'fail',
    message:
      renewable <= totalEnergy
        ? 'Renewable energy is within total energy consumption.'
        : 'Renewable energy consumption exceeds total energy consumption.',
  })

  const recycledWater = Number(values.water_recycled_reused || 0)
  const totalWater = Number(values.total_water_withdrawal || 0)
  checks.push({
    label: 'Water range validation',
    status: recycledWater <= totalWater ? 'pass' : 'fail',
    message:
      recycledWater <= totalWater
        ? 'Water recycled or reused is within total withdrawal.'
        : 'Water recycled or reused exceeds total withdrawal.',
  })

  const divertedWaste = Number(values.waste_diverted_from_landfill || 0)
  const totalWaste = Number(values.total_waste_generated || 0)
  checks.push({
    label: 'Waste range validation',
    status: divertedWaste <= totalWaste ? 'pass' : 'fail',
    message:
      divertedWaste <= totalWaste
        ? 'Waste diverted is within total waste generated.'
        : 'Waste diverted from landfill exceeds total waste generated.',
  })

  const reductionTarget = Number(values.reduction_target_percent || 0)
  const hasReductionSupport =
    reductionTarget === 0 ||
    (String(values.reduction_strategy_description || '').trim() &&
      Number(values.reduction_target_year || 0) >= 2026)
  checks.push({
    label: 'Reduction target support',
    status: hasReductionSupport ? 'pass' : 'fail',
    message:
      hasReductionSupport
        ? 'Reduction target fields are complete.'
        : 'Reduction targets require both a strategy description and a target year of 2026 or later.',
  })

  const documentRules = [
    ['whs_policy_in_place', 'whs_policy_document_reference', 'WHS policy'],
    ['esg_policy_in_place', 'esg_policy_document_reference', 'ESG policy'],
    ['cybersecurity_policy_in_place', 'cybersecurity_policy_document_reference', 'Cybersecurity policy'],
  ]
  const missingDocuments = documentRules
    .filter(([toggleField, docField]) => values[toggleField] === 'Yes' && !String(values[docField] || '').trim())
    .map(([, , label]) => label)

  checks.push({
    label: 'Supporting document references',
    status: missingDocuments.length === 0 ? 'pass' : 'fail',
    message:
      missingDocuments.length === 0
        ? 'Required policy references are present.'
        : `Missing required references for: ${missingDocuments.join(', ')}.`,
  })

  const summary = checks.reduce(
    (accumulator, check) => {
      accumulator[check.status] += 1
      return accumulator
    },
    { pass: 0, warning: 0, fail: 0 }
  )

  return { checks, summary }
}
