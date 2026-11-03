// Hash routes: #/, #/articles/<id>?p=<patient>, #/records/<bundle>, #/cohort, #/how/<step>
function parse() {
  const [path, query = ''] = location.hash.replace(/^#\/?/, '').split('?')
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent)
  return { view: parts[0] || 'home', id: parts[1] || null, params: Object.fromEntries(new URLSearchParams(query)) }
}

export const route = $state(parse())

window.addEventListener('hashchange', () => Object.assign(route, parse()))

export function href(view, id, params = {}) {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== '')).toString()
  return `#/${view}${id ? `/${encodeURIComponent(id)}` : ''}${query ? `?${query}` : ''}`
}

export function go(view, id, params, { replace = false } = {}) {
  const next = href(view, id, params)
  if (replace) history.replaceState(null, '', next)
  else location.hash = next
  Object.assign(route, parse())
}
