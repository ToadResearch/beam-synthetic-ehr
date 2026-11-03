<script>
  import { onDestroy, tick, untrack } from 'svelte'
  import { fade } from 'svelte/transition'
  import { route, go, href } from '../lib/router.svelte.js'
  import { loadIndex, loadArticle } from '../lib/data.js'
  import { uploads } from '../lib/uploads.svelte.js'
  import { focus, pin } from '../lib/focus.svelte.js'
  import { find } from '../lib/find.svelte.js'
  import { layout, remember, openPanel } from '../lib/layout.svelte.js'
  import { pagesOf } from '../lib/pages.js'
  import Reader from './Reader.svelte'
  import RecordView from './RecordView.svelte'
  import ArticleLibrary from './ArticleLibrary.svelte'
  import Splitter from './Splitter.svelte'

  let index = $state(null)
  let data = $state(null)
  let error = $state(null)
  let scroller = $state()
  let recordScroller = $state()
  let record = $state()
  let grid = $state()
  let read = $state(0)
  let page = $state('context')
  let pane = $state('article')

  loadIndex().then((i) => (index = i)).catch((e) => (error = e.message))
  openPanel()

  const id = $derived(route.id || index?.featured || null)

  async function fetchArticle(key) {
    if (!key.startsWith('upload-')) return loadArticle(key)
    const upload = uploads.articles.find((a) => a.key === key)
    if (!upload) throw new Error('That opened file is no longer in this tab. Open it again.')
    if (!upload.blocks.length && index?.articles.some((a) => a.id === upload.article.id)) {
      const bundled = await loadArticle(upload.article.id)
      return { ...upload, blocks: bundled.blocks, article: { ...bundled.article, ...upload.article } }
    }
    return upload
  }

  $effect(() => {
    const key = id
    if (!key) return
    data = null
    error = null
    // A new article starts at the top with nothing selected. The selection includes where to scroll, and segment
    // ids repeat across articles (b00001 …), so a stale one would jump into the new article.
    focus.hover = null
    pin(null)
    untrack(() => {
      if (scroller) scroller.scrollTop = 0
      if (recordScroller) recordScroller.scrollTop = 0
      read = 0
    })
    fetchArticle(key).then((d) => { if (key === id) data = d }).catch((e) => { if (key === id) error = e.message })
  })

  const patient = $derived(data ? data.patients.find((p) => p.id === route.params.p) || data.patients[0] : null)
  const pages = $derived(patient ? pagesOf(patient) : [])
  // The FHIR record compiled for the patient on show, when the article is in this dataset.
  const bundle = $derived(index?.articles.find((a) => a.id === data?.article.id)?.patients.find((p) => p.id === patient?.id)?.bundle || null)
  // The publisher's article type and the PubMed Central id, both from the article's own metadata.
  const eyebrow = $derived(data ? [data.article.type?.replace(/-/g, ' '), data.article.pmcid].filter(Boolean).join(' · ') : '')

  // A new patient opens on its first page.
  let pageFor = null
  $effect(() => {
    if (patient && pageFor !== patient) { pageFor = patient; if (!pages.some((p) => p.key === page)) page = pages[0]?.key }
  })

  let strip = $state()
  function choosePage(key) {
    page = key
    focus.pinned = null
    recordScroller?.scrollTo({ top: 0 })
    // On a phone the sections are a strip: keep the chosen one in view.
    tick().then(() => {
      const chip = strip?.querySelector('.active')
      if (chip) strip.scrollTo({ left: chip.offsetLeft - (strip.clientWidth - chip.offsetWidth) / 2, behavior: 'smooth' })
    })
  }
  function choosePatient(p) { go('articles', route.id || data.article.id, { p: p.id }) }

  // A link from a FHIR resource arrives with the quote (or the table cells) it was compiled from.
  $effect(() => {
    if (!data || !patient || !route.params.seg) return
    if (route.params.cells) {
      pin({ id: 'link', evidence: [], cells: route.params.cells.split(',') }, route.params.seg)
      return
    }
    const quote = route.params.quote
    const fact = patient.sections.flatMap((s) => s.items.map((f) => ({ f, s }))).find(({ f }) => f.evidence.some((e) => e.seg === route.params.seg && (!quote || e.quote.startsWith(quote.slice(0, 60)))))
    if (fact) {
      page = fact.s.key
      pane = 'record'
      tick().then(() => record?.open(fact.f, fact.s.key))
    } else pin({ id: 'link', evidence: [{ seg: route.params.seg, quote }] })
  })

  function progress() {
    const max = scroller.scrollHeight - scroller.clientHeight
    read = max > 0 ? Math.min(1, scroller.scrollTop / max) : 0
  }

  // Find in article: count what the reader drew, mark the current match and bring it into view.
  let typed = ''
  $effect(() => {
    const q = find.query
    void data
    tick().then(() => {
      const fresh = q !== typed
      typed = q
      if (fresh) find.current = 0
      show(fresh)
    })
  })
  function matches() { return scroller ? [...scroller.querySelectorAll('mark.hit, td.hit, th.hit')] : [] }
  function show(scroll = true) {
    const all = matches()
    find.count = all.length
    if (find.current >= all.length) find.current = 0
    all.forEach((m, i) => m.classList.toggle('current', i === find.current))
    const now = all[find.current]
    if (scroll && now) reveal(now)
  }
  // Bring a match into view inside the article sheet only (and inside its table, for a cell).
  function reveal(el) {
    const box = scroller.getBoundingClientRect()
    const r = el.getBoundingClientRect()
    scroller.scrollTo({ top: scroller.scrollTop + r.top - box.top - box.height / 2 + r.height / 2, behavior: 'smooth' })
    const table = el.closest('.scroll')
    if (table) {
      const t = table.getBoundingClientRect()
      if (r.left < t.left || r.right > t.right) table.scrollTo({ left: table.scrollLeft + r.left - t.left - (t.width - r.width) / 2, behavior: 'smooth' })
    }
  }
  function step(d) {
    if (!find.count) return
    find.current = (find.current + d + find.count) % find.count
    show()
  }
  function findKey(e) {
    if (e.key === 'Enter') { e.preventDefault(); step(e.shiftKey ? -1 : 1) }
    if (e.key === 'Escape') find.query = ''
  }

  // Splitter: the article sheet's share of the width the two sheets have between them.
  function resize(x) {
    const a = grid.querySelector('.source').getBoundingClientRect()
    const b = grid.querySelector('.record').getBoundingClientRect()
    const room = b.right - a.left - 12
    if (room > 0) layout.split = Math.min(75, Math.max(30, ((x - a.left - 6) / room) * 100))
  }

  function download() {
    const blob = new Blob([JSON.stringify({ article: data.article, patients: data.patients }, null, 2)], { type: 'application/json' })
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `${data.article.id || 'article'}.json` })
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }

  onDestroy(() => { focus.hover = null; focus.pinned = null; find.query = '' })
