<script>
  import { onDestroy } from 'svelte'
  import { loadIndex, loadArticle, loadRecord } from '../lib/data.js'
  import { runs } from '../lib/marks.js'
  import { chart, title, value, codings, dosage, extension, sourceOf } from '../lib/fhir.js'
  import { chartable } from '../lib/sections.js'
  import { describe } from '../lib/facts.js'
  import { labelOf } from '../lib/pages.js'
  import Sparkline from './Sparkline.svelte'

  let index = $state(null)
  let excerpt = $state(null)
  let preview = $state(null)
  let step = $state(0)

  // A real paragraph from the featured article and three facts the model took from it.
  function pickExcerpt(article) {
    const patient = article.patients[0]
    const facts = patient.sections.flatMap((s) => s.items.map((f) => ({ ...f, ...describe(f, s.key, s.label), section: s.key, sectionLabel: labelOf(s.key, s.label) })))
    let best = null
    for (const block of article.blocks) {
      if (block.type !== 'p' || block.text.length > 900) continue
      const seen = new Set()
      const picks = []
      for (const f of facts) {
        const e = f.evidence.find((x) => x.seg === block.id && x.quote.length < 140 && block.text.includes(x.quote))
        if (e && !seen.has(f.section) && !picks.some((p) => p.quote === e.quote)) { seen.add(f.section); picks.push({ ...f, quote: e.quote }) }
        if (picks.length === 3) break
      }
      if (!best || picks.length > best.picks.length) best = { block, picks }
      if (picks.length === 3) break
    }
    if (!best?.picks.length) return null
    const order = best.picks.sort((a, b) => best.block.text.indexOf(a.quote) - best.block.text.indexOf(b.quote))
    return { text: best.block.text, id: best.block.id, picks: order }
  }

  // A table from the article, its cells lighting up one by one, and the Observations they became, then two other resources.
  function pickPreview(record, article) {
    const c = chart(record.bundle)
    const condition = c.problems.find((r) => codings(r.code).length) || c.problems[0]
    const medication = c.medications.find((r) => dosage(r)) || c.medications[0]
    const fromTables = c.series.filter((s) => s.points.every((p) => extension(p.resource, 'reported-relative-time')) && chartable(s.points))
    const pool = fromTables.length ? fromTables : c.series
    // The longest series, and among those the one that moves the most, so the chart has a shape.
    const most = Math.max(0, ...pool.map((s) => s.points.length))
    const spread = (s) => { const v = s.points.map((p) => p.value); return (Math.max(...v) - Math.min(...v)) / (Math.max(...v.map(Math.abs)) || 1) }
    const series = pool.filter((s) => s.points.length === most).sort((a, b) => spread(b) - spread(a))[0]
    return { condition, medication, series, table: series ? tableOf(series, article) : null, total: c.total }
  }

  // The rows of the article's table around the one the series was read from, with the columns of its values.
  function tableOf(series, article) {
    const cells = series.points.map((p) => sourceOf(p.resource)?.cells?.ids?.find((id) => /-c[1-9]\d*$/.test(id))).filter(Boolean)
    const seg = cells[0]?.replace(/-c\d+$/, '')
    const block = seg && article.blocks.find((b) => b.type === 'table' && b.rows?.some((r) => r.id === seg))
    if (!block) return null
    const at = block.rows.findIndex((r) => r.id === seg)
    const from = Math.max(0, Math.min(at - 1, block.rows.length - 4))
    return { label: block.label, caption: block.caption, head: block.head, rows: block.rows.slice(from, from + 4), seg, cols: cells.map((id) => +/-c(\d+)$/.exec(id)[1]) }
  }

  loadIndex().then(async (i) => {
    index = i
    const featured = i.articles.find((a) => a.id === i.featured)
    const [article, record] = await Promise.all([loadArticle(featured.id), loadRecord(featured.patients[0].bundle)])
    excerpt = pickExcerpt(article)
    preview = pickPreview(record, article)
  })

  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
  const timer = setInterval(() => { step = reduced ? 4 : (step + 1) % 7 }, 1400)
  onDestroy(() => clearInterval(timer))

  const lit = $derived(excerpt ? Math.min(step, excerpt.picks.length) : 0)
  const cellsLit = $derived(preview?.table ? Math.min(step, preview.table.cols.length) : 0)
  // Each fact keeps one tint, in the paragraph and on its section name, so a quote and its fact read as a pair.
  const marks = $derived(excerpt ? excerpt.picks.slice(0, lit).map((p, i) => ({ quote: p.quote, kind: `t${i + 1}` })) : [])
