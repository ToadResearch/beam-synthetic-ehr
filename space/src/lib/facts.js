// How the facts panel partitions a section: sub-groups by the kind or role the model assigned, and facts that
// repeat one name (a lab value read at several times, a dose that changed) folded into one row.
import { humanize } from './sections.js'

const ROLE = { primary_diagnosis: 'Diagnosis', complication: 'Complications', comorbidity: 'Other conditions', history: 'History', differential: 'Considered' }
const KIND = {
  symptoms_function: { symptom: 'Symptoms', sign: 'Signs', functional_status: 'Function', mental_status: 'Mental status', performance_score: 'Scores', quality_of_life: 'Quality of life' },
  observations: { laboratory: 'Laboratory', imaging: 'Imaging', vital: 'Vital signs', physiologic: 'Physiologic', microbiology: 'Microbiology', pathology: 'Pathology', other: 'Other' },
  procedures_devices: { procedure: 'Procedures', nonpharmacologic_therapy: 'Therapies', device: 'Devices' },
  family_genetics: { family_condition: 'Family history', genetic_test: 'Genetic tests', consanguinity: 'Family history' },
}

function groupOf(section, f) {
  if (section === 'conditions') {
    if (f.assertion === 'absent') return 'Ruled out'
    if (f.assertion === 'possible') return 'Possible'
    return ROLE[f.fields.role] || 'Other conditions'
  }
  if (section === 'symptoms_function' && f.assertion === 'absent') return 'Absent'
  const kinds = KIND[section]
  return kinds ? kinds[f.fields.kind] || 'Other' : null
}

const ORDER = ['Diagnosis', 'Complications', 'Other conditions', 'History', 'Considered', 'Possible', 'Ruled out',
  'Symptoms', 'Signs', 'Scores', 'Function', 'Mental status', 'Quality of life', 'Absent',
  'Laboratory', 'Vital signs', 'Physiologic', 'Imaging', 'Microbiology', 'Pathology',
  'Procedures', 'Therapies', 'Devices', 'Family history', 'Genetic tests', 'Other']

// What a row shows. Facts without a name of their own (outcomes, care plans, perinatal events, allergies)
// carry the section's label as their name; their content is in the value or the fields.
export function describe(f, section, label) {
  const generic = !f.name || f.name === label
  switch (section) {
    case 'outcomes': return generic ? { name: f.value || label, value: null, tag: f.fields.event ? humanize(f.fields.event).toLowerCase() : null } : { name: f.name, value: f.value, tag: null }
    case 'care_plans': return { name: f.fields.action_text || f.value || f.name, value: null, tag: f.fields.plan_type && f.fields.plan_type !== 'other' ? humanize(f.fields.plan_type).toLowerCase() : null }
    case 'reproductive_perinatal': return generic ? { name: f.fields.event ? humanize(f.fields.event) : label, value: f.value, tag: null } : { name: f.name, value: f.value, tag: null }
    case 'allergies': return { name: generic ? f.fields.substance || label : f.name, value: f.value || f.fields.reaction || null, tag: null }
    default: return generic && f.value ? { name: f.value, value: null, tag: null } : { name: f.name, value: f.value, tag: null }
  }
}

// [{ label, count, rows: [{ fact } | { name, facts }] }], in a fixed clinical order; label is null for one group.
export function partition(section) {
  const groups = new Map()
  for (const f of section.items) {
    const g = groupOf(section.key, f)
    if (!groups.has(g)) groups.set(g, [])
    groups.get(g).push(f)
  }
  const out = [...groups.entries()]
    .sort((a, b) => (ORDER.indexOf(a[0]) + 1 || 99) - (ORDER.indexOf(b[0]) + 1 || 99))
    .map(([label, facts]) => ({ label: groups.size > 1 ? label : null, count: facts.length, rows: fold(facts, section) }))
  return out
}

function fold(facts, section) {
  const byName = new Map()
  const rows = []
  for (const f of facts) {
    const name = describe(f, section.key, section.label).name
    const key = String(name).toLowerCase()
    if (byName.has(key)) { byName.get(key).facts.push(f); continue }
    const row = { name, facts: [f] }
    byName.set(key, row)
    rows.push(row)
  }
  return rows.map((r) => (r.facts.length > 1 ? r : { fact: r.facts[0] }))
}

// One line that says what is inside a collapsed section.
export function teaser(section) {
  const parts = partition(section)
  if (parts.length > 1) return parts.map((p) => `${p.label} ${p.count}`).join(' · ')
  return parts[0].rows.slice(0, 5).map((r) => (r.facts ? `${r.name} ×${r.facts.length}` : describe(r.fact, section.key, section.label).name)).join(' · ')
}
