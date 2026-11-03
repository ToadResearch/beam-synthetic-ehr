// Find in article: the query, how many matches the reader drew, and which one is current.
export const find = $state({ query: '', count: 0, current: 0 })

// Every case-insensitive occurrence of the query in a text, as [start, end] ranges.
export function findAll(text, query) {
  const q = query.trim().toLowerCase()
  if (q.length < 2 || !text) return []
  const low = text.toLowerCase()
  const out = []
  for (let at = low.indexOf(q); at >= 0; at = low.indexOf(q, at + q.length)) out.push([at, at + q.length])
  return out
}

export const hits = (text, query) => (query.trim().length >= 2 && text?.toLowerCase().includes(query.trim().toLowerCase()))
