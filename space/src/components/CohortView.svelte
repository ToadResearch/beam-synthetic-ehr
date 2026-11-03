<script>
  // Build a cohort from the dataset's patients, one filter at a time. Each step shows how many patients are still in,
  // so the cohort visibly narrows. Every filter reads the model's extraction: conditions with their ICD-10-CM codes,
  // age at presentation and documented sex.
  import { fade } from 'svelte/transition'
  import { href } from '../lib/router.svelte.js'
  import { loadIndex, loadRecord } from '../lib/data.js'
  import { plural } from '../lib/sections.js'
  import { layout } from '../lib/layout.svelte.js'
  import { ageOptions, sexOptions } from '../lib/filters.js'
  import Dropdown from './Dropdown.svelte'

  let index = $state(null)
  let error = $state(null)
  loadIndex().then((i) => (index = i)).catch((e) => (error = e.message))

  let conditions = $state([''])
  let age = $state('')
  let sex = $state('')
  let busy = $state(false)

  const all = $derived(index ? index.articles.flatMap((a) => a.patients.map((p) => ({ a, p }))) : [])

  // A condition step keeps patients with a condition whose name contains the words, or whose ICD-10-CM code starts with them.
  const hasCondition = (p, term) => {
    const t = term.trim().toLowerCase()
    return !t || p.conditions?.some((c) => c.name?.toLowerCase().includes(t) || c.code?.toLowerCase().startsWith(t))
  }

  // The steps in order, each with the patients it starts from and keeps.
  const run = $derived.by(() => {
    let left = all
    const before = {}
    const counts = {}
    const step = (key, keep) => { before[key] = left; left = left.filter(keep); counts[key] = left.length }
    conditions.forEach((term, i) => step(`c${i}`, ({ p }) => hasCondition(p, term)))
    step('age', ({ p }) => !age || p.age === age)
    step('sex', ({ p }) => !sex || p.sex === sex)
    return { before, counts, left }
  })
  const cohort = $derived(run.left)
  const resources = $derived(cohort.reduce((n, { p }) => n + p.resources, 0))
  const changed = $derived(conditions.some((c) => c.trim()) || age || sex)

  const tally = (key, keep) => (run.before[key] || []).filter(keep).length
  const ages = $derived(ageOptions((g) => tally('age', ({ p }) => p.age === g)))
  const sexes = $derived(sexOptions((x) => tally('sex', ({ p }) => p.sex === x)))

  const share = (n) => (all.length ? Math.max(n ? 2 : 0, (n / all.length) * 100) : 0)

  function reset() { conditions = ['']; age = ''; sex = '' }

  // The cohort as NDJSON: one FHIR R4 bundle per line.
  async function download() {
    busy = true
    try {
      const lines = []
      for (const { p } of cohort) lines.push(JSON.stringify((await loadRecord(p.bundle)).bundle))
      const blob = new Blob([`${lines.join('\n')}\n`], { type: 'application/x-ndjson' })
      const link = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `cohort-${cohort.length}-patients.ndjson` })
      link.click()
      setTimeout(() => URL.revokeObjectURL(link.href), 1000)
    } finally {
      busy = false
    }
  }
  // The conditions to list for a patient: the ones the condition steps matched first, then coded ones.
  const matches = (c) => conditions.some((term) => term.trim() && hasCondition({ conditions: [c] }, term))
  const listed = (p) => [...(p.conditions || [])].filter((c) => c.code || matches(c))
    .sort((x, y) => matches(y) - matches(x) || !!y.code - !!x.code)
</script>

