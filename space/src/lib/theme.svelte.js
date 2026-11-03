// Light or dark. Until the visitor picks one the system decides; a pick is remembered in this browser.
import { tick } from 'svelte'

const KEY = 'theme'
const query = matchMedia('(prefers-color-scheme: dark)')

function saved() {
  try {
    const t = localStorage.getItem(KEY)
    return t === 'light' || t === 'dark' ? t : null
  } catch {
    return null
  }
}

export const theme = $state({ mode: saved() || (query.matches ? 'dark' : 'light') })

query.addEventListener('change', (e) => { if (!saved()) theme.mode = e.matches ? 'dark' : 'light' })

function apply(mode) {
  theme.mode = mode
  document.documentElement.dataset.theme = mode
  try { localStorage.setItem(KEY, mode) } catch {}
}

// Switch themes; the new one spreads out in a circle from (x, y), the point that was clicked.
export function toggleTheme(x, y) {
  const next = theme.mode === 'dark' ? 'light' : 'dark'
  if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) return apply(next)
  const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))
  const transition = document.startViewTransition(async () => { apply(next); await tick() })
  transition.ready.then(() => {
    document.documentElement.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
      { duration: 620, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', pseudoElement: '::view-transition-new(root)' },
    )
  })
}
