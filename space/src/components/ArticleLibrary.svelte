<script>
  // The article list on the desk: search, and filters built from what the model extracted (the patients' age and
  // documented sex, the kinds of facts it found). Opened files come first.
  import { tick } from 'svelte'
  import { href } from '../lib/router.svelte.js'
  import { uploads } from '../lib/uploads.svelte.js'
  import { plural } from '../lib/sections.js'
  import { ageOptions, sexOptions, themeOptions } from '../lib/filters.js'
  import Dropdown from './Dropdown.svelte'

  let { index, current, onpick } = $props()

  let query = $state('')
  let age = $state('')
  let sex = $state('')
  let theme = $state('')

  const count = (pick) => index.articles.filter(pick).length
  const ages = $derived(ageOptions((g) => count((a) => a.ages?.includes(g))))
  const sexes = $derived(sexOptions((x) => count((a) => a.sexes?.includes(x))))
  const themes = $derived(themeOptions((t) => count((a) => a.themes?.includes(t))))

  // Each word typed must appear in the title, the PMC ID, the citation or a patient's label, in any order.
  const words = $derived(query.toLowerCase().split(/[\s,;]+/).filter(Boolean))
  const shown = $derived(index.articles.filter((a) => (!age || a.ages?.includes(age)) && (!sex || a.sexes?.includes(sex)) && (!theme || a.themes?.includes(theme)) &&
    words.every((w) => `${a.id} ${a.title} ${a.citation || ''} ${a.patients.map((p) => p.label).join(' ')}`.toLowerCase().includes(w))))
  const filtered = $derived(!!(query.trim() || age || sex || theme))

  // The open article's row stays in sight. The list scrolls itself, never the page.
  let list = $state()
  $effect(() => {
    void current
    tick().then(() => {
      const row = list?.querySelector('.row.active')
      if (!row) return
      const r = row.getBoundingClientRect(), l = list.getBoundingClientRect()
      if (r.top < l.top || r.bottom > l.bottom) list.scrollTop += r.top - l.top - (l.height - r.height) / 2
    })
  })
</script>

<div class="library">
  <div class="controls">
    <input class="search" type="search" placeholder="Search titles or PMC IDs" bind:value={query} aria-label="Search articles by title, PMC ID or patient" />
    <div class="filters">
      {#if ages.length > 1}<Dropdown bind:value={age} options={ages} label="Any age" />{/if}
      {#if sexes.length > 1}<Dropdown bind:value={sex} options={sexes} label="Any sex" />{/if}
      {#if themes.length > 1}<div class="wide"><Dropdown bind:value={theme} options={themes} label="Any theme" /></div>{/if}
    </div>
    <p class="counts">
      <span>{filtered ? `${shown.length} of ${index.articles.length}` : index.articles.length} articles · {plural(shown.reduce((n, a) => n + a.patients.length, 0), 'patient')}</span>
      {#if filtered}<button class="clear" onclick={() => { query = ''; age = ''; sex = ''; theme = '' }}>Clear</button>{/if}
    </p>
  </div>
  <nav class="list" aria-label="Articles" bind:this={list}>
    {#each uploads.articles as u (u.key)}
      <a class="row" class:active={u.key === current} href={href('articles', u.key)} onclick={onpick}>
        <span class="title">{u.article.title || u.article.id}</span>
        <span class="meta">Opened file · {plural(u.patients.length, 'patient')}</span>
      </a>
    {/each}
    {#each shown as a (a.id)}
      <a class="row" class:active={a.id === current} href={href('articles', a.id)} onclick={onpick}>
        <span class="title">{a.title}</span>
        <span class="meta">{plural(a.patients.length, 'patient')}{a.patients.length === 1 && a.patients[0].label ? ` · ${a.patients[0].label}` : ''}</span>
      </a>
    {:else}
      <p class="none">No article matches.</p>
    {/each}
  </nav>
  <p class="note">Extracted by Reflection Beam, not clinically reviewed.</p>
</div>

<style>
  .library { height: 100%; display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; }
  .controls { display: grid; gap: 8px; padding: 2px 4px 10px; }
  .filters { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .wide { grid-column: 1 / -1; }
  .counts { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin: 2px 2px 0; font-size: 12.5px; color: var(--ink-3); }
  .clear { padding: 2px 6px; border-radius: 6px; font-size: 12.5px; font-weight: 500; color: var(--ink-2); }
  .clear:hover { background: var(--desk-hover); color: var(--ink); }
  .list { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; padding: 6px 6px 16px; }
  .row { display: block; padding: 10px 12px; margin-bottom: 2px; border-radius: 10px; text-decoration: none; transition: background-color 150ms var(--ease), box-shadow 200ms var(--ease); }
  .row:hover { background: var(--desk-hover); }
  .row.active { background: var(--card); box-shadow: var(--shadow-card); }
  .title { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; font-size: 13.5px; line-height: 1.42; color: var(--ink-2); }
  .row.active .title { color: var(--ink); font-weight: 550; }
  .meta { display: block; margin-top: 3px; font-size: 12px; color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .none { margin: 8px 12px; font-size: 13px; color: var(--ink-3); }
  .note { margin: 0; padding: 10px 16px 14px; font-size: 11.5px; line-height: 1.5; color: var(--ink-3); }
</style>