</script>

<!-- Table text marks subscripts as _(2) and superscripts as ^(6). -->
{#snippet rich(t)}{#each (t || '').split(/([_^]\([^)]*\))/) as part}{#if part.startsWith('_(')}<sub>{part.slice(2, -1)}</sub>{:else if part.startsWith('^(')}<sup>{part.slice(2, -1)}</sup>{:else}{part}{/if}{/each}{/snippet}

<div class="home">
  <p class="intro">
    Patient records built from {index ? `${index.totals.articles} ` : ''}open-access case reports. Each fact is traced to the
    words it came from, then compiled to HL7 FHIR R4.
  </p>

  <div class="doors">
    <a class="door" href="#/articles">
      <div class="visual">
        {#if excerpt}
          <p class="excerpt">
            {#each runs(excerpt.text, marks) as run}
              {#if run.kind}<mark class={run.kind}>{run.text}</mark>{:else}{run.text}{/if}
            {/each}
          </p>
          <ul class="pulled">
            {#each excerpt.picks as p, i (p.id)}
              <li class:on={i < lit}>
                <span class="sec t{i + 1}">{p.sectionLabel}</span><span class="n">{p.name}</span>{#if p.value}<span class="v">{p.value}</span>{/if}
              </li>
            {/each}
          </ul>
        {/if}
      </div>
      <div class="words">
        <h2>Articles</h2>
        <p>Read each case report beside what Reflection Beam extracted from it. Select a fact to see the passage it came from and Beam's reason for keeping it.</p>
        <span class="go">{index ? `${index.totals.articles} articles · ${index.totals.facts.toLocaleString()} facts` : ''}<span class="arrow" aria-hidden="true">→</span></span>
      </div>
    </a>

    <a class="door" href="#/records">
      <div class="visual">
        {#if preview}
          {#if preview.table}
            <figure class="src">
              <figcaption><span class="tbl">{preview.table.label}</span>{preview.table.caption}</figcaption>
              <div class="tscroll">
                <table>
                  <thead>
                    {#each preview.table.head as h (h.key)}
                      <tr>{#each h.cells as cell}<th colspan={cell.cs || 1} rowspan={cell.rs || 1}>{@render rich(cell.t)}</th>{/each}</tr>
                    {/each}
                  </thead>
                  <tbody>
                    {#each preview.table.rows as r (r.id)}
                      <tr class:on={r.id === preview.table.seg}>
                        {#each r.cells as cell, j}
                          <td colspan={cell.cs || 1} rowspan={cell.rs || 1} class:lit={r.id === preview.table.seg && preview.table.cols.slice(0, cellsLit).includes(j)}>{@render rich(cell.t)}</td>
                        {/each}
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            </figure>
          {/if}
          <div class="mini">
            {#if preview.series}
              <div class="r chart-row" style="--d: 0ms">
                <span class="t">Observation ×{preview.series.points.length}</span><span class="n">{preview.series.name}</span>
                <div class="spark"><Sparkline points={preview.series.points} height={38} active={cellsLit - 1} /></div>
                <span class="d">{preview.series.points.map((p) => value(p.resource)).join('  →  ')}</span>
              </div>
            {/if}
            {#if preview.condition}
              <div class="r" style="--d: 120ms">
                <span class="t">Condition</span><span class="n">{title(preview.condition)}</span>
                {#each codings(preview.condition.code).slice(0, 1) as code}<span class="code"><span class="sys">ICD-10-CM</span>{code.code}</span>{/each}
              </div>
            {/if}
            {#if preview.medication}
              <div class="r" style="--d: 240ms">
                <span class="t">MedicationStatement</span><span class="n">{title(preview.medication)}</span><span class="d">{dosage(preview.medication) || ''}</span>
              </div>
            {/if}
          </div>
        {/if}
      </div>
      <div class="words">
        <h2>Records</h2>
        <p>Each patient as an HL7 FHIR R4 bundle, explained resource by resource. The values were reported for real cases, so the records carry clinical detail that simulated data leaves out.</p>
        <span class="go">{index ? `${index.totals.patients} patients · ${index.totals.resources.toLocaleString()} resources` : ''}<span class="arrow" aria-hidden="true">→</span></span>
      </div>
    </a>
  </div>

  <div class="foot">
    <a class="how" href="#/how/1">How it works<span class="arrow" aria-hidden="true">→</span></a>
    <span class="muted">One article followed from its text to a validated FHIR record, in ten steps.</span>
    <span class="credit muted">Extraction by Reflection Beam on Modal · Articles from PubMed Central, CC BY</span>
  </div>
</div>

<style>
  .home { height: 100%; overflow-y: auto; padding: 36px 40px 36px; display: flex; flex-direction: column; max-width: 1480px; margin: 0 auto; }
  .intro { max-width: 640px; margin: 0 0 28px; font: 20px/1.5 var(--serif); color: var(--ink-2); animation: rise 500ms var(--ease) both; text-wrap: pretty; }
  .doors { flex: 1 0 auto; min-height: 520px; display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: minmax(0, 1fr) auto auto auto; column-gap: 20px; }
  .door {
    display: grid; grid-row: span 4; grid-template-rows: subgrid; row-gap: 0; text-decoration: none; border: 1px solid var(--rule); border-radius: 14px;
    background: var(--card); overflow: hidden; animation: rise 560ms var(--ease) both;
    transition: border-color 220ms var(--ease), box-shadow 320ms var(--ease);
  }
  .door + .door { animation-delay: 90ms; }
  .door:hover { border-color: var(--rule-strong); box-shadow: 0 22px 48px -36px var(--shade); }
  .visual {
    min-height: 280px; position: relative; padding: 34px 36px; border-bottom: 1px solid var(--rule);
    display: flex; flex-direction: column; justify-content: safe center;
  }
  .words { grid-row: span 3; display: grid; grid-template-rows: subgrid; row-gap: 0; align-items: start; padding: 24px 36px 28px; }
  h2 { font: 600 28px/1.1 var(--serif); letter-spacing: -0.01em; margin: 0 0 10px; }
  .words p { margin: 0 0 18px; color: var(--ink-2); max-width: 520px; line-height: 1.55; }
  .go { justify-self: start; display: inline-flex; align-items: center; gap: 10px; font-size: 14px; color: var(--ink); }
  .arrow { display: inline-block; transition: transform 260ms var(--ease); }
  .door:hover .arrow, .how:hover .arrow { transform: translateX(4px); }

  /* Three tints for the three facts: the site's highlighter first, then green and rose, each with a darker edge. */
  .door {
    --t1: var(--hl); --t1-edge: var(--hl-edge);
    --t2: light-dark(#d4eedd, #1c3a2f); --t2-edge: light-dark(#3f9d6c, #5cc596);
    --t3: light-dark(#f8dbe5, #3d2232); --t3-edge: light-dark(#cc5f86, #e48aae);
  }
  .excerpt { font: 17.5px/1.72 var(--serif); margin: 0; max-width: 580px; color: var(--ink); animation: fade-in 500ms var(--ease) both; }
  .excerpt mark { transition: background-color 400ms var(--ease); }
  .t1 { background: var(--t1); box-shadow: inset 0 -1.5px 0 var(--t1-edge); }
  .t2 { background: var(--t2); box-shadow: inset 0 -1.5px 0 var(--t2-edge); }
  .t3 { background: var(--t3); box-shadow: inset 0 -1.5px 0 var(--t3-edge); }
  .pulled { list-style: none; padding: 0; margin: 24px 0 0; display: flex; flex-direction: column; border-top: 1px solid var(--rule); max-width: 600px; }
  .pulled li {
    display: grid; grid-template-columns: 160px auto 1fr; align-items: baseline; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--rule);
    font-size: 14px; opacity: 0.25; transition: opacity 500ms var(--ease);
  }
  .pulled li.on { opacity: 1; }
  .pulled .sec { justify-self: start; padding: 3px 5px 2px; border-radius: 4px; font: 600 10.5px/1.2 var(--sans); letter-spacing: 0.08em; text-transform: uppercase; white-space: nowrap; color: var(--ink); }
  .pulled .n { font-weight: 500; }
  .pulled .v { font: 12.5px var(--mono); color: var(--ink-2); }

  .src { margin: 0 0 22px; max-width: 580px; animation: fade-in 500ms var(--ease) both; }
  figcaption { margin: 0 0 8px; font-size: 12.5px; color: var(--ink-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tbl { margin-right: 8px; font: 600 10.5px var(--sans); letter-spacing: 0.08em; text-transform: uppercase; }
  .tscroll { overflow-x: auto; border: 1px solid var(--rule); border-radius: 10px; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; font-variant-numeric: tabular-nums; }
  th, td { padding: 6px 10px; text-align: left; white-space: nowrap; border-bottom: 1px solid var(--rule); }
  th { font-weight: 600; color: var(--ink-2); background: var(--sunk); }
  td { color: var(--ink-3); transition: background-color 400ms var(--ease), color 300ms var(--ease); }
  td:first-child { max-width: 210px; overflow: hidden; text-overflow: ellipsis; }
  tbody tr:last-child td { border-bottom: 0; }
  tr.on td { color: var(--ink); }
  tr.on td:first-child { font-weight: 500; }
  td.lit { background: var(--hl); box-shadow: inset 0 -1.5px 0 var(--hl-edge); }
  .mini { display: flex; flex-direction: column; max-width: 580px; border-top: 1px solid var(--rule); }
  .r {
    display: grid; grid-template-columns: 172px 1fr auto; align-items: baseline; gap: 4px 14px;
    padding: 12px 0; border-bottom: 1px solid var(--rule); animation: rise 520ms var(--ease) both; animation-delay: var(--d);
  }
  .r .t { font: 12px var(--mono); color: var(--ink-3); }
  .r .n { font-weight: 500; }
  .r .code { display: inline-flex; gap: 6px; align-items: baseline; font: 12px var(--mono); padding: 1px 7px; border-radius: 5px; border: 1px solid var(--rule); }
  .r .sys { font-size: 10.5px; color: var(--ink-3); }
  .r .d { grid-column: 2 / -1; font-size: 13px; color: var(--ink-2); }
  .r.chart-row .spark { grid-column: 2 / -1; padding: 6px 0 2px; }
  .r.chart-row .d { font-family: var(--mono); font-size: 12px; }

  .foot { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 16px; margin-top: 22px; font-size: 14px; }
  .how { display: inline-flex; gap: 10px; text-decoration: none; font-weight: 600; }
  .credit { margin-left: auto; font-size: 13px; }
  @media (max-width: 900px) {
    .home { padding: 22px 16px 28px; }
    .intro { font-size: 18px; }
    .doors { flex: none; min-height: 0; display: flex; flex-direction: column; gap: 20px; }
    .door { display: flex; flex-direction: column; }
    .words { display: block; }
    .visual { flex: none; min-height: 0; padding: 22px 20px; }
    .words { padding: 18px 20px 22px; }
    .pulled li { grid-template-columns: minmax(0, 1fr); gap: 2px; }
    .r { grid-template-columns: minmax(0, 1fr); }
    .r .d, .r.chart-row .spark { grid-column: 1 / -1; }
    .r .code { justify-self: start; }
    .credit { margin-left: 0; }
  }
</style>
