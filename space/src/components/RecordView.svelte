<script>
  // One page of a patient's extracted record. Every item can be found in the article: pointing marks its words,
  // clicking keeps them marked and scrolls there.
  import { tick } from 'svelte'
  import { focus, pin, cellSegment } from '../lib/focus.svelte.js'
  import { chartable, humanize, plural } from '../lib/sections.js'
  import { partition } from '../lib/facts.js'
  import { pagesOf } from '../lib/pages.js'
  import FactRow from './FactRow.svelte'
  import FactGroup from './FactGroup.svelte'
  import Sparkline from './Sparkline.svelte'
  import Json from './Json.svelte'

  let { article, patient, page, scroller } = $props()

  let selected = $state(null)
  let details = $state({})
  let openGroups = $state({})
  let pointer = $state({ series: null, index: -1 })

  const pages = $derived(pagesOf(patient))
  const current = $derived(pages.find((p) => p.key === page) || pages[0])
  const section = $derived(current.section ? patient.sections.find((s) => s.key === current.key) : null)
  const parts = $derived(section ? partition(section) : [])

  let shownFor = null
  $effect(() => {
    if (shownFor !== patient) { shownFor = patient; selected = null; details = {}; openGroups = {} }
  })

  // value and time let a table bring the right cell into view when a fact quotes a whole row.
  const target = (f) => ({ id: f.id, evidence: f.evidence, value: f.value, time: f.time })
  const pointTarget = (s, p) => ({ id: `${s.id}:${p.cell}`, evidence: [], cells: [p.cell, p.timeCell, s.nameCell] })
  const plainTarget = (id, evidence) => ({ id, evidence })
  const pinned = (id) => focus.pinned?.id === id

  function select(f) {
    if (selected === f.id) { selected = null; pin(null) } else { selected = f.id; pin(target(f)) }
  }
  function toggleDetails(f) {
    details[f.id] = !details[f.id]
    if (details[f.id]) { selected = f.id; pin(target(f)) }
  }
  function choose(t) { pin(pinned(t.id) ? null : t) }

  // A fact a link points to: open its row (and the folded group around it), then bring it into view.
  export async function open(fact, sectionKey) {
    const folded = (sectionKey === section?.key ? parts : partition(patient.sections.find((s) => s.key === sectionKey)))
      .flatMap((g) => g.rows).find((r) => r.facts?.includes(fact))
    if (folded) openGroups[`${sectionKey}:${folded.name}`] = true
    selected = fact.id
    details[fact.id] = true
    pin(target(fact))
    await tick()
    await new Promise((r) => setTimeout(r, 320))
    const row = scroller?.querySelector(`[data-fact="${fact.id}"]`)
    if (row) scroller.scrollTo({ top: scroller.scrollTop + row.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 120, behavior: 'smooth' })
  }

  function download() {
    const blob = new Blob([JSON.stringify(patient, null, 2)], { type: 'application/json' })
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `${article.article.id}-${patient.id}.json` })
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }

  const CONTEXT_LABELS = { case_kind: 'Case kind', index_subject_description: 'Index subject description', species: 'Species', multiple_index_patients: 'Multiple index patients', subject_state: 'Subject state', care_setting: 'Care setting', chief_complaint: 'Chief complaint' }
  const contextValue = (v) => (v === true ? 'yes' : v === false ? 'no' : typeof v === 'string' && /^[a-z_]+$/.test(v) ? humanize(v).toLowerCase() : v)
</script>

