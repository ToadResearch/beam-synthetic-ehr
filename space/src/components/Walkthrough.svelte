<script>
  import { onDestroy } from 'svelte'
  import { fly, fade } from 'svelte/transition'
  import { route, go } from '../lib/router.svelte.js'
  import { loadTour } from '../lib/data.js'
  import { findRange, runs } from '../lib/marks.js'
  import { segmentSpan, humanize } from '../lib/sections.js'
  import Sparkline from './Sparkline.svelte'

  let tour = $state(null)
  let error = $state(null)
  loadTour().then((t) => (tour = t)).catch((e) => (error = e.message))

  const STEPS = [
    { key: 'source', title: 'One open-access case report', body: 'Only articles with a license that allows adaptation are used. The article\u2019s XML is split into numbered segments: every paragraph, table row and figure caption gets an ID that later facts must cite.' },
    { key: 'roster', title: 'Who the article is about', body: 'Reflection Beam first lists the patients the article describes. People who only appear in cited studies or the discussion are kept out, so their facts never reach a record.' },
    { key: 'fact', title: 'Facts, each with a quote', body: 'For each of fourteen sections, Beam reads windows of segments and returns facts with structured fields. A fact is only accepted with a verbatim quote from the segment it cites.' },
    { key: 'why', title: 'Beam says why', body: 'Alongside each fact Beam states why it belongs to this patient and notes what every segment it read contains. Its full reasoning is kept in the run folder.' },
    { key: 'checks', title: 'Checked against the article', body: 'Code, not Beam, checks every answer: the quote must appear in the cited segment and every field must fit the schema. Failures go back to Beam for a bounded repair.' },
    { key: 'series', title: 'Tables, cell by cell', body: 'Measurements in tables become time series. Each point names the exact cell it came from, so a value can be traced to its row and column.' },
    { key: 'timeline', title: 'Put in order', body: 'Events are placed relative to each other: before, after, during. Times stay as the article reports them. No dates are invented.' },
    { key: 'coding', title: 'ICD-10-CM: pick one or abstain', body: 'Up to eight candidates are retrieved from the FY2027 ICD-10-CM tabular list and index. Beam selects one only when it matches the fact, and abstains otherwise.' },
    { key: 'fhir', title: 'Compiled to FHIR R4', body: 'A deterministic compiler turns each fact into a FHIR resource. The source fact, with its quotes, travels with the resource as an extension.' },
    { key: 'release', title: 'Validated and released', body: 'Every bundle goes through the official HL7 FHIR validator, with bounded repair. The dataset keeps uncoded and coded bundles plus the full extraction record.' },
  ]

  const n = $derived(Math.min(Math.max(parseInt(route.id || '1', 10) || 1, 1), STEPS.length))
  const step = $derived(STEPS[n - 1])
  let direction = $state(1)

  function to(k) {
    if (k < 1 || k > STEPS.length || k === n) return
    direction = k > n ? 1 : -1
    go('how', String(k), {}, { replace: true })
  }

  function onkey(e) {
    if (e.target.closest?.('input, textarea')) return
    if (e.key === 'ArrowRight') { e.preventDefault(); to(n + 1) }
    if (e.key === 'ArrowLeft') { e.preventDefault(); to(n - 1) }
    if (e.key === 'Escape') go('articles')
  }

  // Text that types itself out on the reasoning step.
  let typed = $state(0)
  let timer
  $effect(() => {
    clearInterval(timer)
    typed = 0
    if (step.key !== 'why' || !tour?.fact?.reasoning) return
    const total = tour.fact.reasoning.length
    timer = setInterval(() => { typed = Math.min(total, typed + 6); if (typed >= total) clearInterval(timer) }, 16)
  })
  onDestroy(() => clearInterval(timer))

  function around(text, quote, pad = 220) {
    const r = findRange(text, quote)
    if (!r) return text.slice(0, pad * 2)
    const start = Math.max(0, text.lastIndexOf(' ', Math.max(0, r[0] - pad)) + 1)
    const end = Math.min(text.length, text.indexOf(' ', Math.min(text.length - 1, r[1] + pad)) + 1 || text.length)
    return (start > 0 ? '… ' : '') + text.slice(start, end).trim() + (end < text.length ? ' …' : '')
  }

  // The article's first segments, with one of each kind it has (paragraph, table row, caption).
  const outline = $derived.by(() => {
    const all = tour?.outline || []
    const picked = all.slice(0, 6)
    for (const kind of ['table_row', 'figure_caption']) {
      const s = all.find((x) => x.kind === kind)
      if (s && !picked.includes(s)) picked.push(s)
    }
    return picked
  })
  const longest = $derived(Math.max(1, ...outline.map((s) => s.chars)))

  const fhirLines = $derived.by(() => {
    if (!tour?.resource) return []
    const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
    return JSON.stringify(tour.resource, null, 2).split('\n').map((line) =>
      esc(line).replace(/("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)/g, (m, s, colon) =>
        s ? `<span class="${colon ? 'k' : 's'}">${s}</span>${colon || ''}` : `<span class="n">${m}</span>`))
  })
</script>

<svelte:window onkeydown={onkey} />

<div class="tour">
  {#if error}
    <p class="state">{error}</p>
  {:else if tour}
    <div class="frame">
      {#key n}
        <div class="slide" in:fly={{ x: 36 * direction, duration: 420, delay: 80, opacity: 0 }} out:fade={{ duration: 140 }}>
          <div class="words">
            <h1>{step.title}</h1>
            <p class="body">{step.body}</p>
            {#if step.key === 'source'}
              <p class="aside">Here: <em>{tour.article.title}</em></p>
            {:else if step.key === 'fact'}
              <p class="aside">Here: the {tour.fact.task?.replace(/^clinical_window_/, '').replace(/_/g, ' ')} pass, reading segments {segmentSpan(tour.fact.window)}.</p>
            {:else if step.key === 'coding' && tour.coding}
              <p class="aside">{tour.coding.candidates.length} candidates were retrieved for “{tour.coding.fact.name}”.</p>
            {/if}
          </div>

          <div class="visual">
            {#if step.key === 'source'}
              <div class="doc">
                <div class="doc-head">
                  <span class="lic">{tour.article.license} · allowed</span>
                  <p class="doc-title">{tour.article.title}</p>
                  <p class="doc-cite">{tour.article.citation?.replace(/\s*doi:.*$/i, '')}</p>
                </div>
                <ol class="segs">
                  {#each outline as s, i (s.id)}
                    <li style="animation-delay: {300 + i * 70}ms">
                      <span class="mono">{s.id}</span>
                      <span class="bar" class:row={s.kind !== 'paragraph'} style="width: {Math.max(8, Math.min(100, (s.chars / longest) * 100))}%"></span>
                      <span class="lab">{s.kind === 'paragraph' ? s.heading : s.kind.replace('_', ' ')}</span>
                    </li>
                  {/each}
                  <li class="more" style="animation-delay: {300 + outline.length * 70}ms"><span class="mono">…</span></li>
                </ol>
                <p class="stats">{tour.counts.segments} segments · {tour.counts.tableRows} table rows · {tour.counts.figures} figures · {tour.counts.words?.toLocaleString()} words</p>
              </div>

            {:else if step.key === 'roster'}
              {#each tour.roster.patients as p (p.id)}
                <div class="card patient">
                  <span class="mono muted">{p.id}</span>
                  <p class="big">{p.label}</p>
                </div>
                {#each p.evidence as e, i}
                  <blockquote style="animation-delay: {200 + i * 160}ms"><span class="mono">{e.seg}</span>{e.quote}</blockquote>
                {/each}
              {/each}
              <p class="note">{tour.roster.count} individual case{tour.roster.count === 1 ? '' : 's'} reported. The cited literature is excluded.</p>

            {:else if step.key === 'fact'}
              {@const e = tour.fact.evidence[0]}
              <div class="card source">
                <span class="mono muted">{tour.segment.id} · {tour.segment.heading}</span>
                <p class="seg-text">
                  {#each runs(around(tour.segment.text, e.quote), [{ quote: e.quote, kind: 'pin' }]) as run}
                    {#if run.kind}<mark class="draw">{run.text}</mark>{:else}{run.text}{/if}
                  {/each}
                </p>
              </div>
              <div class="card fact-card">
                <p class="fact-name">{tour.fact.name}</p>
                <dl>
                  <dt>section</dt><dd>conditions</dd>
                  <dt>assertion</dt><dd>{tour.fact.assertion}</dd>
                  {#if tour.fact.time}<dt>time</dt><dd>{tour.fact.time}</dd>{/if}
                  {#each Object.entries(tour.fact.fields).slice(0, 4) as [k, v]}<dt>{k.replace(/_/g, ' ')}</dt><dd>{v}</dd>{/each}
                  <dt>evidence</dt><dd>{tour.fact.evidence.length} quotes ({[...new Set(tour.fact.evidence.map((x) => x.seg))].join(', ')})</dd>
                </dl>
              </div>

            {:else if step.key === 'why'}
              <div class="card note-card"><span class="k">Why it belongs to this patient</span><p>{tour.fact.why}</p></div>
              <div class="card note-card" style="animation-delay: 140ms"><span class="k">Beam's note on {tour.fact.evidence[0].seg}</span><p>{tour.fact.segmentWhy}</p></div>
              {#if tour.fact.reasoning}
                <div class="card reasoning" style="animation-delay: 280ms">
                  <span class="k">From Beam's reasoning</span>
                  <p>{tour.fact.reasoning.slice(0, typed)}<span class="caret"></span></p>
                </div>
              {/if}

            {:else if step.key === 'checks'}
              {@const e = tour.fact.evidence[0]}
              {@const r = findRange(tour.segment.text, e.quote)}
              <ul class="checks">
                <li style="--i: 0"><span class="tick">✓</span><div><b>Quote found</b> in {e.seg}{#if r}, characters {r[0]}–{r[1]}{/if}<span class="q">“{e.quote}”</span></div></li>
                <li style="--i: 1"><span class="tick">✓</span><div><b>About this patient</b><span class="q">subject: {humanize(tour.fact.subject || 'index_patient').toLowerCase()}</span></div></li>
                <li style="--i: 2"><span class="tick">✓</span><div><b>Fields fit the schema</b><span class="q">{Object.keys(tour.fact.fields).map((k) => k.replace(/_/g, ' ')).join(', ')}</span></div></li>
                <li style="--i: 3"><span class="tick">✓</span><div><b>Accepted</b><span class="q">status {tour.fact.status}, {tour.fact.attempts > 1 ? `after ${tour.fact.attempts - 1} repair${tour.fact.attempts > 2 ? 's' : ''}` : 'on the first attempt'}</span></div></li>
              </ul>

            {:else if step.key === 'series' && tour.series}
              <div class="card">
                <p class="fact-name">{tour.series.name}</p>
                <div class="cells">
                  {#each tour.series.points as p, i}
                    <div class="cell" style="animation-delay: {150 + i * 120}ms"><span class="mono muted">{p.cell}</span><span class="t">{p.label}</span><span class="v mono">{p.raw}</span></div>
                  {/each}
                </div>
                <div class="big-spark"><Sparkline points={tour.series.points} height={120} /></div>
              </div>

            {:else if step.key === 'timeline'}
              <ol class="events">
                {#each tour.timeline as e, i (e.id)}
                  <li style="animation-delay: {120 + i * 110}ms"><span class="kind">{e.kind?.replace(/_/g, ' ')}</span><span>{e.text}</span></li>
                {/each}
              </ol>

            {:else if step.key === 'coding' && tour.coding}
              {@const chosen = tour.coding.decision.candidate_id}
              <ol class="candidates">
                {#each tour.coding.candidates as c, i (c.id)}
                  <li class:chosen={c.id === chosen} style="animation-delay: {100 + i * 70}ms; --d: {500 + tour.coding.candidates.length * 70}ms">
                    <span class="code mono">{c.code}</span><span class="disp">{c.display}</span>
                    <span class="score mono">{c.score?.toFixed(2)}</span>
                  </li>
                {/each}
              </ol>
              <div class="card decision" style="animation-delay: {700 + tour.coding.candidates.length * 70}ms">
                <span class="k">{tour.coding.decision.decision === 'select' ? `Selected, ${tour.coding.decision.relation}` : 'Abstained'}</span>
                <p>{tour.coding.decision.rationale}</p>
              </div>

            {:else if step.key === 'fhir'}
              <pre class="fhir">{#each fhirLines as line, i}<span class="line" style="animation-delay: {i * 22}ms">{@html line}</span>{'\n'}{/each}</pre>

            {:else if step.key === 'release'}
              <div class="card pass-card">
                <span class="seal">✓</span>
                <div>
                  <p class="fact-name">Passed the official HL7 FHIR validator</p>
                  <p class="muted small">{tour.validation?.errors ?? 0} errors · FHIR 4.0.1</p>
                </div>
              </div>
              <ul class="counts">
                {#each Object.entries(tour.bundleCounts).sort((a, b) => b[1] - a[1]) as [type, count], i}
                  <li style="animation-delay: {200 + i * 60}ms"><span>{type}</span><span class="bar" style="--w: {Math.max(2, (count / Math.max(...Object.values(tour.bundleCounts))) * 100)}%"></span><span class="mono">{count}</span></li>
                {/each}
              </ul>
              <div class="end-links">
                <a href="#/articles/{tour.article.id}">Read this article with its facts</a>
                <a href="#/records">Browse the records</a>
              </div>
            {/if}
          </div>
        </div>
      {/key}
    </div>

    <nav class="controls" aria-label="Steps">
      <button class="nav" onclick={() => to(n - 1)} disabled={n === 1} aria-label="Previous step">←</button>
      <ol class="progress">
        {#each STEPS as s, i}
          <li><button class:done={i + 1 < n} class:on={i + 1 === n} onclick={() => to(i + 1)} title={s.title} aria-label="Step {i + 1}: {s.title}"></button></li>
        {/each}
      </ol>
      <button class="nav" onclick={() => to(n + 1)} disabled={n === STEPS.length} aria-label="Next step">→</button>
      <span class="count mono" aria-live="polite">{n} of {STEPS.length}</span>
    </nav>
  {/if}
</div>

<style>
  .tour { height: 100%; display: flex; flex-direction: column; }
  .frame { flex: 1; min-height: 0; display: grid; overflow: hidden; }
  .slide {
    grid-area: 1 / 1; min-height: 0; overflow-y: auto;
    display: grid; grid-template-columns: minmax(280px, 0.8fr) minmax(0, 1.2fr); gap: 56px; align-items: center;
    padding: 40px 64px; max-width: 1360px; width: 100%; margin: 0 auto;
  }
  .words { align-self: center; }
  .count { position: absolute; right: 24px; color: var(--ink-3); font-size: 12px; }
  h1 { font: 600 36px/1.14 var(--serif); margin: 0 0 18px; letter-spacing: -0.014em; text-wrap: balance; }
  .body { font-size: 17px; line-height: 1.6; color: var(--ink-2); margin: 0 0 18px; max-width: 460px; }
  .aside { font-size: 14px; color: var(--ink-3); margin: 0; max-width: 460px; }
  .visual { display: flex; flex-direction: column; gap: 12px; min-width: 0; }

  .card {
    background: var(--card); border: 1px solid var(--rule); border-radius: 10px; padding: 16px 18px;
    animation: rise 520ms var(--ease) both;
  }
  .k { display: block; font-size: 12px; color: var(--ink-3); margin-bottom: 6px; }
  .muted { color: var(--ink-3); }
  .small { font-size: 13px; margin: 2px 0 0; }

  .doc { background: var(--card); border: 1px solid var(--rule); border-radius: 10px; padding: 22px 24px; animation: rise 520ms var(--ease) both; }
  .lic { display: inline-flex; align-items: center; gap: 8px; font: 12px var(--mono); color: var(--ink-2); margin-bottom: 12px; animation: fade-in 400ms var(--ease) 200ms both; }
  .lic::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--ok); }
  .doc-title { font: 600 21px/1.3 var(--serif); margin: 0 0 6px; }
  .doc-cite { font-size: 13px; color: var(--ink-3); margin: 0 0 18px; }
  .segs { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 9px; }
  .segs li { display: grid; grid-template-columns: 64px 1fr 150px; align-items: center; gap: 12px; animation: rise 420ms var(--ease) both; }
  .segs .mono { font-size: 11.5px; color: var(--ink-3); }
  .segs .bar { height: 6px; border-radius: 3px; background: var(--rule-strong); transform-origin: left; animation: grow 600ms var(--ease) both; animation-delay: inherit; }
  .segs .bar.row { background: var(--ink-3); }
  .segs .more { grid-template-columns: 64px; }
  .segs .lab { font-size: 12.5px; color: var(--ink-3); }
  .stats { margin: 18px 0 0; font-size: 13px; color: var(--ink-2); }

  .patient .big { font: 600 22px/1.3 var(--serif); margin: 4px 0 0; }
  blockquote {
    margin: 0; padding: 10px 14px; box-shadow: inset 2px 0 0 var(--hl-edge); background: var(--card); border-radius: 0 8px 8px 0;
    font: italic 16px/1.5 var(--serif); animation: rise 480ms var(--ease) both;
  }
  blockquote .mono { display: block; font: normal 11px var(--mono); color: var(--ink-3); margin-bottom: 2px; }
  .note { margin: 2px 0 0; font-size: 13.5px; color: var(--ink-3); }

  .seg-text { font: 16.5px/1.65 var(--serif); margin: 8px 0 0; }
  mark.draw { animation: wash 900ms var(--ease) 300ms both; }
  @keyframes wash { from { background-size: 0 100%; } to { background-size: 100% 100%; } }
  mark.draw {
    background: linear-gradient(var(--hl), var(--hl)) no-repeat left / 0 100%;
    box-shadow: none; border-bottom: 1.5px solid var(--hl-edge);
  }
  .fact-card { animation-delay: 700ms; box-shadow: inset 2px 0 0 var(--ink); }
  .fact-name { font-weight: 600; font-size: 16px; margin: 0 0 10px; }
  dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0; font-size: 13.5px; }
  dt { color: var(--ink-3); }
  dd { margin: 0; }

  .note-card p { margin: 0; font-size: 15.5px; line-height: 1.5; }
  .reasoning p { margin: 0; font: 13px/1.6 var(--mono); color: var(--ink-2); white-space: pre-wrap; min-height: 6em; }
  .caret { display: inline-block; width: 7px; height: 1em; vertical-align: -2px; background: var(--ink-3); margin-left: 2px; animation: blink 1s steps(2) infinite; }
  @keyframes blink { 50% { opacity: 0; } }

  .checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
  .checks li {
    display: flex; gap: 14px; padding: 14px 16px; border-radius: 10px; background: var(--card); border: 1px solid var(--rule);
    animation: rise 420ms var(--ease) both; animation-delay: calc(var(--i) * 260ms + 120ms);
  }
  .tick {
    flex: none; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; font-size: 13px;
    color: var(--card); background: var(--ok); animation: pop 360ms var(--ease) both; animation-delay: calc(var(--i) * 260ms + 380ms);
  }
  @keyframes pop { from { transform: scale(0.3); opacity: 0; } to { transform: none; opacity: 1; } }
  .checks b { display: block; font-weight: 600; margin-bottom: 2px; }
  .checks .q { display: block; font-size: 13.5px; color: var(--ink-2); }

  .cells { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin-bottom: 14px; }
  .cell { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--rule); background: var(--paper); animation: rise 420ms var(--ease) both; }
  .cell .mono.muted { font-size: 10.5px; }
  .cell .t { font-size: 12.5px; color: var(--ink-2); }
  .cell .v { font-size: 14px; }
  .big-spark { padding: 6px 6px 2px; }

  .events { list-style: none; margin: 0; padding: 0 0 0 22px; position: relative; display: flex; flex-direction: column; gap: 10px; }
  .events::before { content: ''; position: absolute; left: 4px; top: 8px; bottom: 8px; width: 1px; background: var(--rule-strong); }
  .events li { position: relative; display: flex; flex-direction: column; animation: rise 420ms var(--ease) both; font-size: 15px; line-height: 1.45; }
  .events li::before { content: ''; position: absolute; left: -22px; top: 6px; width: 9px; height: 9px; border-radius: 50%; background: var(--paper); border: 1.5px solid var(--ink-3); }
  .events .kind { font: 600 10.5px/1.6 var(--sans); letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-3); }

  .candidates { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .candidates li {
    display: grid; grid-template-columns: 80px 1fr auto; gap: 12px; align-items: baseline; padding: 9px 14px; border-radius: 8px;
    border: 1px solid var(--rule); background: var(--card); animation: rise 380ms var(--ease) both, dim 400ms var(--ease) var(--d) forwards;
  }
  .candidates li.chosen { animation: rise 380ms var(--ease) both, choose 500ms var(--ease) var(--d) forwards; }
  @keyframes dim { to { opacity: 0.45; } }
  @keyframes choose { to { border-color: var(--rule-strong); box-shadow: inset 2px 0 0 var(--ink); background: var(--sunk); } }
  .code { font-size: 13.5px; }
  .disp { font-size: 14px; }
  .score { font-size: 12px; color: var(--ink-3); }
  .decision { box-shadow: inset 2px 0 0 var(--ink); }
  .decision p { margin: 0; font-size: 14.5px; line-height: 1.55; }

  .fhir {
    margin: 0; padding: 18px 20px; border-radius: 10px; background: var(--card); border: 1px solid var(--rule);
    font: 12.5px/1.6 var(--mono); color: var(--ink-2); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 70vh; overflow-y: auto;
  }
  .fhir .line { animation: fade-in 260ms var(--ease) both; }
  .fhir :global(.k) { color: var(--ink); }
  .fhir :global(.s) { color: var(--ink-2); }
  .fhir :global(.n) { color: var(--ink); font-weight: 500; }

  .pass-card { display: flex; align-items: center; gap: 16px; }
  .seal { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; color: var(--card); background: var(--ok); font-size: 20px; animation: pop 420ms var(--ease) 200ms both; }
  .pass-card .fact-name { margin: 0; }
  .counts { list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .counts li { display: grid; grid-template-columns: 170px 1fr 48px; align-items: center; gap: 12px; font-size: 13.5px; animation: rise 360ms var(--ease) both; }
  .counts .bar { height: 6px; border-radius: 3px; background: var(--ink-3); width: var(--w); transform-origin: left; animation: grow 700ms var(--ease) both; animation-delay: inherit; }
  .counts .mono { text-align: right; color: var(--ink-2); }
  @keyframes grow { from { transform: scaleX(0); } to { transform: none; } }
  .end-links { display: flex; gap: 22px; margin-top: 14px; font-size: 14.5px; }

  .controls { position: relative; flex: none; display: flex; align-items: center; justify-content: center; gap: 18px; padding: 14px 20px 22px; }
  .nav { width: 38px; height: 38px; border-radius: 50%; border: 1px solid var(--rule); transition: border-color 160ms var(--ease), background-color 160ms var(--ease); }
  .nav:hover:not(:disabled) { border-color: var(--ink-3); background: var(--card); }
  .nav:disabled { opacity: 0.3; cursor: default; }
  .progress { list-style: none; display: flex; gap: 6px; margin: 0; padding: 0; }
  .progress button { display: block; width: 34px; height: 4px; border-radius: 2px; background: var(--rule-strong); transition: background-color 260ms var(--ease), width 260ms var(--ease); }
  .progress button.done { background: var(--ink-3); }
  .progress button.on { background: var(--ink); width: 52px; }
  .state { color: var(--ink-2); margin: 48px auto; }
  @media (max-width: 900px) {
    .slide { grid-template-columns: 1fr; gap: 24px; padding: 24px 18px; align-items: start; }
    h1 { font-size: 30px; }
    .count { display: none; }
    .progress button { width: 18px; }
    .progress button.on { width: 28px; }
  }
</style>
