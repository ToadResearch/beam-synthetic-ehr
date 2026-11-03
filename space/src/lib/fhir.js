// Reading FHIR R4 resources for display. Works for any bundle; uses this dataset's extensions when present.

const tail = (url = '') => url.slice(url.lastIndexOf('/') + 1)
const parse = (text) => { try { return JSON.parse(text) } catch { return null } }

export const ICD10CM = 'http://hl7.org/fhir/sid/icd-10-cm'
const SYSTEMS = {
  [ICD10CM]: 'ICD-10-CM', 'http://snomed.info/sct': 'SNOMED CT', 'http://loinc.org': 'LOINC',
  'http://www.nlm.nih.gov/research/umls/rxnorm': 'RxNorm', 'http://hl7.org/fhir/sid/cvx': 'CVX',
}
export const systemName = (system) => SYSTEMS[system] || tail(system) || 'code'

export function extension(resource, name) {
  return (resource?.extension || []).find((x) => tail(x.url) === name)
}

// The extracted fact a resource was compiled from (evidence quotes, relative time), if the bundle carries it.
export function sourceFact(resource) {
  const x = extension(resource, 'source-fact')
  return x?.valueString ? parse(x.valueString) : null
}

export function concept(c) {
  if (!c) return ''
  return c.text || c.coding?.find((x) => x.display)?.display || c.coding?.[0]?.code || ''
}

export function codings(c) {
  return (c?.coding || []).filter((x) => x.code)
}

export function number(v) {
  if (v == null || v === '') return ''
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return Math.abs(n) >= 1000 ? n.toLocaleString('en-US', { maximumFractionDigits: 2 }) : String(+n.toPrecision(6))
}

// Table cells keep the source's span markers ("79 [rowspan=2,colspan=1]"); they are not part of the value.
export const unmark = (text) => String(text).replace(/\s*\[(?:rowspan|colspan)=\d+(?:,(?:rowspan|colspan)=\d+)*\]/g, '')

export function value(r) {
  if (r.valueQuantity) {
    // Some table rows carry their whole label as the unit ("WBC (×10³/µL)"). The name already says it, so it is left out.
    const q = r.valueQuantity
    const unit = [q.unit, q.code].find((u) => u && u !== r.code?.text)
    return [number(q.value), unit].filter(Boolean).join(' ')
  }
  if (r.valueString != null) return unmark(r.valueString)
  if (r.valueCodeableConcept) return concept(r.valueCodeableConcept)
  if (r.valueBoolean != null) return r.valueBoolean ? 'yes' : 'no'
  if (r.valueInteger != null) return String(r.valueInteger)
  if (r.valueRange) {
    const { low, high } = r.valueRange
    return `${number(low?.value)}–${number(high?.value)} ${high?.unit || low?.unit || ''}`.trim()
  }
  if (r.valueDateTime) return r.valueDateTime.slice(0, 10)
  if (r.component?.length) return r.component.map((c) => `${concept(c.code)} ${value(c) ?? ''}`.trim()).join(' · ')
  return null
}

// When it happened, as reported: dates when the bundle has them, else the article's relative wording.
export function when(r) {
  const rel = extension(r, 'reported-relative-time')
  const t = rel?.valueString ? parse(rel.valueString) : null
  if (t?.time_text) return t.time_text
  for (const k of ['effectiveDateTime', 'onsetDateTime', 'performedDateTime', 'occurrenceDateTime', 'authoredOn', 'recordedDate', 'issued', 'date']) {
    if (r[k]) return r[k].slice(0, 10)
  }
  for (const k of ['effectivePeriod', 'performedPeriod', 'period']) if (r[k]?.start) return r[k].start.slice(0, 10)
  for (const k of ['onsetString', 'performedString', 'abatementString']) if (r[k]) return r[k]
  return sourceFact(r)?.time?.text || null
}

