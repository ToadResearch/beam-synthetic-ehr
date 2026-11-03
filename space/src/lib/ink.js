// One underline for a row of tabs, under the tab marked aria-selected. It appears in place, then slides between tabs,
// like the one under the top navigation. The row must be positioned (relative, sticky or absolute).
export function ink(node) {
  const line = document.createElement('span')
  line.className = 'tab-ink'
  line.setAttribute('aria-hidden', 'true')
  node.append(line)
  let timer
  function place() {
    const on = node.querySelector('[aria-selected="true"]')
    if (!on) { line.style.opacity = '0'; return }
    const first = !line.style.width
    line.style.width = `${on.offsetWidth}px`
    line.style.transform = `translateX(${on.offsetLeft}px)`
    line.style.opacity = '1'
    if (first) timer = setTimeout(() => line.classList.add('ready'), 60)
  }
  const resize = new ResizeObserver(place)
  resize.observe(node)
  const watch = new MutationObserver(place)
  watch.observe(node, { subtree: true, attributes: true, attributeFilter: ['aria-selected'] })
  document.fonts?.ready.then(place)
  place()
  return { destroy() { clearTimeout(timer); resize.disconnect(); watch.disconnect(); line.remove() } }
}
