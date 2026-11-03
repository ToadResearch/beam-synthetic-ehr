<script>
  import { tick } from 'svelte'
  import { fade, slide } from 'svelte/transition'
  import { href } from '../lib/router.svelte.js'
  import { chart, story, byType, title, value, when, codings, systemName, conditionStatus, dosage, isDatasetBundle, sourceOf, TYPE_INFO } from '../lib/fhir.js'
  import { chartable, plural } from '../lib/sections.js'
  import { ink } from '../lib/ink.js'
  import BundleMap from './BundleMap.svelte'
  import Sparkline from './Sparkline.svelte'
  import ResourceDrawer from './ResourceDrawer.svelte'

  let { record, blocks = [] } = $props()

  let selected = $state(null)
  let picked = $state(null)
  let pointer = $state({ key: null, index: -1 })
  let root = $state()
  let open = $state({})
  let modesH = $state(0)

  const groups = $derived(byType(record.bundle))
  const parts = $derived(story(record.bundle, blocks))
  const c = $derived(chart(record.bundle))
  const fromDataset = $derived(isDatasetBundle(record.bundle))
  // Bundles without source facts cannot be told in the article's order.
  const mode = $derived(picked || (fromDataset ? 'story' : 'types'))
  const unreviewed = $derived((record.bundle.meta?.tag || []).some((t) => t.code === 'model-coding-unreviewed'))
  const article = $derived(record.article?.id && (!record.uploaded || record.linkable) ? record.article : null)

  function detail(r) {
    switch (r.resourceType) {
      case 'Condition': {
        const s = conditionStatus(r)
        return [s.refuted ? 'ruled out' : s.verification && s.verification !== 'confirmed' ? s.verification : null, s.clinical, r.bodySite?.map((b) => b.text).filter(Boolean).join(', ')].filter(Boolean).join(' · ')
      }
      case 'Observation': return value(r) || (r.dataAbsentReason?.coding?.[0]?.code === 'not-performed' ? 'not performed' : '')
      case 'MedicationStatement': case 'MedicationRequest': case 'MedicationAdministration': return dosage(r) || ''
      case 'Procedure': case 'CarePlan': case 'ServiceRequest': return r.status && !['unknown', 'completed'].includes(r.status) ? r.status : ''
      default: return ''
    }
  }

  // Values from one table row are one series: show them together, each value once.
  const numeric = (r) => r.valueQuantity?.value ?? (() => { const m = /^[<>≤≥]?\s*(-?\d[\d,]*\.?\d*)/.exec(value(r) || ''); return m ? Number(m[1].replace(/,/g, '')) : null })()
  function lines(items, tabular) {
    const out = []
    const series = new Map()
    for (const it of items) {
      const name = title(it.r)
      if ((tabular || it.fold) && it.r.resourceType === 'Observation') {
        if (!series.has(name)) { const l = { series: true, name, items: [], seen: new Set(), key: `${it.seg}:${name}` }; series.set(name, l); out.push(l) }
        const l = series.get(name)
        const id = `${when(it.r) || ''}|${value(it.r) || ''}`
        if (!l.seen.has(id)) { l.seen.add(id); l.items.push(it) }
      } else out.push({ series: false, r: it.r, key: it.r.id })
    }
    return out.map((l) => (l.series && l.items.length === 1 ? { series: false, r: l.items[0].r, key: l.items[0].r.id } : l))
  }

  // By resource type: each type is closed at first, with a line saying what is inside. Observations are split by
  // the category the bundle gives them, and the values of one table row read as one series.
  const CATEGORY = { laboratory: 'Laboratory', 'vital-signs': 'Vital signs', imaging: 'Imaging', exam: 'Examination', survey: 'Scores', procedure: 'Procedure results', 'social-history': 'Social history' }
  const CATEGORIES = [...Object.values(CATEGORY), 'Other observations']
  const categoryOf = (r) => (r.category || []).flatMap((c) => c.coding || []).map((k) => CATEGORY[k.code]).find(Boolean) || 'Other observations'
  // An Observation read several times with short values (a lab value, a color, a pressure) is one row.
  const brief = (r) => (value(r) || '').length <= 28
  function split(g) {
    const named = new Map()
    for (const r of g.items) named.set(title(r), [...(named.get(title(r)) || []), r])
    const fold = new Set([...named].filter(([, rs]) => rs.filter(brief).length > 1).map(([name]) => name))
    const rows = (items) => lines(items.map((r) => ({ r, seg: g.type, fold: r.resourceType === 'Observation' && brief(r) && fold.has(title(r)) })), false)
    if (g.type !== 'Observation') return [{ label: null, rows: rows(g.items) }]
    const by = new Map()
    for (const r of g.items) { const k = categoryOf(r); if (!by.has(k)) by.set(k, []); by.get(k).push(r) }
    const out = [...by.entries()].sort((a, b) => CATEGORIES.indexOf(a[0]) - CATEGORIES.indexOf(b[0]))
    return out.length > 1 ? out.map(([label, items]) => ({ label, count: items.length, rows: rows(items) })) : [{ label: null, rows: rows(g.items) }]
  }
  const preview = (g) => [...new Set(g.items.map((r) => title(r)))].slice(0, 8).join(' · ')
  const allOpen = $derived(groups.every((g) => open[g.type]))

  // The record scrolls inside its pane: move that, never the page, and stop below the sticky bar.
  function scroller() {
    let el = root?.parentElement
    while (el && !/(auto|scroll)/.test(getComputedStyle(el).overflowY)) el = el.parentElement
    return el
  }
  function reveal(el, smooth = true) {
    const s = scroller()
    if (!el || !s) return
    const top = s.scrollTop + el.getBoundingClientRect().top - s.getBoundingClientRect().top - modesH - 12
    s.scrollTo({ top, behavior: smooth ? 'smooth' : 'auto' })
  }
  // Closing a type while reading inside it brings its header back under the bar instead of leaving the reader lost.
  async function toggle(type, e) {
    const group = e.currentTarget.closest('.tgroup')
    const s = scroller()
    const inside = open[type] && s && group.getBoundingClientRect().top < s.getBoundingClientRect().top + modesH
    open = { ...open, [type]: !open[type] }
    if (inside) { await tick(); reveal(group, false) }
  }
  async function pick(type) {
    picked = 'types'
    open = { ...open, [type]: true }
    await tick()
    reveal(root?.querySelector(`#type-${type}`))
  }

  function download() {
    const blob = new Blob([JSON.stringify(record.bundle, null, 2)], { type: 'application/fhir+json' })
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `${record.bundle.id || 'bundle'}.json` })
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }
  const quoteLink = (seg, quote) => href('articles', article.id, { p: record.patient?.id, seg, quote: quote?.slice(0, 120) })