<div class="record">
  <header class="view-head">
    <h2>{current.label}</h2>
    {#if current.key === 'summary'}<p>Beam's summary of the case. Every sentence cites the article.</p>
    {:else if current.key === 'measurements'}<p>Values read cell by cell from the article's tables. Point at a value to find its cell.</p>
    {:else if current.key === 'timeline'}<p>In the order Beam placed them. Times stay relative, as the article reports them.</p>
    {:else if current.key === 'raw'}<p>This patient's extracted record as the site serves it: every fact with its quotes and Beam's reasons.</p>
    {:else if section}<p>{plural(section.items.length, 'fact')}{parts.length > 1 ? ` in ${parts.length} groups` : ''}. Click one to find it in the article.</p>{/if}
  </header>

  {#if current.key === 'summary'}
    <div class="claims">
      {#each patient.summary as c, i}
        {@const t = plainTarget(`claim-${i}`, c.evidence)}
        <button class="claim" class:on={pinned(t.id)} onmouseenter={() => (focus.hover = t)} onmouseleave={() => (focus.hover = null)} onclick={() => choose(t)}>
          {c.text}
          <span class="where">{[...new Set(c.evidence.map((e) => e.seg))].join(', ')}</span>
        </button>
      {/each}
    </div>

  {:else if current.key === 'measurements'}
    {#each patient.series as s (s.id)}
      {@const numbers = s.points.filter((p) => p.value != null).length}
      <section class="series">
        <h3 class="s-name">
          <span>{s.name}</span>
          <span class="c">{s.kind && s.kind !== 'other' ? `${humanize(s.kind).toLowerCase()} · ` : ''}{plural(s.points.length, 'value')}</span>
        </h3>
        {#if chartable(s.points)}
          <Sparkline points={s.points}
            active={pointer.series === s.id ? pointer.index : -1}
            onhover={(i) => { pointer = { series: s.id, index: i }; focus.hover = i < 0 ? null : pointTarget(s, s.points[i]) }}
            onpick={(i) => pin(pointTarget(s, s.points[i]), cellSegment(s.points[i].cell))} />
        {/if}
        <ol class="points" class:dense={s.points.length > 8} class:rows={s.points.some((p) => (p.label || '').length > 9 || String(p.raw ?? '').length > 12)}>
          {#each s.points as p, i (p.cell || i)}
            <li>
              <button class:on={pinned(`${s.id}:${p.cell}`)} class:lit={pointer.series === s.id && pointer.index === i}
                onmouseenter={() => { pointer = { series: s.id, index: i }; focus.hover = pointTarget(s, p) }}
                onmouseleave={() => { pointer = { series: null, index: -1 }; focus.hover = null }}
                onclick={() => pin(pointTarget(s, p), cellSegment(p.cell))}>
                <span class="t">{p.label || '·'}</span><span class="v" class:missing={p.value == null}>{p.raw ?? p.value ?? '—'}</span>
              </button>
            </li>
          {/each}
        </ol>
        {#if numbers === 0}<p class="note">No number could be read from these cells, so they are shown as printed.</p>{/if}
      </section>
    {/each}

  {:else if current.key === 'timeline'}
    <ol class="timeline">
      {#each patient.timeline as e (e.id)}
        {@const t = plainTarget(e.id, e.evidence)}
        <li class:on={pinned(e.id)}>
          <button onmouseenter={() => (focus.hover = t)} onmouseleave={() => (focus.hover = null)} onclick={() => choose(t)}>
            <span class="text">{e.text}</span>
            {#if e.kind}<span class="kind">{e.kind.replace(/_/g, ' ')}</span>{/if}
          </button>
        </li>
      {/each}
    </ol>

  {:else if current.key === 'context'}
    {@const t = plainTarget('context', patient.caseContext.evidence)}
    <dl class="stacked">
      {#each Object.entries(patient.caseContext.fields) as [k, v]}
        <dt>{CONTEXT_LABELS[k] || humanize(k)}</dt><dd>{contextValue(v)}</dd>
      {/each}
    </dl>
    {#if patient.caseContext.evidence.length}
      <button class="text-btn" class:on={pinned('context')} onclick={() => choose(t)}>Show in article</button>
    {/if}
    {#each patient.caseContext.limitations as note}<p class="footnote">{note}</p>{/each}

  {:else if current.key === 'raw'}
    <button class="text-btn" onclick={download}>
      <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M8 2.5v8M4.75 7.25 8 10.5l3.25-3.25M2.5 12.5h11" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
      Download JSON
    </button>
    <Json value={patient} />

  {:else if section}
    {#each parts as g, gi (g.label ?? gi)}
      {#if g.label}<h3 class="group-title">{g.label}<span class="c">{g.count}</span></h3>{/if}
      <div class="facts">
        {#each g.rows as r (r.fact ? r.fact.id : `${section.key}:${r.name}`)}
          {#if r.fact}
            <FactRow fact={r.fact} section={section.key} label={section.label} implied={g.label} open={!!details[r.fact.id]} selected={selected === r.fact.id}
              onselect={() => select(r.fact)} ontoggle={() => toggleDetails(r.fact)} onquote={(e) => pin(target(r.fact), e.seg)} />
          {:else}
            {@const key = `${section.key}:${r.name}`}
            <FactGroup name={r.name} facts={r.facts} section={section.key} label={section.label} implied={g.label}
              open={!!openGroups[key]} {details} {selected} ontoggle={() => (openGroups[key] = !openGroups[key])}
              onselect={select} ondetails={toggleDetails} onquote={(f, e) => pin(target(f), e.seg)} />
          {/if}
        {/each}
      </div>
    {/each}
  {/if}
</div>

<style>
  .record { padding: 30px 32px 120px; }
  .record > :global(*) { max-width: 680px; }
  .view-head { margin-bottom: 18px; }
  .view-head h2 { margin: 0; font: 600 22px/1.3 var(--serif); letter-spacing: -0.01em; text-wrap: balance; }
  .view-head p { margin: 6px 0 0; font-size: 14px; color: var(--ink-3); }
  .group-title {
    display: flex; align-items: baseline; gap: 8px; margin: 28px 0 6px;
    font: 600 12px/1.2 var(--sans); letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3);
  }
  .group-title .c { font-weight: 500; letter-spacing: 0; }
  .facts { display: grid; margin: 0 -12px; }
  .c { font-size: 12px; color: var(--ink-3); font-variant-numeric: tabular-nums; }

  .claims { display: grid; gap: 2px; margin: 0 -14px; }
  .claim {
    display: block; width: 100%; text-align: left; padding: 10px 14px; border-radius: 12px;
    font: 16.5px/1.7 var(--serif); color: var(--ink); transition: background-color 200ms var(--ease);
  }
  .claim:hover { background: var(--sunk); }
  .claim.on { background: var(--hl-soft); }
  .where { margin-left: 8px; font: 500 12px var(--sans); color: var(--ink-3); white-space: nowrap; }

  .series { padding: 18px 0; border-bottom: 1px solid var(--rule); }
  .series:first-of-type { padding-top: 4px; }
  .s-name { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin: 0 0 12px; font: 500 15px/1.35 var(--sans); color: var(--ink); }
  .s-name .c { flex: none; }
  .points { list-style: none; margin: 12px 0 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(78px, 1fr)); border-top: 1px solid var(--rule); }
  .points.dense { grid-template-columns: repeat(auto-fill, minmax(64px, 1fr)); }
  .points li { border-bottom: 1px solid var(--rule); }
  .points button { width: 100%; display: flex; flex-direction: column; align-items: flex-start; gap: 1px; padding: 7px 8px 7px 0; text-align: left; transition: background-color 160ms var(--ease); }
  .points button:hover, .points button.lit { background: var(--hl-soft); }
  .points button.on { background: var(--hl); }
  .points .t { font-size: 11.5px; color: var(--ink-3); padding-left: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
  .points .v { font-size: 13.5px; font-variant-numeric: tabular-nums; padding-left: 6px; overflow-wrap: anywhere; }
  .points .v.missing { color: var(--ink-3); }
  .points.rows { grid-template-columns: minmax(0, 1fr); }
  .points.rows button { flex-direction: row; justify-content: space-between; align-items: baseline; gap: 16px; padding: 7px 6px 7px 0; }
  .points.rows .t { font-size: 13px; color: var(--ink-2); white-space: normal; }
  .points.rows .v { text-align: right; flex: none; max-width: 55%; }
  .note { margin: 10px 0 0; font-size: 12.5px; color: var(--ink-3); }

  .timeline { list-style: none; margin: 0 0 0 4px; padding: 0 0 0 18px; position: relative; }
  .timeline::before { content: ''; position: absolute; left: 4px; top: 16px; bottom: 16px; width: 2px; border-radius: 2px; background: var(--rule); }
  .timeline li { position: relative; }
  .timeline li::before {
    content: ''; position: absolute; left: -19px; top: 16px; z-index: 1; width: 10px; height: 10px; border-radius: 50%;
    background: var(--card); box-shadow: 0 0 0 2px var(--ink-3); transition: background-color 150ms var(--ease), box-shadow 150ms var(--ease), transform 200ms var(--spring);
  }
  .timeline li:hover::before, .timeline li.on::before { background: var(--hl-edge); box-shadow: 0 0 0 2px var(--hl-edge); transform: scale(1.15); }
  .timeline button { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 10px; width: 100%; text-align: left; padding: 10px 12px; border-radius: 10px; transition: background-color 180ms var(--ease); }
  .timeline button:hover { background: var(--sunk); }
  .timeline li.on button { background: var(--hl-soft); }
  .timeline .text { font-size: 15px; font-weight: 500; line-height: 1.45; color: var(--ink); }
  .timeline .kind { font-size: 12.5px; color: var(--ink-3); }

  .stacked { margin: 0 0 8px; }
  .stacked dt { font-size: 12.5px; font-weight: 500; color: var(--ink-3); }
  .stacked dd { margin: 2px 0 18px; font: 16.5px/1.55 var(--serif); color: var(--ink); }
  .text-btn {
    display: inline-flex; align-items: center; gap: 7px; margin-left: -10px; padding: 7px 10px; border-radius: 9px;
    font-size: 13.5px; font-weight: 500; color: var(--ink); transition: background-color 150ms var(--ease);
  }
  .text-btn svg { color: var(--hl-edge); }
  .text-btn:hover { background: var(--sunk); }
  .text-btn.on { background: var(--hl-soft); }
  .footnote { margin: 22px 0 0; font-size: 13px; line-height: 1.6; color: var(--ink-3); }
  @media (max-width: 1200px) { .record { padding: 24px 24px 100px; } }
  @media (max-width: 900px) { .record { padding: 20px 18px 120px; } }
</style>