export function dated(r) {
  for (const k of ['effectiveDateTime', 'onsetDateTime', 'performedDateTime', 'occurrenceDateTime', 'authoredOn', 'recordedDate', 'issued']) {
    if (r[k]) return r[k]
  }
  return r.effectivePeriod?.start || r.performedPeriod?.start || r.period?.start || null
}

export function title(r) {
  switch (r.resourceType) {
    case 'MedicationStatement': case 'MedicationRequest': case 'MedicationAdministration': case 'MedicationDispense':
      return concept(r.medicationCodeableConcept) || r.medicationReference?.display || 'Medication'
    case 'FamilyMemberHistory':
      return [concept(r.relationship), (r.condition || []).map((c) => concept(c.code)).join(', ')].filter(Boolean).join(': ')
    case 'CarePlan': return r.title || r.description || concept(r.category?.[0]) || 'Care plan'
    case 'Immunization': return concept(r.vaccineCode)
    case 'Encounter': return concept(r.type?.[0]) || r.class?.display || r.class?.code || 'Encounter'
    case 'Patient': return r.name?.[0]?.text || [r.name?.[0]?.given?.join(' '), r.name?.[0]?.family].filter(Boolean).join(' ') || 'Patient'
    case 'Device': return r.deviceName?.[0]?.name || concept(r.type) || 'Device'
    case 'DocumentReference': return r.description || concept(r.type) || 'Document'
    case 'Provenance': return `Provenance for ${r.target?.length ?? 0} resources`
    case 'Organization': case 'Practitioner': return r.name?.[0]?.text || r.name?.text || r.name || r.resourceType
    default: return concept(r.code) || r.resourceType
  }
}

export function conditionStatus(r) {
  const verification = r.verificationStatus?.coding?.[0]?.code || null
  const clinical = r.clinicalStatus?.coding?.[0]?.code || null
  return { verification, clinical, refuted: verification === 'refuted' }
}

export function dosage(r) {
  const d = r.dosage?.[0] || r.dosageInstruction?.[0]
  if (!d) return null
  // The compiler joins dose, route and timing with " ; ". Shown as a list.
  if (d.text) return d.text.replace(/\s+;\s+/g, ', ')
  const dose = d.doseAndRate?.[0]?.doseQuantity
  return [dose && `${number(dose.value)} ${dose.unit || ''}`.trim(), concept(d.route), d.timing?.code?.text].filter(Boolean).join(', ') || null
}

const INTERNAL = new Set(['Patient', 'Device', 'Provenance', 'DocumentReference', 'Organization', 'Practitioner', 'PractitionerRole', 'Location', 'Claim', 'ExplanationOfBenefit'])

