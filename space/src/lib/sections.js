export const SECTION_LABELS = {
  demographics: 'Demographics', case_context: 'Case context', conditions: 'Conditions',
  symptoms_function: 'Symptoms and function', observations: 'Observations', medications: 'Medications',
  procedures_devices: 'Procedures and devices', allergies: 'Allergies', oncology: 'Oncology',
  family_genetics: 'Family and genetics', reproductive_perinatal: 'Reproductive and perinatal',
  social_exposures: 'Social and exposures', outcomes: 'Outcomes', care_plans: 'Care plans',
}

export function humanize(key) {
  const text = String(key).replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function segmentSpan(ids) {
  if (!ids?.length) return ''
  return ids.length === 1 ? ids[0] : `${ids[0]}–${ids[ids.length - 1]}`
}

export const plural = (n, word, many = `${word}s`) => `${n.toLocaleString('en-US')} ${n === 1 ? word : many}`

// Whether a measurement series reads well as a line: enough numbers, mostly numbers, and some change.
export function chartable(points, value = (p) => p.value) {
  const values = points.map(value).filter((v) => typeof v === 'number' && Number.isFinite(v))
  return values.length >= 3 && values.length / points.length >= 0.6 && Math.min(...values) !== Math.max(...values)
}
