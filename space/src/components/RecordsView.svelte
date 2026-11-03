<script>
  import { tick } from 'svelte'
  import { fade, fly } from 'svelte/transition'
  import { route, href } from '../lib/router.svelte.js'
  import { loadIndex, loadRecord, loadArticle } from '../lib/data.js'
  import { uploads } from '../lib/uploads.svelte.js'
  import Record from './Record.svelte'
  import { layout, openPanel } from '../lib/layout.svelte.js'

  let index = $state(null)
  let record = $state(null)
  let blocks = $state([])
  let error = $state(null)
  let query = $state('')
  openPanel()
  let main = $state()

  loadIndex().then((i) => (index = i)).catch((e) => (error = e.message))

  const key = $derived(route.id || index?.articles.find((a) => a.id === index.featured)?.patients[0]?.bundle || null)

  // The open patient's row stays in sight. The list scrolls itself, never the page.
  let list = $state()
  $effect(() => {
    layout.record = key
    void index
    tick().then(() => {
      const row = list?.querySelector('.pt.on')
      if (!row) return
      const r = row.getBoundingClientRect(), l = list.getBoundingClientRect()
      if (r.top < l.top || r.bottom > l.bottom) list.scrollTop += r.top - l.top - (l.height - r.height) / 2
    })
  })

  function fetchRecord(k) {
    if (!k.startsWith('upload-')) return loadRecord(k)
    const u = uploads.records.find((r) => r.key === k)
    if (!u) return Promise.reject(new Error('That opened file is no longer in this tab. Open it again.'))
    // A row of this dataset names its article; the Patient resource says which of the article's patients it is.
    const listed = index?.articles.find((a) => a.id === u.meta.article?.id)
    const pid = (u.bundle.entry || []).map((e) => e.resource).find((r) => r?.resourceType === 'Patient')
      ?.extension?.find((x) => x.url.endsWith('/source-patient-id'))?.valueString
    const known = listed?.patients.find((p) => p.id === pid)
    return Promise.resolve({
      article: u.meta.article || null, patient: known ? { id: known.id, label: known.label } : u.meta.patient || null,
      bundle: u.bundle, uploaded: true, linkable: !!listed, name: u.meta.name,
    })
  }

  $effect(() => {
    const k = key
    if (!k) return
    record = null
    error = null
    if (innerWidth <= 900) layout.library = false
    fetchRecord(k).then(async (r) => {
      // The article's text gives the record its section headings; a record without it still reads by type.
      const known = r.article?.id && index?.articles.some((a) => a.id === r.article.id)
      const a = known ? await loadArticle(r.article.id).catch(() => null) : null
      if (k === key) { blocks = a?.blocks || []; record = r; main?.scrollTo({ top: 0 }) }
    }).catch((e) => { if (k === key) error = e.message })
  })

  // The search reads the patient, the article and its PMC ID, and the patient's conditions with the ICD-10-CM codes the model chose.
  function keeps(a, p) {
    const text = query.trim().replace(/[\s,;]+$/, '').toLowerCase()
    return !text || `${p.label} ${a.title} ${a.id}`.toLowerCase().includes(text) ||
      p.conditions?.some((c) => c.name?.toLowerCase().includes(text) || c.code?.toLowerCase().startsWith(text))
  }
  const groups = $derived.by(() => {
    if (!index) return []
    return index.articles.map((a) => ({ ...a, patients: a.patients.filter((p) => keeps(a, p)) })).filter((a) => a.patients.length)
  })
  const current = $derived(index?.articles.flatMap((a) => a.patients).find((p) => p.bundle === key) || null)
</script>

