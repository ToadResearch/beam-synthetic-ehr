<script>
  import { slide } from 'svelte/transition'
  import { focus } from '../lib/focus.svelte.js'
  import { humanize, segmentSpan } from '../lib/sections.js'
  import { describe } from '../lib/facts.js'

  // Clicking the row finds the fact's words in the article; the chevron opens what the model said about it.
  // compact: one of several facts folded under a shared name, so the row leads with its value.
  // implied: the sub-group the row sits in, whose name already says what a flag would.
  let { fact, section, label, implied = null, compact = false, open = false, selected = false, onselect, ontoggle, onquote } = $props()

  const shownAs = $derived(describe(fact, section, label))
  const ASSERTION = { absent: 'absent', possible: 'possible', hypothetical: 'hypothetical', conditional: 'conditional', historical: 'history' }
  const IMPLIED = { 'Ruled out': 'absent', Absent: 'absent', Possible: 'possible', History: 'history' }
  const flags = $derived([
    fact.assertion && fact.assertion !== 'present' ? ASSERTION[fact.assertion] || fact.assertion : null,
    fact.temporality === 'historical' && fact.assertion !== 'historical' ? 'history' : null,
  ].filter((f) => f && f !== IMPLIED[implied]))

  const escape = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
  const pattern = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const reasoning = $derived.by(() => {
    if (!fact.reasoning) return null
    const html = escape(fact.reasoning)
    const name = escape(fact.name || '')
    return name.length >= 3 ? html.replace(new RegExp(pattern(name), 'gi'), (m) => `<b>${m}</b>`) : html
  })
  const shown = (v) => (typeof v === 'string' && /^[a-z_]+$/.test(v) ? humanize(v).toLowerCase() : v)
  const pass = $derived(fact.task ? fact.task.replace(/^clinical_window_/, '').replace(/_/g, ' ') : null)
  const verdict = $derived.by(() => {
    if (!fact.attempts) return null
    const how = fact.attempts > 1 ? `after ${fact.attempts - 1} repair${fact.attempts > 2 ? 's' : ''}` : 'on the first attempt'
    return `${fact.status === 'partial' ? 'Kept from a partly accepted answer' : 'Accepted'} ${how}`
  })

  function enter() { focus.hover = { id: fact.id, evidence: fact.evidence } }
  function leave() { if (focus.hover?.id === fact.id) focus.hover = null }
</script>