</script>

{#snippet sectionLinks(cls)}
  {#each pages as p (p.key)}
    <button class={cls} class:active={p.key === page} class:quiet={p.quiet} onclick={() => choosePage(p.key)}>{p.label}</button>
  {/each}
{/snippet}

<div class="workspace" class:closed={!layout.library}>
  <aside class="library-col" aria-label="Articles">
    {#if index}<ArticleLibrary {index} current={id} onpick={() => { if (innerWidth <= 900) layout.library = false }} />{/if}
  </aside>
  {#if layout.library}<button class="scrim" aria-label="Close the article list" onclick={() => (layout.library = false)}></button>{/if}

  <div class="reading" bind:this={grid} style="--a: {layout.split}fr; --b: {100 - layout.split}fr" data-pane={pane}>
    <section class="sheet source" aria-label="Article">
      <div class="sheet-bar">
        <span class="sheet-label">Article</span>
        <div class="find">
          <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.5" /><path d="m10.5 10.5 3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg>
          <input type="search" placeholder="Find in article" bind:value={find.query} onkeydown={findKey} aria-label="Find in article" />
          {#if find.query.trim().length >= 2}<span class="find-count">{find.count ? `${find.current + 1}/${find.count}` : 'none'}</span>{/if}
        </div>
      </div>
      <div class="progress" style="--read: {read}"></div>
      <div class="sheet-scroll" bind:this={scroller} onscroll={progress}>
        {#if error}
          <p class="state">{error}</p>
        {:else if !data}
          <div class="loading" aria-label="Loading"><span></span><span></span><span></span></div>
        {:else}
          {#key data.article.id}
            <div in:fade={{ duration: 220 }}>
              <header class="article-head">
                {#if eyebrow}<p class="eyebrow">{eyebrow}</p>{/if}
                <h1>{data.article.title}</h1>
                {#if data.article.citation}<p class="byline">{data.article.citation.replace(/\s*doi:.*$/i, '')}</p>{/if}
                <p class="links">
                  {#if bundle}<a href={href('records', bundle)} title={data.patients.length > 1 ? `The FHIR record of ${patient.label}` : 'The FHIR record compiled from this article'}>FHIR record<span aria-hidden="true"> →</span></a>{/if}
                  {#if data.article.url}<a href={data.article.url} target="_blank" rel="noreferrer">PubMed Central<span aria-hidden="true"> ↗</span></a>{/if}
                  <button class="link" onclick={download}>Download JSON</button>
                </p>
                {#if data.article.license}
                  <p class="license">
                    {#if data.article.licenseUrl}<a href={data.article.licenseUrl} target="_blank" rel="noreferrer">{data.article.license}</a>{:else}{data.article.license}{/if}{#if data.article.copyright}, {data.article.copyright.replace(/\.\s*$/, '')}{/if}. Shown unchanged.
                  </p>
                {/if}
              </header>
              <div class="article-text">
                {#if data.blocks.length}
                  <Reader blocks={data.blocks} {scroller} />
                {:else}
                  <p class="state">This file has the extracted record but not the article text. Open it together with the article's source packet (<span class="mono">inputs/&lt;article&gt;/source.jsonl</span> in the run folder) to see each fact in place.</p>
                {/if}
              </div>
            </div>
          {/key}
        {/if}
      </div>
    </section>

    <Splitter value={layout.split} onmove={resize} onnudge={(d) => (layout.split = Math.min(75, Math.max(30, layout.split + d)))} onend={remember} label="Resize the article and the record" />

    <section class="sheet record" aria-label="Extracted record">
      <div class="sheet-bar">
        {#if data && data.patients.length > 1}
          <div class="patients" role="tablist" aria-label="Patients in this article">
            {#each data.patients as p, i (p.id)}
              <button role="tab" aria-selected={p.id === patient?.id} class:active={p.id === patient?.id} onclick={() => choosePatient(p)} title={p.label}>Patient {i + 1}</button>
            {/each}
          </div>
        {:else}
          <span class="sheet-label">Extracted record</span>
        {/if}
      </div>
      <nav class="strip" bind:this={strip} aria-label="Record sections">{@render sectionLinks('chip')}</nav>
      <div class="sheet-scroll" bind:this={recordScroller}>
        {#if data && patient}
          {#key `${patient.id}:${page}`}
            <div in:fade={{ duration: 180 }}><RecordView bind:this={record} article={data} {patient} {page} scroller={recordScroller} /></div>
          {/key}
        {/if}
      </div>
    </section>

    <nav class="sections" aria-label="Record sections">{@render sectionLinks('section-link')}</nav>
  </div>

  <div class="pane-switch" role="tablist" aria-label="Show">
    <button role="tab" aria-selected={pane === 'article'} class:on={pane === 'article'} onclick={() => (pane = 'article')}>Article</button>
    <button role="tab" aria-selected={pane === 'record'} class:on={pane === 'record'} onclick={() => (pane = 'record')}>Record</button>
  </div>
</div>

<style>
  .workspace {
    position: relative; height: 100%; overflow: hidden; display: grid; grid-template-columns: 280px minmax(0, 1fr);
    transition: grid-template-columns 260ms var(--ease);
  }
  .workspace.closed { grid-template-columns: 0 minmax(0, 1fr); }
  .library-col { min-width: 0; min-height: 0; overflow: hidden; padding: 10px 6px 0 12px; transition: opacity 200ms var(--ease); }
  .closed .library-col { visibility: hidden; opacity: 0; }
  .scrim, .pane-switch, .strip { display: none; }

  .reading {
    min-width: 0; min-height: 0; padding: 10px 12px 12px 4px; display: grid;
    grid-template-columns: minmax(0, var(--a)) 12px minmax(0, var(--b)) 176px; overflow: hidden;
  }
  .closed .reading { padding-left: 12px; }
  .sheet { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; background: var(--card); border-radius: 14px; box-shadow: var(--shadow-sheet); }
  .sheet-bar { flex: none; display: flex; align-items: center; gap: 12px; height: 50px; padding: 0 12px 0 22px; border-bottom: 1px solid var(--rule); }
  .sheet-label { font-size: 13px; font-weight: 600; color: var(--ink-3); white-space: nowrap; }
  .sheet-scroll { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; }
  .progress { flex: none; height: 2px; margin-top: -2px; position: relative; z-index: 1; background: var(--hl-edge); transform-origin: left; transform: scaleX(var(--read)); opacity: 0.8; transition: transform 100ms linear; }

  .find { position: relative; display: flex; align-items: center; margin-left: auto; width: min(260px, 60%); }
  .find svg { position: absolute; left: 11px; color: var(--ink-3); pointer-events: none; }
  .find input {
    width: 100%; height: 32px; padding: 0 52px 0 34px; border-radius: 10px; border: 1px solid transparent; background: var(--sunk);
    font-size: 13.5px; transition: background-color 150ms var(--ease), border-color 150ms var(--ease), box-shadow 150ms var(--ease);
  }
  .find input::placeholder { color: var(--ink-3); }
  .find input:focus { outline: none; background: var(--card); border-color: var(--rule-strong); box-shadow: 0 0 0 3px var(--sunk); }
  .find-count { position: absolute; right: 12px; font-size: 12px; color: var(--ink-3); pointer-events: none; font-variant-numeric: tabular-nums; }

  .article-head, .article-text { max-width: 700px; margin: 0 auto; padding: 0 44px; }
  .article-head { padding-top: 36px; padding-bottom: 28px; margin-bottom: 8px; border-bottom: 1px solid var(--rule); }
  .eyebrow { margin: 0; font-size: 12px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); }
  h1 { margin: 10px 0 12px; font: 600 27px/1.25 var(--serif); letter-spacing: -0.015em; text-wrap: balance; }
  .byline { margin: 0 0 10px; font-size: 14px; color: var(--ink-2); }
  .links { display: flex; flex-wrap: wrap; gap: 4px 18px; margin: 0; font-size: 13.5px; }
  .links a, .link { color: var(--ink); text-decoration: underline; text-decoration-color: var(--rule-strong); text-underline-offset: 3px; transition: text-decoration-color 150ms var(--ease); }
  .links a:hover, .link:hover { text-decoration-color: currentColor; }
  .license { margin: 12px 0 0; font-size: 12.5px; color: var(--ink-3); }
  .license a { color: inherit; }
  .article-text { padding-top: 12px; padding-bottom: 120px; }
  .state { color: var(--ink-2); max-width: 520px; margin: 48px auto; padding: 0 24px; line-height: 1.6; }
  .loading { display: flex; gap: 6px; justify-content: center; padding: 120px 0; }
  .loading span { width: 5px; height: 5px; border-radius: 50%; background: var(--ink-3); animation: pulse 1s var(--ease-io) infinite alternate; }
  .loading span:nth-child(2) { animation-delay: 160ms; }
  .loading span:nth-child(3) { animation-delay: 320ms; }
  @keyframes pulse { from { opacity: 0.2; } to { opacity: 1; } }

  .patients { display: flex; gap: 2px; overflow-x: auto; scrollbar-width: none; margin-left: -10px; padding: 6px; }
  .patients button { padding: 5px 11px; border-radius: 8px; font-size: 13px; color: var(--ink-2); white-space: nowrap; transition: background-color 150ms var(--ease), color 150ms var(--ease); }
  .patients button:hover { background: var(--sunk); color: var(--ink); }
  .patients button.active { background: var(--sunk); color: var(--ink); font-weight: 600; box-shadow: inset 0 -2px 0 var(--hl-edge); }

  .sections { min-height: 0; overflow: auto; padding: 6px 6px 24px 12px; }
  .sections :global(.section-link) {
    display: block; width: 100%; text-align: left; padding: 7px 12px; margin-bottom: 2px; border-radius: 10px;
    font-size: 13.5px; line-height: 1.35; color: var(--ink-2); transition: background-color 150ms var(--ease), color 150ms var(--ease), box-shadow 200ms var(--ease);
  }
  .sections :global(.section-link:hover) { background: var(--desk-hover); color: var(--ink); }
  .sections :global(.section-link.active) { background: var(--card); color: var(--ink); font-weight: 600; box-shadow: var(--shadow-card); }
  .sections :global(.section-link.quiet) { margin-top: 18px; color: var(--ink-3); }

  @media (max-width: 1200px) {
    .reading { grid-template-columns: minmax(0, var(--a)) 12px minmax(0, var(--b)) 156px; }
    .article-head, .article-text { padding-left: 32px; padding-right: 32px; }
  }

  /* Phone and narrow tablet: one sheet at a time, the list as a drawer, sections as a strip. */
  @media (max-width: 900px) {
    .workspace, .workspace.closed { grid-template-columns: minmax(0, 1fr); }
    .library-col {
      position: absolute; z-index: 12; top: 0; bottom: 0; left: 0; width: min(340px, 88vw); padding: 12px 6px 0 12px;
      background: var(--paper); box-shadow: 16px 0 40px -28px var(--shade); transform: translateX(-104%); transition: transform 300ms var(--ease);
    }
    .workspace:not(.closed) .library-col { transform: none; }
    .closed .library-col { visibility: visible; opacity: 1; }
    .scrim { display: block; position: absolute; inset: 0; z-index: 11; background: color-mix(in oklab, var(--paper) 50%, transparent); }
    .reading, .closed .reading { grid-template-columns: minmax(0, 1fr); padding: 8px 8px 64px; }
    .reading :global(.splitter), .sections { display: none; }
    .reading[data-pane='article'] .record, .reading[data-pane='record'] .source { display: none; }
    .strip { display: flex; gap: 4px; flex: none; overflow-x: auto; scrollbar-width: none; padding: 8px 12px; border-bottom: 1px solid var(--rule); }
    .strip :global(.chip) { flex: none; padding: 5px 10px; border-radius: 99px; font-size: 13px; color: var(--ink-2); white-space: nowrap; }
    .strip :global(.chip.active) { background: var(--sunk); color: var(--ink); font-weight: 600; }
    .article-head, .article-text { padding-left: 20px; padding-right: 20px; }
    .article-head { padding-top: 24px; }
    h1 { font-size: 23px; }
    .sheet-bar { padding-left: 16px; }
    .find { width: 62%; }
    .pane-switch {
      display: flex; position: absolute; z-index: 5; left: 50%; bottom: 14px; transform: translateX(-50%); padding: 3px; gap: 2px;
      border-radius: 12px; background: var(--card); box-shadow: var(--shadow-sheet);
    }
    .pane-switch button { padding: 8px 18px; border-radius: 9px; font-size: 14px; color: var(--ink-2); }
    .pane-switch button.on { background: var(--sunk); color: var(--ink); font-weight: 600; }
  }
</style>
