// Turning files a visitor opens into the shapes the views draw. Mirrors scripts/build_data.py,
// minus what only the run folder has (the model's stated reasons and reasoning).
import { SECTION_LABELS } from './sections.js'

const HIDDEN = new Set(['subject', 'evidence', 'time', 'name', 'attribute', 'assertion', 'temporality', 'numeric_value', 'unit',
  'comparator', 'text_value', 'dose_value', 'dose_unit', 'dose_text'])
const number = (v) => {
  if (v == null) return null
  const n = Number(v)
  return Number.isInteger(n) && Math.abs(n) >= 1000 ? n.toLocaleString('en-US') : String(+n.toPrecision(6))
}
const asObject = (v) => (typeof v === 'string' ? JSON.parse(v) : v)

// Article tables. Each table_row segment repeats its table: [label, caption, *header lines, group heading, row],
// one per line, empty parts left out. The row is the last line. Body cells carry ' [rowspan=r,colspan=c]' markers;
// header lines carry none, so their spans are inferred. Cell IDs follow the pipeline (table_grid): '<segment>-c<j>'
// is cell j of the segment's last '|' line and '<segment>-h<j>' cell j of the '|' line before it; `map` says which
// drawn row each is.
const SPAN = /\s*\[rowspan=(\d+),colspan=(\d+)\]$/
const LABEL = /^(supplementary\s+)?(table|tab\.?)\b/i
const splitRow = (line) => line.split('|').map((c) => c.trim())

function tableCell(text) {
  const m = SPAN.exec(text)
  if (!m) return { t: text }
  const cell = { t: text.slice(0, m.index).trimEnd() }
  if (+m[1] > 1) cell.rs = +m[1]
  if (+m[2] > 1) cell.cs = +m[2]
  return cell
}

// Columns the body fills, placing each row's cells around the rowspans from rows above.
function gridWidth(rows) {
  let width = 0
  let covered = new Map()
  for (const cells of rows) {
    const busy = new Set(covered.keys())
    covered = new Map([...covered].filter(([, n]) => n > 1).map(([c, n]) => [c, n - 1]))
    let col = 0
    for (const cell of cells) {
      while (busy.has(col)) col++
      if ((cell.rs || 1) > 1) for (let c = col; c < col + (cell.cs || 1); c++) covered.set(c, cell.rs - 1)
      col += cell.cs || 1
    }
    width = Math.max(width, col, Math.max(-1, ...busy) + 1)
  }
  return width
}

function leadNumber(text) {
  const m = /^\s*([−-]?\d+(?:\.\d+)?)/.exec(text)
  return m ? Number(m[1].replace('−', '-')) : null
}

// How k spanning header cells divide the n cells below them: evenly, or where a run of numbers restarts.
function groupSizes(k, children) {
  const n = children.length
  if (k <= 1 || n < k) return k === 1 ? [n] : null
  if (n % k === 0) return Array(k).fill(n / k)
  const values = children.map((c) => leadNumber(c.t))
  if (!values.includes(null)) {
    const drops = []
    for (let i = 0; i < n - 1; i++) if (values[i + 1] < values[i]) drops.push([values[i] - values[i + 1], i + 1])
    drops.sort((a, b) => b[0] - a[0] || b[1] - a[1])
    if (drops.length >= k - 1) {
      const cuts = drops.slice(0, k - 1).map((d) => d[1]).sort((a, b) => a - b)
      return [...cuts, n].map((b, i) => b - ([0, ...cuts][i]))
    }
  }
  return Array.from({ length: k }, (_, i) => Math.floor(n / k) + (i < n % k ? 1 : 0))
}

