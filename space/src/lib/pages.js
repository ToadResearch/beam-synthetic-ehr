// The pages of a patient's extracted record, in the order the section menu lists them.
const SECTIONS = [
  ['demographics', 'Demographics'], ['conditions', 'Conditions'], ['symptoms_function', 'Symptoms & function'],
  ['medications', 'Medications'], ['procedures_devices', 'Procedures & devices'], ['observations', 'Observations'],
  ['allergies', 'Allergies'], ['family_genetics', 'Family & genetics'], ['reproductive_perinatal', 'Reproductive & perinatal'],
  ['oncology', 'Oncology'], ['social_exposures', 'Social & exposures'], ['outcomes', 'Outcomes'], ['care_plans', 'Care plans'],
]

export const labelOf = (key, fallback) => SECTIONS.find(([k]) => k === key)?.[1] ?? fallback

export function pagesOf(patient) {
  const present = new Set(patient.sections.map((s) => s.key))
  return [
    patient.caseContext && { key: 'context', label: 'Case context' },
    patient.summary.length && { key: 'summary', label: 'Summary' },
    patient.timeline.length && { key: 'timeline', label: 'Timeline' },
    patient.series.length && { key: 'measurements', label: 'Measurements' },
    ...SECTIONS.filter(([k]) => present.has(k)).map(([key, label]) => ({ key, label, section: true })),
    { key: 'raw', label: 'Raw data', quiet: true },
  ].filter(Boolean)
}
