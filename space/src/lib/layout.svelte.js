// The left panel (article or patient list) and how the reading area is split. Only the split is remembered:
// each visit to Articles or Records starts with the panel open, except on a phone, where it is a drawer.
const KEY = 'layout'

function saved() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {}
  } catch {
    return {}
  }
}

const start = saved()
export const layout = $state({ library: true, split: start.split ?? 55, record: null })

export function remember() {
  try { localStorage.setItem(KEY, JSON.stringify({ split: layout.split })) } catch {}
}

export function openPanel() {
  layout.library = innerWidth > 900
}