// Header lines as cells with inferred spans: the top line's first cells reach down to the body, the rest group
// the cells of the line below; a single short line copies the first row's colspans or widens its stub.
function headerRows(lines, width, firstBody) {
  const rows = lines.map((line) => splitRow(line).map(tableCell))
  if (!rows.length || rows.some((r) => r.some((c) => 'rs' in c || 'cs' in c))) return rows
  const last = rows.at(-1)
  if (rows.length === 1) {
    if (width > last.length) {
      if (firstBody && firstBody.length === last.length) {
        last.forEach((c, i) => { if ((firstBody[i].cs || 1) > 1) c.cs = firstBody[i].cs })
      } else last[0].cs = width - last.length + 1
    }
    return rows
  }
  const stubs = width - last.length
  if (stubs < 0 || stubs >= rows[0].length) return rows
  for (const c of rows[0].slice(0, stubs)) c.rs = rows.length
  for (let upper = rows.length - 2; upper >= 0; upper--) {
    const parents = upper === 0 ? rows[upper].slice(stubs) : rows[upper]
    const children = rows[upper + 1]
    const sizes = groupSizes(parents.length, children)
    if (!sizes) break
    let at = 0
    parents.forEach((parent, i) => {
      const span = children.slice(at, at + sizes[i]).reduce((s, c) => s + (c.cs || 1), 0)
      if (span > 1) parent.cs = span
      at += sizes[i]
    })
  }
  return rows
}

// One table drawn as printed: header rows, body rows with their spans, group and mid-table header rows.
function tableBlock(tid, segments) {
  const sids = segments.map((s) => s.segment_id)
  const lines = segments.map((s) => s.text.split('\n'))
  const n = lines.length
  if (n === 1 && lines[0].length <= 2 && !lines[0].at(-1).includes('|') && (lines[0].length === 1 || LABEL.test(lines[0][0]))) {
    // Label and caption only: the table itself is an image or empty.
    return { type: 'table', id: tid, label: lines[0].length === 2 ? lines[0][0] : '', caption: lines[0].at(-1), head: [], rows: [], map: {}, notes: [] }
  }
  let common = lines[0].slice(0, -1)
  for (const ls of lines.slice(1)) {
    let k = 0
    while (k < Math.min(common.length, ls.length - 1) && common[k] === ls[k]) k++
    common = common.slice(0, k)
  }
  let at = 0
  let label = ''
  let caption = ''
  if (at < common.length && !common[at].includes('|') && LABEL.test(common[at])) label = common[at++]
  if (at < common.length && !common[at].includes('|')) caption = common[at++]
  let headLines = common.slice(at)
  const rowCells = lines.map((ls) => splitRow(ls.at(-1)).map(tableCell))
  const isGroup = rowCells.map((r) => r.length === 1 && (r[0].cs || 1) > 1)
  if (headLines.length && isGroup[0] && headLines.at(-1) === rowCells[0][0].t) headLines = headLines.slice(0, -1)
  const pipes = lines.map((ls) => ls.filter((l) => l.includes('|')))
  const firstIsHead = !headLines.length && n > 1 && pipes[0].length === 1 && pipes[1].length === 1 && lines[0].at(-1).includes('|')

  const rows = []
  const map = {}
  let group = null
  let subs = 0
  lines.forEach((ls, k) => {
    const sid = sids[k]
    const keys = Array(ls.length).fill(null)
    headLines.forEach((_, i) => { keys[at + i] = `h${i}` })
    if (isGroup[k]) group = rowCells[k][0].t
    const extra = []
    for (let pos = common.length; pos < ls.length - 1; pos++) extra.push(pos)
    if (extra.length && ls[extra.at(-1)] === group) extra.pop()
    extra.forEach((pos, i) => {
      keys[pos] = `s${i}`
      if (i >= subs) { // a header row first printed here, part way down the table
        rows.push({ key: `s${i}`, kind: 'sub', cells: headerRows([ls[pos]], 0, null)[0] })
        subs++
      }
    })
    if (k === 0 && firstIsHead) keys[keys.length - 1] = 'h0'
    else {
      keys[keys.length - 1] = sid
      rows.push({ id: sid, kind: isGroup[k] ? 'group' : 'row', cells: rowCells[k] })
    }
    const pipeAt = ls.flatMap((l, i) => (l.includes('|') ? [i] : []))
    let h = null
    let c = null
    if (pipeAt.length >= 2) [h, c] = [keys[pipeAt.at(-2)], keys[pipeAt.at(-1)]]
    else if (pipeAt.length === 1) {
      if (k === 0 && n > 1 && pipes[1].length === 1) h = keys[pipeAt[0]]
      else c = keys[pipeAt[0]]
    }
    if (h || c) map[sid] = [h, c]
  })

  const body = rows.filter((r) => r.kind !== 'sub').map((r) => r.cells)
  const firstBody = rows.find((r) => r.kind === 'row')?.cells || null
  const width = Math.max(gridWidth(body), ...headLines.slice(-1).map((l) => splitRow(l).length))
  const head = firstIsHead
    ? [{ key: 'h0', id: sids[0], cells: headerRows([lines[0].at(-1)], width, firstBody)[0] }]
    : headerRows(headLines, width, firstBody).map((cells, i) => ({ key: `h${i}`, cells }))
  return { type: 'table', id: tid, label, caption, head, rows, map, notes: [] }
}

