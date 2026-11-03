<script>
  import { tick } from 'svelte'
  import { route } from '../lib/router.svelte.js'
  import { theme, toggleTheme } from '../lib/theme.svelte.js'
  import { layout } from '../lib/layout.svelte.js'

  let nav = $state()
  const paneled = $derived(route.view === 'articles' || route.view === 'records')
  const panelName = $derived(route.view === 'records' ? 'patient list' : 'article list')
  // One underline for the whole nav, moved under the current view.
  let ink = $state({ x: 0, w: 0, ready: false })

  function measure() {
    const on = nav?.querySelector('a.on')
    if (!on) { ink = { ...ink, w: 0, ready: false }; return }
    // From nothing (the start page) the line appears in place; from another view it slides.
    const appear = ink.w === 0
    ink = { x: on.offsetLeft, w: on.offsetWidth, ready: !appear }
    if (appear) setTimeout(() => (ink = { ...ink, ready: true }), 60)
  }
  $effect(() => {
    void route.view
    tick().then(measure)
  })
  // Fonts arriving or the window changing width move the links: keep the line under its word.
  $effect(() => {
    if (!nav) return
    const watch = new ResizeObserver(measure)
    watch.observe(nav)
    document.fonts?.ready.then(measure)
    return () => watch.disconnect()
  })

  function flip(e) {
    const box = e.currentTarget.getBoundingClientRect()
    toggleTheme(box.left + box.width / 2, box.top + box.height / 2)
  }
</script>

<header class="bar">
  <!-- The panel toggle keeps its place on every view, so the header never shifts; it shows where there is a panel. -->
  <button class="menu" class:away={!paneled} onclick={() => (layout.library = !layout.library)}
    aria-expanded={layout.library} aria-hidden={!paneled} tabindex={paneled ? 0 : -1}
    aria-label={`${layout.library ? 'Hide' : 'Show'} the ${panelName}`} title={`${layout.library ? 'Hide' : 'Show'} the ${panelName}`}>
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M2.5 4h11M2.5 8h11M2.5 12h11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg>
  </button>
  <a class="brand" href="#/" aria-label="Synthetic EHR, start">
    <svg viewBox="0 0 18 18" width="18" height="18" aria-hidden="true">
      <rect x="2.5" y="1.5" width="13" height="15" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.4" />
      <path d="M5.5 5.5h7M5.5 12.5h4.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
      <path d="M5 9h8" stroke="var(--hl-edge)" stroke-width="3" stroke-linecap="round" />
    </svg>
    <span>Synthetic EHR</span>
  </a>

  <nav aria-label="Views" bind:this={nav}>
    <a href="#/articles" class:on={route.view === 'articles'}>Articles</a>
    <a href="#/records" class:on={route.view === 'records' || route.view === 'cohort'}>Records</a>
    <a href="#/how/1" class:on={route.view === 'how'}>How it works</a>
    <span class="ink" class:ready={ink.ready} style="width: {ink.w}px; transform: translateX({ink.x}px); opacity: {ink.w ? 1 : 0}" aria-hidden="true"></span>
  </nav>

  <div class="end">
    <button class="theme" class:dark={theme.mode === 'dark'} onclick={flip}
      aria-label={theme.mode === 'dark' ? 'Switch to the light theme' : 'Switch to the dark theme'} title={theme.mode === 'dark' ? 'Light theme' : 'Dark theme'}>
      <svg class="sun" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><circle cx="8" cy="8" r="2.9" fill="none" stroke="currentColor" stroke-width="1.35" /><path d="M8 1.6v1.5M8 12.9v1.5M1.6 8h1.5M12.9 8h1.5M3.47 3.47l1.06 1.06M11.47 11.47l1.06 1.06M3.47 12.53l1.06-1.06M11.47 4.53l1.06-1.06" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" /></svg>
      <svg class="moon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M13.2 9.7A5.6 5.6 0 0 1 6.3 2.8a5.6 5.6 0 1 0 6.9 6.9z" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linejoin="round" /></svg>
    </button>
  </div>
</header>

<style>
  .bar {
    height: var(--bar); flex: none;
    display: flex; align-items: center; gap: 40px;
    padding: 0 20px;
    background: var(--paper);
    position: relative; z-index: 20;
  }
  .menu { width: 34px; height: 34px; margin-right: -26px; display: grid; place-items: center; border-radius: 10px; color: var(--ink-2); transition: background-color 150ms var(--ease), color 150ms var(--ease), transform 150ms var(--spring), opacity 220ms var(--ease); }
  .menu.away { opacity: 0; pointer-events: none; }
  .menu:hover { background: var(--desk-hover); color: var(--ink); }
  .menu:active { transform: scale(0.92); }
  .brand { display: flex; align-items: center; gap: 10px; text-decoration: none; font-weight: 600; font-size: 15px; letter-spacing: -0.005em; }
  nav { position: relative; display: flex; gap: 26px; height: 100%; }
  nav a {
    display: flex; align-items: center; height: 100%;
    text-decoration: none; color: var(--ink-3); font-size: 14.5px;
    transition: color 160ms var(--ease);
  }
  nav a:hover, nav a.on { color: var(--ink); }
  .ink { position: absolute; left: 0; top: calc(50% + 11px); height: 1.5px; border-radius: 1px; background: var(--ink); pointer-events: none; }
  .ink.ready { transition: transform 380ms var(--ease), width 380ms var(--ease), opacity 200ms var(--ease); }
  .end { margin-left: auto; display: flex; align-items: center; gap: 18px; }
  .theme { position: relative; width: 32px; height: 32px; display: grid; place-items: center; color: var(--ink-2); transition: color 160ms var(--ease); }
  .theme:hover { color: var(--ink); }
  .theme svg { grid-area: 1 / 1; transition: transform 520ms var(--ease), opacity 320ms var(--ease); }
  /* The icon names the theme a click switches to: the moon in light, the sun in dark. */
  .theme .sun { opacity: 0; transform: rotate(-90deg) scale(0.4); }
  .theme.dark .sun { opacity: 1; transform: none; }
  .theme.dark .moon { opacity: 0; transform: rotate(90deg) scale(0.4); }
  @media (max-width: 760px) {
    .bar { gap: 18px; padding: 0 12px; }
    nav { gap: 16px; }
    nav a { font-size: 14px; }
    .brand span { display: none; }
    .menu { margin-right: -10px; }
    .end { gap: 8px; }
  }
  @media (max-width: 430px) {
    nav a[href^='#/how'] { display: none; }
  }
</style>