<div class="layout" class:closed={!layout.library}>
  <nav class="list" class:open={layout.library} aria-label="Patients">
    <div class="top">
      <input class="search" type="search" placeholder="Patients, conditions or codes" bind:value={query} aria-label="Search patients, conditions and ICD-10-CM codes" />
      <a class="build" href="#/cohort">
        <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M2.5 4h11M4.5 8h7M6.5 12h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg>
        <span>Build a cohort</span>
        <span class="go" aria-hidden="true">→</span>
      </a>
    </div>
    <div class="scroll" bind:this={list}>
      {#if uploads.records.length}
        <div class="group">
          <p class="g-title label">Opened files</p>
          {#each uploads.records as u (u.key)}
            <a class="pt" class:on={u.key === key} href={href('records', u.key)}>
              <span class="pl">{u.meta.patient?.label || u.meta.name}</span>
              <span class="pm">{u.bundle.entry?.length ?? 0} resources</span>
            </a>
          {/each}
        </div>
      {/if}
      {#each groups as a (a.id)}
        <div class="group">
          <p class="g-title">{a.title}</p>
          {#each a.patients as p (p.bundle)}
            <a class="pt" class:on={p.bundle === key} href={href('records', p.bundle)}>
              <span class="pl">{p.label}</span>
              <span class="pm">{[p.age, p.sex].filter(Boolean).join(' · ')}{p.age || p.sex ? ' · ' : ''}{p.resources} resources{p.passed ? ' · valid' : ''}</span>
            </a>
          {/each}
        </div>
      {:else}
        <p class="none">No patient matches.</p>
      {/each}
    </div>
  </nav>

  <section class="main" bind:this={main}>
    <button class="switch" onclick={() => (layout.library = !layout.library)} aria-expanded={layout.library}>
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M2.5 4h11M2.5 8h11M2.5 12h7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" /></svg>
      <span>{current ? `Patient ${index.articles.flatMap((a) => a.patients).indexOf(current) + 1} of ${index.totals.patients}` : 'Patients'}</span>
    </button>
    {#if error}
      <p class="state">{error}</p>
    {:else if record}
      {#key key}<div in:fade={{ duration: 220 }}><Record {record} {blocks} /></div>{/key}
    {:else}
      <div class="loading" aria-label="Loading"><span></span><span></span><span></span></div>
    {/if}
  </section>
  {#if layout.library}<div class="scrim" transition:fade={{ duration: 160 }} onclick={() => (layout.library = false)} role="presentation"></div>{/if}
</div>

<style>
  .layout { position: relative; height: 100%; overflow: hidden; display: grid; grid-template-columns: 300px minmax(0, 1fr); transition: grid-template-columns 260ms var(--ease); }
  .layout.closed { grid-template-columns: 0 minmax(0, 1fr); }
  .list { min-width: 0; overflow: hidden; display: flex; flex-direction: column; min-height: 0; padding: 10px 2px 0 8px; background: var(--paper); transition: opacity 200ms var(--ease); }
  .closed .list { visibility: hidden; opacity: 0; }
  .top { display: grid; gap: 8px; padding: 2px 8px 10px; }
  .build {
    display: flex; align-items: center; gap: 9px; padding: 7px 10px; border: 1px solid var(--rule); border-radius: 10px;
    background: var(--card); font-size: 13.5px; font-weight: 500; color: var(--ink-2); text-decoration: none;
    transition: border-color 150ms var(--ease), color 150ms var(--ease);
  }
  .build:hover { border-color: var(--rule-strong); color: var(--ink); }
  .build .go { margin-left: auto; color: var(--ink-3); transition: transform 220ms var(--ease); }
  .build:hover .go { transform: translateX(3px); }
  .none { margin: 14px 10px; font-size: 13px; color: var(--ink-3); }
  .scroll { flex: 1; min-height: 0; overflow-y: auto; padding: 0 10px 60px; }
  .group { padding: 14px 0 6px; border-top: 1px solid var(--rule); }
  .group:first-child { border-top: 0; }
  .g-title { margin: 0 10px 6px; font: 13.5px/1.4 var(--serif); color: var(--ink-3); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .g-title.label { font: 600 11px/1.2 var(--sans); }
  .pt { position: relative; display: block; padding: 8px 10px; border-radius: 8px; text-decoration: none; transition: background-color 140ms var(--ease); }
  .pt:hover { background: var(--sunk); }
  .pt.on { background: var(--card); box-shadow: 0 0 0 1px var(--rule), 0 1px 2px var(--shade); }
  .pl { display: block; font-size: 14px; line-height: 1.4; }
  .pm { display: block; font-size: 12px; color: var(--ink-3); margin-top: 2px; }
  .main { overflow-y: auto; min-height: 0; margin: 10px 12px 12px 4px; background: var(--card); border-radius: 14px; box-shadow: var(--shadow-sheet); }
  .closed .main { margin-left: 12px; }
  .switch { display: none; }
  .state { color: var(--ink-2); max-width: 520px; margin: 48px auto; }
  .loading { display: flex; gap: 6px; justify-content: center; padding: 120px 0; }
  .loading span { width: 5px; height: 5px; border-radius: 50%; background: var(--ink-3); animation: pulse 1s var(--ease-io) infinite alternate; }
  .loading span:nth-child(2) { animation-delay: 160ms; }
  .loading span:nth-child(3) { animation-delay: 320ms; }
  @keyframes pulse { from { opacity: 0.2; } to { opacity: 1; } }
  .scrim { display: none; }
  @media (max-width: 900px) {
    .layout, .layout.closed { grid-template-columns: minmax(0, 1fr); }
    .closed .list { visibility: visible; opacity: 1; }
    .main, .closed .main { margin: 8px; }
    .list {
      position: absolute; z-index: 12; top: 0; bottom: 0; left: 0; width: min(360px, 88vw); padding-top: 12px;
      transform: translateX(-102%); transition: transform 320ms var(--ease); box-shadow: 16px 0 40px -28px var(--shade);
    }
    .list.open { transform: none; }
    .scrim { display: block; position: absolute; inset: 0; z-index: 11; background: color-mix(in oklab, var(--paper) 50%, transparent); }
    .switch {
      display: flex; align-items: center; gap: 8px; margin: 14px 16px 0; height: 32px; padding: 0 12px 0 10px;
      border-radius: 8px; border: 1px solid var(--rule); background: var(--card); font-size: 13.5px; color: var(--ink-2);
    }
  }
</style>