// cell_id -> literal text for every article table cell, numbered as the pipeline numbers them.
export function pipelineCells(source) {
  const out = {}
  const tables = {}
  for (const seg of source.segments) {
    if (seg.kind === 'table_row') (tables[seg.table_id || seg.segment_id] ||= []).push(seg)
  }
  for (const segs of Object.values(tables)) {
    const pipes = segs.map((s) => s.text.split('\n').filter((l) => l.includes('|')))
    segs.forEach((seg, i) => {
      const lines = pipes[i]
      let header = null
      let row = null
      if (lines.length >= 2) [header, row] = lines.slice(-2)
      else if (lines.length === 1 && i === 0 && segs.length > 1 && pipes[1].length === 1) header = lines[0]
      else if (lines.length === 1) row = lines[0]
      if (header) splitRow(header).forEach((t, j) => { out[`${seg.segment_id}-h${j}`] = t })
      if (row) splitRow(row).forEach((t, j) => { out[`${seg.segment_id}-c${j}`] = t })
    })
  }
  return out
}

export function blocksFrom(source) {
  const figures = Object.fromEntries((source.figures || []).map((f) => [f.figure_id, f]))
  const captions = Object.fromEntries(source.segments.filter((s) => s.kind === 'figure_caption').map((s) => [s.figure_id, s.segment_id]))
  const blocks = []
  const tables = {}
  const placed = new Set()
  const rowsOf = {}
  for (const seg of source.segments) if (seg.kind === 'table_row') (rowsOf[seg.table_id || seg.segment_id] ||= []).push(seg)
  let heading
  const figure = (fid) => {
    const f = figures[fid]
    placed.add(fid)
    return { type: 'figure', id: fid, label: f.label || fid, caption: f.caption || '', captionId: captions[fid], images: (f.media || []).map((m) => m.url).filter(Boolean) }
  }
  for (const seg of source.segments) {
    const { kind, segment_id: sid } = seg
    if (kind === 'figure_caption') continue
    if (seg.heading !== heading) {
      heading = seg.heading
      if (heading) blocks.push({ type: 'heading', text: heading })
    }
    if (kind === 'table_row') {
      const tid = seg.table_id || sid
      if (!tables[tid]) {
        tables[tid] = tableBlock(tid, rowsOf[tid])
        blocks.push(tables[tid])
      }
      continue
    }
    if (kind === 'table_footnote' && tables[seg.table_id]) {
      tables[seg.table_id].notes.push({ id: sid, text: seg.text })
      continue
    }
    blocks.push({ type: 'p', id: sid, text: seg.text })
    for (const ref of seg.cross_references || []) {
      if (ref.ref_type !== 'fig') continue
      for (const fid of ref.target_ids || []) if (figures[fid] && !placed.has(fid)) blocks.push(figure(fid))
    }
  }
  const rest = Object.keys(figures).filter((fid) => !placed.has(fid))
  if (rest.length) blocks.push({ type: 'heading', text: 'Figures' }, ...rest.map(figure))
  return blocks
}