<div class="fact" class:open class:selected class:compact onmouseenter={enter} onmouseleave={leave} role="group" data-fact={fact.id}>
  <div class="head">
    <button class="main" onclick={onselect} title="Show in the article">
      <span class="what">
        {#if compact}
          <span class="value lead" class:missing={!shownAs.value}>{shownAs.value || humanize(fact.fields.result_absent_reason || 'no value').toLowerCase()}</span>
        {:else}
          <span class="name">{shownAs.name}</span>
          {#if shownAs.value}<span class="value">{shownAs.value}</span>{/if}
        {/if}
        {#if shownAs.tag}<span class="flag">{shownAs.tag}</span>{/if}
        {#each flags as flag}<span class="flag">{flag}</span>{/each}
        {#if fact.time}<span class="time">{fact.time}</span>{/if}
      </span>
    </button>
    <button class="more" onclick={ontoggle} aria-expanded={open} aria-label={open ? 'Hide details' : 'Show details'}>
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="m6 3.5 4.5 4.5L6 12.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
    </button>
  </div>
  {#if open}
    <div class="detail" transition:slide={{ duration: 240 }}>
      <div class="sources">
        {#each fact.evidence as e}
          <button class="quote" onclick={() => onquote?.(e)} title="Show this passage in the article">
            <span class="q">{e.quote}</span>
            <span class="seg">{e.seg}</span>
          </button>
        {:else}
          <p class="nosource">No quoted source.</p>
        {/each}
      </div>
      {#if fact.why || fact.segmentWhy}
        <dl class="notes">
          {#if fact.why}<dt>Why Beam kept it</dt><dd>{fact.why}</dd>{/if}
          {#if fact.segmentWhy}<dt>Its note on {fact.evidence[0]?.seg}</dt><dd>{fact.segmentWhy}</dd>{/if}
        </dl>
      {/if}
      {#if Object.keys(fact.fields).length}
        <dl class="fields">
          {#each Object.entries(fact.fields) as [k, v]}<dt>{humanize(k)}</dt><dd>{shown(v)}</dd>{/each}
        </dl>
      {/if}
      {#if reasoning}
        <details class="reasoning">
          <summary>Reasoning excerpt</summary>
          <p>{@html reasoning}</p>
        </details>
      {/if}
      {#if pass || verdict}
        <p class="meta">
          {#if verdict}<span class="ok" class:partial={fact.status === 'partial'}>{verdict}</span>{/if}
          {#if pass}<span>{humanize(pass)} pass, reading {segmentSpan(fact.window)}</span>{/if}
        </p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .head { display: flex; align-items: stretch; gap: 2px; }
  .main {
    flex: 1; min-width: 0; display: flex; align-items: flex-start; gap: 12px;
    padding: 10px 12px; border-radius: 10px; text-align: left; transition: background-color 180ms var(--ease);
  }
  .main:hover { background: var(--sunk); }
  .selected .main { background: var(--hl-soft); }
  .what { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: 1px 10px; }
  .name { font-size: 15px; font-weight: 500; line-height: 1.45; color: var(--ink); }
  .value { font-size: 14px; line-height: 1.45; color: var(--ink-2); font-variant-numeric: tabular-nums; }
  .value.lead { font-size: 14.5px; color: var(--ink); font-weight: 500; }
  .value.lead.missing { font-size: 13.5px; font-style: italic; font-weight: 400; color: var(--ink-3); }
  .flag { font-size: 12.5px; font-style: italic; color: var(--ink-3); }
  .time { font-size: 13px; color: var(--ink-3); }
  .more {
    flex: none; width: 36px; display: grid; place-items: start center; padding-top: 13px; border-radius: 10px;
    color: var(--ink-3); transition: background-color 150ms var(--ease), color 150ms var(--ease);
  }
  .more:hover { background: var(--sunk); color: var(--ink); }
  .more svg { transition: transform 220ms var(--ease); }
  .open .more { color: var(--ink-2); }
  .open .more svg { transform: rotate(90deg); }
  .compact .main { padding: 7px 12px; }
  .compact .more { padding-top: 9px; width: 32px; }

  .detail { padding: 2px 48px 16px 12px; font-size: 13.5px; }
  .sources { display: flex; flex-direction: column; gap: 4px; margin: 2px 0; }
  .quote {
    display: flex; gap: 14px; justify-content: space-between; align-items: baseline; width: 100%; text-align: left;
    padding: 9px 12px 9px 14px; border-radius: 8px; background: var(--paper); box-shadow: inset 2px 0 0 var(--hl-edge);
    transition: background-color 160ms var(--ease);
  }
  .quote:hover { background: var(--hl-soft); }
  .q { font: italic 15.5px/1.55 var(--serif); color: var(--ink); }
  .seg { flex: none; font: 11px var(--mono); color: var(--ink-3); }
  .nosource { color: var(--ink-3); margin: 6px 0; }
  .notes, .fields { display: grid; grid-template-columns: minmax(110px, 32%) minmax(0, 1fr); gap: 5px 16px; margin: 14px 0 0; }
  dt { color: var(--ink-3); font-size: 13px; padding-top: 1px; }
  dd { margin: 0; color: var(--ink-2); line-height: 1.5; overflow-wrap: anywhere; }
  .notes dd { color: var(--ink); }
  .fields { padding-top: 12px; border-top: 1px solid var(--rule); }
  .reasoning { margin-top: 14px; }
  .reasoning summary {
    cursor: pointer; font-size: 13px; color: var(--ink-2); list-style: none; display: inline-flex; align-items: center; gap: 8px;
    transition: color 160ms var(--ease);
  }
  .reasoning summary:hover { color: var(--ink); }
  .reasoning summary::before { content: ''; width: 5px; height: 5px; border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor; transform: rotate(-45deg); transition: transform 200ms var(--ease); }
  .reasoning[open] summary::before { transform: rotate(45deg); }
  .reasoning summary::-webkit-details-marker { display: none; }
  .reasoning p {
    margin: 10px 0 0; padding: 12px 14px; border-radius: 10px; background: var(--paper);
    font: 12px/1.6 var(--mono); color: var(--ink-2); white-space: pre-wrap; animation: fade-in 240ms var(--ease);
  }
  .reasoning :global(b) { color: var(--ink); font-weight: 600; background: var(--hl-soft); }
  .meta { display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 14px 0 0; font-size: 12px; color: var(--ink-3); }
  .ok { display: inline-flex; align-items: center; gap: 6px; color: var(--ink-2); }
  .ok::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--ok); }
  .ok.partial::before { background: var(--hl-edge); }
</style>