</script>

{#snippet line(r)}
  {@const codes = codings(r.code)}
  {@const refuted = r.resourceType === 'Condition' && conditionStatus(r).refuted}
  <button class="res" class:refuted onclick={() => (selected = r)}>
    <span class="rtype mono">{r.resourceType}</span>
    <span class="rbody">
      <span class="rname">{title(r)}</span>
      {#if detail(r)}<span class="rdetail">{detail(r)}</span>{/if}
      {#each codes as code}<span class="code mono" title={code.display}><span class="sys">{systemName(code.system)}</span>{code.code}</span>{/each}
    </span>
    {#if when(r)}<span class="rwhen">{when(r)}</span>{/if}
  </button>
{/snippet}

{#snippet series(l)}
  {@const pts = l.items.map((it) => ({ value: numeric(it.r), label: when(it.r), r: it.r }))}
  <div class="series">
    <div class="s-head">
      <span class="rtype mono">Observation ×{l.items.length}</span>
      <span class="rname">{l.name}</span>
    </div>
    {#if chartable(pts)}
      <div class="s-chart">
        <Sparkline points={pts} height={40} active={pointer.key === l.key ? pointer.index : -1}
          onhover={(i) => (pointer = { key: l.key, index: i })} onpick={(i) => (selected = pts[i].r)} />
      </div>
    {/if}
    <ol class="s-points">
      {#each pts as p, i}
        <li><button class:lit={pointer.key === l.key && pointer.index === i} onmouseenter={() => (pointer = { key: l.key, index: i })} onmouseleave={() => (pointer = { key: null, index: -1 })} onclick={() => (selected = p.r)}>
          <span class="t">{p.label || '·'}</span><span class="v">{value(p.r) ?? '—'}</span>
        </button></li>
      {/each}
    </ol>
  </div>
{/snippet}

<div class="record" bind:this={root}>
  <header class="top">
    <h1>{record.patient?.label || title(c.patient || { resourceType: 'Patient' })}</h1>
    <p class="who">
      {#if c.demographics.age}<span>Age {c.demographics.age}</span>{/if}
      {#if c.demographics.sex}<span class="cap">{c.demographics.sex}</span>{/if}
      {#if c.patient}<span>{title(c.patient)}</span>{/if}
      <span>FHIR R4 bundle of {plural(c.total, 'resource')}</span>
    </p>
    {#if record.article?.title}
      <p class="from">
        Compiled from {#if article}<a href="#/articles/{article.id}?p={record.patient?.id}">{record.article.title}</a>{:else}{record.article.title}{/if}{#if record.article.license}<span class="muted">, {record.article.license}</span>{/if}
      </p>
    {:else if record.uploaded}
      <p class="from">Opened from {record.name}.{fromDataset ? '' : ' This bundle has no source-fact extensions, so resources cannot be traced to an article.'}</p>
    {/if}
    <ul class="checks">
      {#if record.validation?.passed}<li class="ok" title={record.validation.scope}>Passed the official HL7 FHIR validator, 0 errors</li>{/if}
      {#if unreviewed}<li class="warn">Codes chosen by Beam and not clinically reviewed</li>{/if}
      {#if fromDataset}<li>Every resource carries the fact and quotes it was compiled from</li>{/if}
    </ul>
    <div class="actions">
      <button class="btn" onclick={() => (selected = record.bundle)}>View the bundle as JSON</button>
      <button class="btn" onclick={download}>Download</button>
    </div>
  </header>

  <section class="explain">
    <div class="intro">
      <h2>How the record is built</h2>
      <p>
        A FHIR bundle is a package of small, typed records called resources. One <span class="mono">Patient</span> resource stands for the person,
        and every other resource names that patient in its <span class="mono">subject</span> field. This bundle has {plural(c.total - 1, 'resource')} around its patient:
      </p>
    </div>
    <BundleMap {groups} onpick={pick} />
  </section>

  <div class="modes" role="tablist" aria-label="How to list the resources" bind:offsetHeight={modesH} use:ink>
    {#if fromDataset}<button role="tab" aria-selected={mode === 'story'} class:on={mode === 'story'} onclick={() => (picked = 'story')}>In the article's order</button>{/if}
    <button role="tab" aria-selected={mode === 'types'} class:on={mode === 'types'} onclick={() => (picked = 'types')}>By resource type</button>
    <span class="hint">{mode === 'story' ? 'Each passage of the article, then the resources compiled from it. Select one to read it field by field.' : 'Select a resource to read it field by field, with the passage it came from.'}</span>
  </div>

  {#key mode}
    <div in:fade={{ duration: 200 }}>
      {#if mode === 'story'}
        {#each parts as part, k}
          <section class="part">
            {#if part.heading}<h3 class="label">{part.heading}</h3>{/if}
            {#each part.passages as p (p.key)}
              <div class="passage">
                <div class="src">
                  {#if p.cells}
                    <p class="cells"><span class="tbl">{p.cells.table}</span>{p.cells.row}</p>
                  {:else if p.quote}
                    <blockquote>{p.quote}</blockquote>
                  {:else}
                    <p class="nocite">No quote attached.</p>
                  {/if}
                  {#if p.seg}
                    {#if article}<a class="seg mono" href={quoteLink(p.seg, p.quote)} title="Show in the article">{p.seg}</a>{:else}<span class="seg mono">{p.seg}</span>{/if}
                  {/if}
                </div>
                <ul class="out">
                  {#each lines(p.items, !!p.cells) as l (l.key)}
                    <li>{#if l.series}{@render series(l)}{:else}{@render line(l.r)}{/if}</li>
                  {/each}
                </ul>
              </div>
            {/each}
          </section>
        {/each}
      {:else}
        <div class="types" style="--stick: {modesH}px">
          <div class="tbar">
            <span>{plural(groups.length, 'resource type')} · {plural(c.total, 'resource')}</span>
            <button class="all" onclick={() => (open = allOpen ? {} : Object.fromEntries(groups.map((g) => [g.type, true])))}>{allOpen ? 'Close all' : 'Open all'}</button>
          </div>
          {#each groups as g (g.type)}
            <section class="tgroup" class:open={open[g.type]} id="type-{g.type}">
              <button class="thead" aria-expanded={!!open[g.type]} onclick={(e) => toggle(g.type, e)}>
                <svg class="chev" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="m6 3.5 4.5 4.5L6 12.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
                <span class="tname mono">{g.type}</span>
                <span class="tcount">{g.items.length}</span>
                <span class="tinfo">{TYPE_INFO[g.type] || ''}</span>
                {#if !open[g.type]}<span class="tpeek">{preview(g)}</span>{/if}
              </button>
              {#if open[g.type]}
                <div class="tbody" transition:slide={{ duration: 260 }}>
                  {#each split(g) as part (part.label)}
                    {#if part.label}<p class="sub"><span>{part.label}</span><span class="subn">{part.count}</span></p>{/if}
                    <ul class="flat">
                      {#each part.rows as l (l.key)}
                        {@const src = l.series ? null : sourceOf(l.r)}
                        <li>
                          {#if l.series}{@render series(l)}{:else}
                            {@render line(l.r)}
                            {#if src?.quotes[0]}<p class="q">“{src.quotes[0].quote}”</p>{:else if src?.cells}<p class="q cellq">{src.cells.row}{src.cells.column ? ` · ${src.cells.column}` : ''}{src.cells.value ? ` · ${src.cells.value}` : ''}</p>{/if}
                          {/if}
                        </li>
                      {/each}
                    </ul>
                  {/each}
                </div>
              {/if}
            </section>
          {/each}
        </div>
      {/if}
    </div>
  {/key}
</div>

{#if selected}
  <ResourceDrawer resource={selected} {record} onclose={() => (selected = null)} />
{/if}

<style>
  .record { max-width: 1040px; margin: 0 auto; padding: 34px 48px 140px; }
  .top { animation: rise 420ms var(--ease) both; }
  h1 { font: 600 32px/1.2 var(--serif); letter-spacing: -0.012em; margin: 0 0 12px; text-wrap: balance; }
  .who { display: flex; flex-wrap: wrap; gap: 4px 18px; margin: 0; font-size: 14px; color: var(--ink-2); }
  .cap::first-letter { text-transform: uppercase; }
  .from { margin: 8px 0 0; font-size: 14px; color: var(--ink-2); max-width: 760px; }
  .checks { list-style: none; display: flex; flex-wrap: wrap; gap: 6px 22px; margin: 16px 0 0; padding: 0; font-size: 13px; color: var(--ink-2); }
  .checks li { display: inline-flex; align-items: center; gap: 8px; }
  .checks li::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--ink-3); }
  .checks .ok::before { background: var(--ok); }
  .checks .warn::before { background: var(--hl-edge); }
  .actions { display: flex; gap: 8px; margin-top: 20px; }
  .btn { height: 32px; padding: 0 12px; border-radius: 8px; border: 1px solid var(--rule); background: var(--card); font-size: 13.5px; color: var(--ink-2); transition: border-color 160ms var(--ease), color 160ms var(--ease); }
  .btn:hover { color: var(--ink); border-color: var(--rule-strong); }

  .explain { margin-top: 40px; animation: rise 480ms var(--ease) 80ms both; }
  .intro h2 { font: 600 19px/1.3 var(--serif); margin: 0 0 8px; }
  .intro p { margin: 0 0 18px; max-width: 720px; color: var(--ink-2); line-height: 1.6; }

  .modes { position: sticky; top: 0; z-index: 4; display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px 22px; margin: 44px -48px 0; padding: 16px 48px 0; background: var(--card); border-bottom: 1px solid var(--rule); }
  .modes button { position: relative; padding: 0 0 12px; font-size: 14.5px; color: var(--ink-3); transition: color 160ms var(--ease); }
  .modes button:hover, .modes button.on { color: var(--ink); }
  .hint { margin-left: auto; font-size: 12.5px; color: var(--ink-3); padding-bottom: 12px; }

  .part { padding-top: 30px; }
  .part > h3.label { margin: 0 0 6px; }
  .passage {
    display: grid; grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr); gap: 28px;
    padding: 16px 0; border-bottom: 1px solid var(--rule);
  }
  .src { position: relative; padding-right: 44px; }
  blockquote { margin: 0; font: 16px/1.6 var(--serif); color: var(--ink); }
  .cells { margin: 0; font-size: 14px; color: var(--ink); }
  .tbl { display: inline-block; margin-right: 8px; font: 600 11px var(--sans); letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); }
  .nocite { margin: 0; font-size: 13.5px; color: var(--ink-3); }
  .seg { position: absolute; top: 3px; right: 0; font-size: 11px; color: var(--ink-3); text-decoration: none; }
  a.seg:hover { color: var(--ink); text-decoration: underline; }
  .out { list-style: none; margin: 0; padding: 0 0 0 18px; border-left: 1px solid var(--rule-strong); display: flex; flex-direction: column; gap: 2px; }

  .res {
    width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) auto; grid-template-rows: auto auto; column-gap: 14px;
    padding: 7px 10px; margin-left: -10px; border-radius: 8px; text-align: left; transition: background-color 150ms var(--ease);
  }
  .res:hover { background: var(--sunk); }
  .rtype { grid-column: 1; font-size: 11px; color: var(--ink-3); }
  .rbody { grid-column: 1; display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 10px; }
  .rname { font-size: 14.5px; font-weight: 500; }
  .rdetail { font-size: 13.5px; color: var(--ink-2); }
  .refuted .rname { color: var(--ink-3); text-decoration: line-through; text-decoration-color: var(--rule-strong); font-weight: 400; }
  .code { display: inline-flex; gap: 6px; align-items: baseline; font-size: 12px; padding: 1px 7px; border-radius: 5px; border: 1px solid var(--rule); color: var(--ink); }
  .sys { font-size: 10.5px; color: var(--ink-3); }
  .rwhen { grid-column: 2; grid-row: 1 / 3; align-self: center; font-size: 12.5px; color: var(--ink-3); text-align: right; max-width: 220px; }

  .series { padding: 7px 0 8px; }
  .s-head { display: flex; flex-direction: column; }
  .s-chart { margin: 8px 0 4px; max-width: 420px; }
  .s-points { list-style: none; margin: 6px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 2px; }
  .s-points button { display: flex; flex-direction: column; padding: 4px 8px 4px 6px; border-radius: 6px; text-align: left; transition: background-color 150ms var(--ease); }
  .s-points button:hover, .s-points button.lit { background: var(--sunk); }
  .s-points .t { font-size: 11px; color: var(--ink-3); }
  .s-points .v { font: 12.5px var(--mono); font-variant-numeric: tabular-nums; }

  .types { padding-top: 22px; }
  .tbar { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 0 0 12px; font-size: 13px; color: var(--ink-3); }
  .all { padding: 3px 8px; margin-right: -8px; border-radius: 7px; font-size: 13px; font-weight: 500; color: var(--ink-2); transition: background-color 150ms var(--ease), color 150ms var(--ease); }
  .all:hover { background: var(--desk-hover); color: var(--ink); }
  .tgroup { margin-bottom: 10px; border: 1px solid var(--rule); border-radius: 12px; background: var(--card); transition: border-color 200ms var(--ease); }
  .tgroup.open { border-color: var(--rule-strong); }
  .thead {
    width: 100%; display: grid; grid-template-columns: 14px auto auto minmax(0, 1fr); align-items: baseline; column-gap: 10px;
    padding: 14px 18px 15px; border-radius: 12px; text-align: left; background: var(--card); transition: background-color 160ms var(--ease);
  }
  .thead:hover { background: var(--sunk); }
  .open .thead { position: sticky; top: var(--stick); z-index: 3; border-radius: 11px 11px 0 0; border-bottom: 1px solid var(--rule); }
  .chev { align-self: center; color: var(--ink-3); transition: transform 220ms var(--ease); }
  .open .chev { transform: rotate(90deg); color: var(--ink-2); }
  .tname { font-size: 15px; color: var(--ink); }
  .tcount { font-size: 11.5px; font-variant-numeric: tabular-nums; color: var(--ink-2); padding: 0 7px; border-radius: 99px; background: var(--sunk); }
  .thead:hover .tcount { background: var(--card); }
  .tinfo { min-width: 0; font-size: 13px; color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tpeek { grid-column: 2 / -1; margin-top: 5px; font-size: 13.5px; color: var(--ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tbody { padding: 2px 18px 10px; }
  .sub { display: flex; align-items: baseline; gap: 8px; margin: 18px 0 6px; font: 600 11px/1.2 var(--sans); letter-spacing: 0.07em; text-transform: uppercase; color: var(--ink-3); }
  .subn { font-weight: 500; letter-spacing: 0; font-variant-numeric: tabular-nums; }
  .flat { list-style: none; margin: 0; padding: 0; }
  .flat li { padding: 4px 0 8px 10px; border-bottom: 1px solid var(--rule); }
  .flat li:last-child { border-bottom: 0; }
  .flat .res { margin-left: -10px; }
  .flat .rtype { display: none; }
  .q { margin: 0 0 0 0; font: italic 14px/1.5 var(--serif); color: var(--ink-2); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .cellq { font: 12.5px var(--mono); font-style: normal; }

  @media (max-width: 900px) {
    .record { padding: 22px 16px 100px; }
    h1 { font-size: 25px; }
    .modes { margin: 34px -16px 0; padding: 12px 16px 0; }
    .hint { display: none; }
    .passage { grid-template-columns: minmax(0, 1fr); gap: 10px; }
    .src { padding-right: 52px; }
    .rwhen { max-width: 120px; }
    .thead { padding: 12px 14px; }
    .thead .tinfo { display: none; }
    .tbody { padding: 2px 14px 8px; }
  }
</style>