// Group a bundle into the sections of a chart.
export function chart(bundle) {
  const resources = (bundle?.entry || []).map((e) => e.resource).filter(Boolean)
  const of = (...types) => resources.filter((r) => types.includes(r.resourceType))
  const patient = of('Patient')[0] || null

  // "Total IgE (normal range: 0–100 IU/ml)" from a table and "total IgE" from the text are one test.
  const groups = new Map()
  for (const o of of('Observation')) {
    const name = title(o)
    const key = name.toLowerCase().replace(/\s*\([^)]*\)/g, '').replace(/\s+/g, ' ').trim()
    if (!groups.has(key)) groups.set(key, { name, items: [] })
    const g = groups.get(key)
    if (name.length < g.name.length) g.name = name
    g.items.push(o)
  }
  const series = []
  const singles = []
  for (const g of groups.values()) {
    const numeric = g.items.filter((o) => typeof o.valueQuantity?.value === 'number')
    // A value read from a table cell and the same value restated in the text are one measurement:
    // plot the table series when there is one, else each distinct value once, in reading order.
    const fromTable = numeric.filter((o) => extension(o, 'reported-relative-time'))
    const seen = new Set()
    const plotted = fromTable.length >= 2 ? fromTable : numeric.filter((o) => {
      const key = `${o.valueQuantity.value}|${o.valueQuantity.unit || ''}`
      return !seen.has(key) && seen.add(key)
    })
    if (plotted.length >= 2) {
      const ordered = plotted.some(dated) ? [...plotted].sort((a, b) => String(dated(a)).localeCompare(String(dated(b)))) : plotted
      series.push({ name: g.name, unit: ordered[0].valueQuantity.unit, points: ordered.map((o, i) => ({ value: o.valueQuantity.value, label: when(o) || `${i + 1}`, resource: o })), others: g.items.filter((o) => !plotted.includes(o)) })
    } else singles.push(...g.items)
  }

  const known = new Set(['Condition', 'MedicationStatement', 'MedicationRequest', 'MedicationAdministration', 'MedicationDispense', 'Procedure', 'ServiceRequest', 'Observation', 'AllergyIntolerance', 'FamilyMemberHistory', 'CarePlan', 'Immunization', 'Encounter'])
  const counts = {}
  for (const r of resources) counts[r.resourceType] = (counts[r.resourceType] || 0) + 1

  const demographics = {}
  if (patient?.gender) demographics.sex = patient.gender
  if (patient?.birthDate) demographics.born = patient.birthDate
  for (const o of of('Observation')) {
    const name = title(o).toLowerCase()
    if (!demographics.age && /\bage\b/.test(name)) demographics.age = value(o)
    if (!demographics.sex && /\b(sex|gender)\b/.test(name)) demographics.sex = value(o)
  }

  return {
    patient, demographics, counts, total: resources.length,
    problems: of('Condition'),
    medications: of('MedicationStatement', 'MedicationRequest', 'MedicationAdministration', 'MedicationDispense'),
    procedures: of('Procedure', 'ServiceRequest'),
    series, results: singles,
    allergies: of('AllergyIntolerance'), family: of('FamilyMemberHistory'), plans: of('CarePlan'),
    immunizations: of('Immunization'), encounters: of('Encounter'),
    other: resources.filter((r) => !known.has(r.resourceType) && !INTERNAL.has(r.resourceType)),
    internals: resources.filter((r) => INTERNAL.has(r.resourceType)),
  }
}

export function isDatasetBundle(bundle) {
  return (bundle?.entry || []).some((e) => extension(e.resource, 'source-fact'))
}

// ---------------------------------------------------------------- explaining a bundle

export const TYPE_INFO = {
  Patient: 'The person the record is about. The identity is synthetic, the facts come from the article.',
  Condition: 'A problem, diagnosis or finding, with an ICD-10-CM code when one matched. Ruled-out diagnoses are kept, marked refuted.',
  Observation: 'A measurement or finding: a laboratory value, a vital sign, an imaging or exam result, a score.',
  MedicationStatement: 'A medicine the patient took or was given, with the dose and route the article reports.',
  MedicationRequest: 'A medicine that was prescribed or ordered.',
  MedicationAdministration: 'A single dose that was given.',
  Procedure: 'Something done for the patient: an operation, a scan, a biopsy, a therapy session.',
  ServiceRequest: 'An order for a test, a referral or a procedure.',
  CarePlan: 'A plan: follow-up, monitoring, advice or a treatment intention.',
  AllergyIntolerance: 'An allergy or intolerance and the reaction it causes.',
  FamilyMemberHistory: 'A condition reported in a relative.',
  Immunization: 'A vaccine given to the patient.',
  Encounter: 'A visit or a hospital stay.',
  DiagnosticReport: 'A report that groups results.',
  Device: 'Here, the compiler that built the record (the author of the Provenance).',
  Provenance: 'Who made the record and when: it lists every resource the compiler produced.',
  DocumentReference: 'An attached document: the extraction packet with every citation, kept with the record.',
}