function headline(section, item) {
  if (item.numeric_value != null) {
    const comparator = ['=', 'unknown', null, undefined].includes(item.comparator) ? '' : item.comparator
    return [`${comparator}${number(item.numeric_value)}`, item.unit].filter(Boolean).join(' ')
  }
  if (section === 'medications') {
    const dose = item.dose_text || [number(item.dose_value), item.dose_unit].filter(Boolean).join(' ')
    return [dose, item.route, item.frequency].filter(Boolean).join(', ') || null
  }
  return item.text_value || null
}

function factsFrom(patient) {
  const out = []
  for (const [section, label] of Object.entries(SECTION_LABELS)) {
    const items = patient.sections?.[section]?.items || []
    if (!items.length) continue
    out.push({
      key: section, label,
      items: items.map((item, n) => ({
        id: `${section}-${n}`,
        name: item.name || (item.attribute || '').replace(/_/g, ' ') || label,
        value: headline(section, item), assertion: item.assertion, temporality: item.temporality, time: item.time?.text || null,
        fields: Object.fromEntries(Object.entries(item).filter(([k, v]) => !HIDDEN.has(k) && v != null && v !== '' && v !== 'unknown' && typeof v !== 'object')),
        evidence: (item.evidence || []).filter((e) => e.source_section && e.quote).map((e) => ({ seg: e.source_section, quote: e.quote })),
      })),
    })
  }
  return out
}