{#snippet count(n)}
  <span class="meter" aria-hidden="true"><i style="width: {share(n)}%"></i></span>
  <span class="n">{n}</span>
{/snippet}

<div class="desk">
  <section class="sheet">
    <div class="sheet-bar">
      <a class="back" href={layout.record ? href('records', layout.record) : '#/records'}>
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M10 3.5 5.5 8l4.5 4.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
        <span>Patients</span>
      </a>
      <span class="sheet-label">Cohort</span>
      {#if index}<span class="summary">{cohort.length} of {all.length} patients · {resources.toLocaleString('en-US')} resources</span>{/if}
      <button class="get" onclick={download} disabled={!cohort.length || busy}>
        <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="M8 2.5v8M4.75 7.25 8 10.5l3.25-3.25M2.5 12.5h11" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
        {busy ? 'Collecting bundles…' : `Download ${plural(cohort.length, 'bundle')}`}
      </button>
    </div>
    <div class="sheet-scroll">
      {#if error}
        <p class="state">{error}</p>
      {:else if index}
        <div class="content" in:fade={{ duration: 200 }}>
          <header class="view-head">
            <h2>Build a cohort</h2>
            <p>Narrow the {all.length} patients one filter at a time. Each step shows how many are still in. The filters read Beam's extraction, and the download is one FHIR bundle per line (NDJSON).</p>
          </header>

          <ol class="steps">
            <li class="step first">
              <span class="what">All patients</span>
              <span class="control"></span>
              {@render count(all.length)}
            </li>
            {#each conditions as term, i (i)}
              <li class="step">
                <label class="what" for="cond-{i}">{i === 0 ? 'Condition or code' : 'And condition'}</label>
                <span class="control">
                  <input id="cond-{i}" class="search" type="search" placeholder="Type 2 diabetes, or E11" bind:value={conditions[i]} />
                  {#if conditions.length > 1}
                    <button class="remove" onclick={() => conditions.splice(i, 1)} aria-label="Remove this condition">
                      <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg>
                    </button>
                  {/if}
                </span>
                {@render count(run.counts[`c${i}`])}
              </li>
            {/each}
            <li class="add"><button onclick={() => conditions.push('')}>Add another condition</button></li>
            <li class="step">
              <span class="what">Age at presentation</span>
              <span class="control">{#if ages.length > 1}<Dropdown bind:value={age} options={ages} label="Any age" />{:else}<span class="empty">No ages left</span>{/if}</span>
              {@render count(run.counts.age)}
            </li>
            <li class="step">
              <span class="what">Sex</span>
              <span class="control">{#if sexes.length > 1}<Dropdown bind:value={sex} options={sexes} label="Any sex" />{:else}<span class="empty">No sexes left</span>{/if}</span>
              {@render count(run.counts.sex)}
            </li>
          </ol>
          {#if changed}<button class="reset" onclick={reset}>Clear all filters</button>{/if}

          <h3 class="result-head">{plural(cohort.length, 'patient')} in the cohort</h3>
          {#if cohort.length}
            <div class="table">
              <table>
                <thead>
                  <tr><th>Patient</th><th>Age</th><th>Sex</th><th>Conditions</th><th class="num">Resources</th></tr>
                </thead>
                <tbody>
                  {#each cohort as { a, p } (p.bundle)}
                    <tr>
                      <td class="who">
                        <a href={href('records', p.bundle)}>{p.label}</a>
                        <span class="from">{a.title}</span>
                      </td>
                      <td class="nowrap">{p.age || '—'}</td>
                      <td class="nowrap">{p.sex || '—'}</td>
                      <td class="codes">
                        {#each listed(p).slice(0, 3) as c}<span class="code" class:hit={matches(c)} title={c.name}>{#if c.code}<b>{c.code}</b>{/if}{c.name}</span>{/each}
                        {#if listed(p).length > 3}<span class="more">and {listed(p).length - 3} more</span>{/if}
                      </td>
                      <td class="num">{p.resources}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <p class="none">No patient passes every step. Loosen a filter above.</p>
          {/if}
        </div>
      {/if}
    </div>
  </section>
</div>

<style>
  .desk { height: 100%; overflow: hidden; padding: 12px; display: flex; justify-content: center; }
  .sheet { width: min(1120px, 100%); display: flex; flex-direction: column; min-height: 0; overflow: hidden; background: var(--card); border-radius: 14px; box-shadow: var(--shadow-sheet); }
  .sheet-bar { flex: none; display: flex; align-items: center; gap: 16px; height: 54px; padding: 0 12px 0 10px; border-bottom: 1px solid var(--rule); }
  .back {
    display: inline-flex; align-items: center; gap: 4px; height: 32px; padding: 0 10px 0 6px; border-radius: 8px;
    font-size: 13.5px; font-weight: 500; color: var(--ink-2); text-decoration: none; transition: background-color 150ms var(--ease), color 150ms var(--ease);
  }
  .back:hover { background: var(--sunk); color: var(--ink); }
  .sheet-label { font-size: 13px; font-weight: 600; color: var(--ink-3); }
  .summary { font-size: 13px; color: var(--ink-2); font-variant-numeric: tabular-nums; }
  .get {
    margin-left: auto; display: inline-flex; align-items: center; gap: 8px; height: 34px; padding: 0 14px; border-radius: 10px;
    border: 1px solid var(--rule); background: var(--card); font-size: 13.5px; font-weight: 500; color: var(--ink);
    transition: border-color 150ms var(--ease), background-color 150ms var(--ease);
  }
  .get:hover:not(:disabled) { border-color: var(--rule-strong); background: var(--sunk); }
  .get:disabled { opacity: 0.5; cursor: default; }
  .sheet-scroll { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; }
  .content { max-width: 920px; margin: 0 auto; padding: 32px 36px 96px; }
  .view-head h2 { margin: 0; font: 600 24px/1.25 var(--serif); letter-spacing: -0.01em; }
  .view-head p { margin: 8px 0 0; max-width: 680px; font-size: 14px; line-height: 1.6; color: var(--ink-3); }

  .steps { list-style: none; margin: 26px 0 0; padding: 0; border-top: 1px solid var(--rule); }
  .step {
    display: grid; grid-template-columns: 170px minmax(0, 340px) minmax(80px, 1fr) 44px; align-items: center; gap: 18px;
    padding: 12px 0; border-bottom: 1px solid var(--rule);
  }
  .what { font-size: 13.5px; font-weight: 500; color: var(--ink-2); }
  .first .what { color: var(--ink); }
  .control { position: relative; display: flex; align-items: center; gap: 6px; min-width: 0; }
  .control .search { flex: 1; height: 34px; }
  .remove { flex: none; width: 30px; height: 30px; display: grid; place-items: center; border-radius: 8px; color: var(--ink-3); transition: background-color 150ms var(--ease), color 150ms var(--ease); }
  .remove:hover { background: var(--sunk); color: var(--ink); }
  .control :global(.dd) { width: 100%; }
  .empty { font-size: 13px; color: var(--ink-3); }
  .meter { height: 6px; border-radius: 3px; background: var(--sunk); overflow: hidden; }
  .meter i { display: block; height: 100%; border-radius: 3px; background: var(--ink-3); transition: width 420ms var(--ease); }
  .n { text-align: right; font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--ink); }
  .add { padding: 8px 0; border-bottom: 1px solid var(--rule); }
  .add button, .reset { padding: 5px 8px; margin-left: -8px; border-radius: 8px; font-size: 13px; font-weight: 500; color: var(--ink-2); transition: background-color 150ms var(--ease), color 150ms var(--ease); }
  .add button:hover, .reset:hover { background: var(--sunk); color: var(--ink); }
  .reset { margin-top: 10px; }

  .result-head { margin: 36px 0 10px; font: 600 18px/1.3 var(--serif); }
  .table { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
  th { text-align: left; padding: 8px 14px 8px 0; font-size: 12px; font-weight: 600; color: var(--ink-3); border-bottom: 1px solid var(--rule-strong); white-space: nowrap; }
  td { padding: 10px 14px 10px 0; vertical-align: top; border-bottom: 1px solid var(--rule); color: var(--ink-2); }
  tbody tr { animation: fade-in 260ms var(--ease) both; }
  .num { text-align: right; font-variant-numeric: tabular-nums; padding-right: 0; }
  .who a { font-size: 14px; font-weight: 500; color: var(--ink); text-decoration: none; }
  .who a:hover { text-decoration: underline; text-decoration-color: var(--rule-strong); }
  .from { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 1; overflow: hidden; margin-top: 2px; font: 13px/1.4 var(--serif); color: var(--ink-3); }
  .codes { min-width: 200px; }
  .code { display: block; font-size: 13px; line-height: 1.5; }
  .code b { font: 500 12px var(--mono); color: var(--ink); margin-right: 6px; }
  .code.hit { color: var(--ink); font-weight: 500; }
  .nowrap { white-space: nowrap; }
  .more { display: block; font-size: 12px; color: var(--ink-3); }
  .none, .state { font-size: 14px; color: var(--ink-3); }
  @media (max-width: 760px) {
    .desk { padding: 8px; }
    .sheet-bar { padding-left: 6px; gap: 10px; }
    .summary { display: none; }
    .content { padding: 22px 18px 80px; }
    .step { grid-template-columns: minmax(0, 1fr) 40px; gap: 6px 12px; }
    .what { grid-column: 1 / -1; }
    .control { grid-column: 1 / -1; }
    .meter { grid-column: 1; }
  }
</style>