const FIELD_INFO = {
  subject: 'Points to the Patient. This reference is what makes the resource part of this patient’s record.',
  patient: 'Points to the Patient this history belongs to.',
  code: 'What it is: the article’s wording, plus a code when one was chosen.',
  verificationStatus: 'Confirmed, suspected, or ruled out (refuted).',
  clinicalStatus: 'Active, resolved, in remission and so on, when the article says.',
  status: 'A status FHIR requires, “unknown” when the article does not say.',
  valueQuantity: 'The measured number and unit.',
  valueString: 'The value as printed when it is not a plain number.',
  referenceRange: 'The normal range printed next to the value.',
  category: 'The kind of observation: laboratory, vital signs, imaging, social history.',
  bodySite: 'Where on the body.',
  method: 'How it was measured or examined.',
  dataAbsentReason: 'Why there is no value (for a finding reported as absent or not measured).',
  medicationCodeableConcept: 'The medicine as the article names it.',
  dosage: 'Dose, route and timing as reported.',
  dosageInstruction: 'Dose, route and timing as ordered.',
  intent: 'Whether this is a plan, a proposal or an order.',
  description: 'The plan in the article’s words.',
  relationship: 'The relative.',
  condition: 'The relative’s condition.',
  extension: 'Additions this dataset makes to standard FHIR, listed below.',
  text: 'A readable summary FHIR keeps next to the structured data.',
  meta: 'Dataset tags: literature-derived facts, synthetic identity, codes not clinically reviewed.',
  id: 'This resource’s identifier inside the bundle.',
  identifier: 'A synthetic record number.',
  name: 'A placeholder name. There is no real identity.',
  target: 'Every resource this provenance covers.',
  agent: 'Who made it: the compiler software.',
  entity: 'What it was made from: the source article.',
  recorded: 'When the record was compiled.',
  content: 'The attached file (omitted in this viewer, kept in the dataset row).',
  deviceName: 'The compiler’s name and version.',
}

const EXT_INFO = {
  'source-fact': 'The extracted fact this resource was compiled from, with the quotes or table cells it rests on.',
  'source-fact-key': 'A stable fingerprint of that fact, the same across runs.',
  'reported-relative-time': 'When, in the article’s own relative terms, and the table header cell it was read from.',
  'synthetic-identity': 'Marks the identity as synthetic.',
  'source-patient-id': 'Which patient of the article this is (p1, p2 …).',
}

export const fieldInfo = (key) => FIELD_INFO[key] || null
export const extensionInfo = (url) => EXT_INFO[tail(url)] || null
export const extensionName = (url) => tail(url)

// Where a resource came from: quotes for facts from the text, cells for values read from a table.
export function sourceOf(r) {
  const fact = sourceFact(r)
  if (!fact) return null
  const quotes = (fact.evidence || []).filter((e) => e.quote && e.source_section).map((e) => ({ seg: e.source_section, quote: e.quote }))
  let cells = null
  if (fact.cells?.length) {
    const t = extension(r, 'reported-relative-time')
    const time = t?.valueString ? parse(t.valueString) : null
    const byRole = (role) => fact.cells.find((c) => c.role === role)
    const timeCell = fact.cells.find((c) => c.cell_id === time?.time_cell_id) || byRole('column_header')
    const valueCell = fact.cells.find((c) => c.role === 'value' && c.cell_id !== fact.series?.reference_range_cell_id && c.cell_id !== timeCell?.cell_id && c.raw_text && unmark(c.raw_text) === unmark(r.valueString ?? '')) ||
      fact.cells.filter((c) => c.role === 'value').at(-1)
    cells = {
      table: fact.cells[0]?.table_id || null, seg: valueCell?.segment_id || fact.cells[0]?.segment_id,
      row: byRole('row_label') ? unmark(byRole('row_label').raw_text) : fact.measurement_name,
      column: timeCell ? unmark(timeCell.raw_text) : null, value: valueCell ? unmark(valueCell.raw_text) : null,
      ids: [valueCell?.cell_id, timeCell?.cell_id, byRole('row_label')?.cell_id].filter(Boolean),
    }
  }
  return { fact, quotes, cells, seg: quotes[0]?.seg || cells?.seg || null }
}

const segNumber = (id) => { const m = /(\d+)$/.exec(id || ''); return m ? +m[1] : Infinity }
const INTERNAL_TYPES = new Set(['Patient', 'Device', 'Provenance', 'DocumentReference', 'Organization', 'Practitioner'])

