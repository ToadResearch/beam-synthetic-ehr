// Locating quoted evidence inside segment text, tolerant of whitespace differences.

export function findRange(text, quote) {
  if (!text || !quote) return null
  const at = text.indexOf(quote)
  if (at >= 0) return [at, at + quote.length]
  const map = []
  let compact = ''
  for (let i = 0; i < text.length; i++) {
    if (!/\s/.test(text[i])) { map.push(i); compact += text[i] }
  }
  const needle = quote.replace(/\s+/g, '')
  const hit = needle ? compact.indexOf(needle) : -1
  return hit < 0 ? null : [map[hit], map[hit + needle.length - 1] + 1]
}

// Split text into plain and marked runs. marks: [{ quote, kind }] where kind is 'pin' or 'hover', or
// [{ ranges: [[start, end]], kind }] for matches already located (find in article).
export function runs(text, marks) {
  const ranges = []
  for (const m of marks) {
    if (m.ranges) {
      for (const [start, end] of m.ranges) ranges.push({ start, end, color: 'var(--find)', kind: m.kind })
      continue
    }
    const r = findRange(text, m.quote)
    if (r) ranges.push({ start: r[0], end: r[1], color: m.color || 'var(--hl-edge)', kind: m.kind })
  }
  if (!ranges.length) return [{ text }]
  ranges.sort((a, b) => a.start - b.start || (a.kind === 'pin' ? -1 : 1))
  const out = []
  let at = 0
  for (const r of ranges) {
    const start = Math.max(r.start, at)
    if (start >= r.end) continue
    if (start > at) out.push({ text: text.slice(at, start) })
    out.push({ text: text.slice(start, r.end), color: r.color, kind: r.kind })
    at = r.end
  }
  if (at < text.length) out.push({ text: text.slice(at) })
  return out
}

// Whether a table cell is named by a quote: the quote contains the cell, or the cell contains the quote.
export function cellQuoted(cell, quote) {
  if (!cell || !quote) return false
  const c = cell.replace(/\s+/g, ' ').trim()
  const q = quote.replace(/\s+/g, ' ').trim()
  if (c.length < 2) return false
  return q === c || (q.includes('|') ? q.split('|').some((part) => part.trim() === c) : q.includes(c) && c.length > 3) || c.includes(q)
}