const CELL_NUMBER = /^(<=|>=|[<>≤≥])?\s*([+\-−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[+\-−]?\.\d+)(?:\s*[×x*]\s*10\s*\^\s*\(?([+\-−]?\d{1,2})\)?)?\s*(.*)$/
const NOTE_MARK = /\s*(?:\^\([^)]{1,8}\)|\^[A-Za-z*†‡§¶#]|[*†‡§¶#])$/

// [value, unit] of a cell holding one number ('8,400 IU/ml', '<0.5', '1.3 kE/L', '1.0 × 10^(9)/L'); nulls for
// ranges, pairs and words. Used where the pipeline left a cell unparsed (units outside its list).
function cellNumber(text) {
  const m = CELL_NUMBER.exec((text || '').replace(SPAN, '').trim())
  if (!m) return [null, null]
  let rest = m[4]
  while (NOTE_MARK.test(rest)) rest = rest.replace(NOTE_MARK, '')
  if (/^(?:[–—\-/,]|to\b)\s*\d/.test(rest) || rest.includes(';')) return [null, null]
  const value = Number(m[2].replace(/,/g, '').replace('−', '-')) * 10 ** Number((m[3] || '0').replace('−', '-'))
  return [value, rest.trim() || null]
}

// Measurement series; a point the pipeline did not parse takes its number from the literal cell.
function seriesFrom(patient, cells = {}) {
  return (patient.measurement_series || []).map((s) => ({
    id: s.series_id, name: s.measurement_name, kind: s.measurement_kind, nameCell: s.name_cell_id,
    points: (s.points || []).map((p) => {
      const magnitude = p.parsed?.magnitude
      let value = magnitude == null || magnitude === '' ? NaN : Number(magnitude)
      let unit = p.parsed?.unit ?? null
      if (!Number.isFinite(value)) [value, unit] = cellNumber(cells[p.value_cell_id])
      const raw = p.parsed?.raw_text || (cells[p.value_cell_id] || '').replace(SPAN, '') || null
      return { label: p.time?.time_text, value, raw, unit, cell: p.value_cell_id, timeCell: p.time?.time_cell_id }
    }),
  }))
}

function timelineFrom(patient) {
  const t = patient.relative_timeline || patient.timeline || {}
  const events = Object.fromEntries((t.events || []).map((e) => [e.event_id, e]))
  const order = [...(t.ordered_event_ids || []).filter((i) => events[i]), ...Object.keys(events).filter((i) => !(t.ordered_event_ids || []).includes(i))]
  return order.map((i) => ({
    id: i, kind: events[i].kind, text: events[i].description,
    evidence: (events[i].evidence || []).filter((e) => e.segment_id && e.quote).map((e) => ({ seg: e.segment_id, quote: e.quote })),
  }))
}

const CONTEXT = ['case_kind', 'index_subject_description', 'species', 'multiple_index_patients', 'subject_state', 'care_setting', 'chief_complaint']

// The case-context section is a set of fields, not a list of facts.
function caseContextFrom(patient) {
  const cc = patient.sections?.case_context || {}
  const fields = Object.fromEntries(CONTEXT.filter((k) => ![null, undefined, '', 'unknown'].includes(cc[k]) && !(Array.isArray(cc[k]) && !cc[k].length)).map((k) => [k, cc[k]]))
  if (!Object.keys(fields).length) return null
  return {
    fields, limitations: cc.limitations || [],
    evidence: (cc.evidence || []).filter((e) => e.source_section && e.quote).map((e) => ({ seg: e.source_section, quote: e.quote })),
  }
}

export function articleFrom(record, source, meta = {}) {
  const cells = source ? pipelineCells(source) : {}
  for (const c of record.measurement_series?.cells || []) if (!(c.cell_id in cells)) cells[c.cell_id] = c.raw_text
  return {
    article: {
      id: record.article_id, title: meta.title || record.title, doi: meta.doi || record.doi,
      url: meta.source_url || record.article_url, citation: source?.metadata?.citation || null,
      license: meta.license || [record.license?.code, record.license?.version].filter(Boolean).join(' ') || null,
      licenseUrl: meta.license_url || null, type: source?.article_type || null, pmcid: record.pmcid || source?.pmcid || null,
    },
    blocks: source ? blocksFrom(source) : [],
    patients: (record.patients || []).map((p) => ({
      id: p.patient_id, label: p.label,
      summary: (p.summary?.claims || []).map((c) => ({ text: c.text, evidence: (c.evidence || []).map((e) => ({ seg: e.segment_id, quote: e.quote })) })),
      sections: factsFrom(p), series: seriesFrom(p, cells), timeline: timelineFrom(p), caseContext: caseContextFrom(p),
    })),
    uploaded: true,
  }
}

function objectsOf(text) {
  const t = text.trim()
  if (!t) return []
  try {
    const v = JSON.parse(t)
    return Array.isArray(v) ? v : [v]
  } catch {
    return t.split('\n').filter((l) => l.trim()).map((l, i) => {
      try { return JSON.parse(l) } catch { throw new Error(`Line ${i + 1} is not JSON`) }
    })
  }
}

// files: [{ name, text }] → { articles: [...], records: [...] } ready for the views.
export function parseFiles(files) {
  const records = []
  const extractions = []
  const sources = {}
  for (const file of files) {
    const loose = []
    for (const obj of objectsOf(file.text)) {
      if (!obj || typeof obj !== 'object') continue
      if (obj.resourceType === 'Bundle') records.push({ bundle: obj, meta: { name: file.name } })
      else if (obj.resourceType) loose.push(obj)
      else if (obj.bundle && (obj.patient_id || obj.bundle_id)) {
        records.push({
          bundle: asObject(obj.bundle),
          meta: { name: file.name, article: { id: obj.article_id, title: obj.title, url: obj.source_url, license: obj.license, licenseUrl: obj.license_url }, patient: obj.patient },
        })
      } else if (obj.record && obj.article_id) extractions.push({ record: asObject(obj.record), meta: obj })
      else if (Array.isArray(obj.patients) && obj.patients.some((p) => p.sections)) extractions.push({ record: obj, meta: {} })
      else if (Array.isArray(obj.segments) && obj.article_id) sources[obj.article_id] = obj
    }
    if (loose.length) records.push({ bundle: { resourceType: 'Bundle', type: 'collection', entry: loose.map((resource) => ({ resource })) }, meta: { name: file.name } })
  }
  const articles = extractions.map(({ record, meta }) => articleFrom(record, sources[record.article_id], meta))
  if (!articles.length && !records.length && Object.keys(sources).length) {
    throw new Error('That is a source packet. Open it together with its extraction record.')
  }
  return { articles, records }
}