// The record retold in the order the article tells it: each passage, then the resources compiled from it.
// blocks (the article's text, when available) give section headings and table labels.
export function story(bundle, blocks = []) {
  const heading = new Map()
  const rowOf = new Map()
  let h = null
  const text = (c) => (typeof c === 'string' ? c : c?.t ?? c?.text ?? '')
  for (const b of blocks) {
    if (b.type === 'heading') { h = b.text; continue }
    if (b.type === 'table') {
      // A table row is one passage, named by its row label (rows under a rowspan borrow the label above).
      const full = Math.max(0, ...(b.rows || []).filter((r) => r.kind === 'row').map((r) => r.cells.length))
      let label = null
      for (const r of [...(b.head || []).filter((x) => x.id), ...(b.rows || [])]) {
        if (r.kind === 'row' || !r.kind) label = r.cells.length >= full || !label ? unmark(text(r.cells[0])) : label
        else if (r.kind === 'group') label = unmark(text(r.cells[0]))
        if (r.id) { heading.set(r.id, h); rowOf.set(r.id, { table: b.label || 'Table', row: label }) }
      }
      for (const n of b.notes || []) heading.set(n.id, h)
      continue
    }
    const id = b.type === 'p' ? b.id : b.type === 'figure' ? b.captionId : null
    if (id) heading.set(id, h)
  }
  const items = []
  ;(bundle?.entry || []).forEach((e, i) => {
    const r = e.resource
    if (!r || INTERNAL_TYPES.has(r.resourceType)) return
    const src = sourceOf(r)
    items.push({ r, src, seg: src?.seg || null, i })
  })
  items.sort((a, b) => segNumber(a.seg) - segNumber(b.seg) || a.i - b.i)

  // Passages: resources sharing a segment and quote (or a table row) sit under one passage.
  const passages = []
  const byKey = new Map()
  for (const it of items) {
    const row = rowOf.get(it.seg) || (it.src?.cells ? { table: it.src.cells.table, row: it.src.cells.row } : null)
    const key = row ? `row:${it.seg}` : `${it.seg}:${it.src?.quotes[0]?.quote || ''}`
    let p = byKey.get(key)
    if (!p) {
      p = { key, seg: it.seg, quote: row ? null : it.src?.quotes[0]?.quote || null, cells: row, heading: heading.get(it.seg) ?? null, items: [] }
      byKey.set(key, p)
      passages.push(p)
    }
    p.items.push(it)
  }
  // Under each heading, in reading order.
  const parts = []
  for (const p of passages) {
    const label = p.seg ? p.heading || (blocks.length ? 'Article' : null) : 'Without a citation'
    if (!parts.length || parts.at(-1).heading !== label) parts.push({ heading: label, passages: [] })
    parts.at(-1).passages.push(p)
  }
  return parts
}

// Resources by type, in the order a chart reads: problems, findings, treatment, plans, the rest.
const TYPE_ORDER = ['Condition', 'Observation', 'MedicationStatement', 'MedicationRequest', 'MedicationAdministration', 'Procedure', 'ServiceRequest',
  'CarePlan', 'AllergyIntolerance', 'FamilyMemberHistory', 'Immunization', 'Encounter', 'DiagnosticReport']
export function byType(bundle) {
  const groups = new Map()
  for (const e of bundle?.entry || []) {
    const r = e.resource
    if (!r) continue
    if (!groups.has(r.resourceType)) groups.set(r.resourceType, [])
    groups.get(r.resourceType).push(r)
  }
  const rank = (t) => (INTERNAL_TYPES.has(t) ? 100 + [...INTERNAL_TYPES].indexOf(t) : TYPE_ORDER.includes(t) ? TYPE_ORDER.indexOf(t) : 50)
  return [...groups.entries()].sort((a, b) => rank(a[0]) - rank(b[0])).map(([type, items]) => ({ type, items, internal: INTERNAL_TYPES.has(type) }))
}

export function reference(r) {
  return r.subject?.reference || r.patient?.reference || null
}
