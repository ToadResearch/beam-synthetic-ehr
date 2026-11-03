<script>
  // Facts that share one name (a value read at several times, a dose that changed), folded into one row.
  import { slide } from 'svelte/transition'
  import { focus } from '../lib/focus.svelte.js'
  import { describe } from '../lib/facts.js'
  import FactRow from './FactRow.svelte'

  let { name, facts, section, label, implied = null, open = false, details = {}, selected = null, ontoggle, onselect, ondetails, onquote } = $props()

  const id = $derived(`group:${section}:${name}`)
  const values = $derived(facts.map((f) => describe(f, section, label).value).filter(Boolean))

  function enter() { focus.hover = { id, evidence: facts.flatMap((f) => f.evidence) } }
  function leave() { if (focus.hover?.id === id) focus.hover = null }
</script>

<div class="group" class:open>
  <button class="head" onclick={ontoggle} aria-expanded={open} onmouseenter={enter} onmouseleave={leave}>
    <span class="name">{name}</span>
    <span class="n">{facts.length}</span>
    <svg class="chev" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="m6 3.5 4.5 4.5L6 12.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
    {#if !open && values.length}<span class="values">{values.join('  ·  ')}</span>{/if}
  </button>
  {#if open}
    <div class="items" transition:slide={{ duration: 240 }}>
      {#each facts as f (f.id)}
        <FactRow fact={f} {section} {label} {implied} compact open={!!details[f.id]} selected={selected === f.id}
          onselect={() => onselect(f)} ontoggle={() => ondetails(f)} onquote={(e) => onquote(f, e)} />
      {/each}
    </div>
  {/if}
</div>

<style>
  .head {
    width: 100%; display: grid; grid-template-columns: auto auto 1fr; align-items: baseline; column-gap: 8px;
    padding: 10px 12px; border-radius: 10px; text-align: left; transition: background-color 160ms var(--ease);
  }
  .head:hover { background: var(--sunk); }
  .name { font-size: 15px; font-weight: 500; line-height: 1.45; color: var(--ink); }
  .n { font-size: 11.5px; font-variant-numeric: tabular-nums; color: var(--ink-2); padding: 0 7px; border-radius: 99px; background: var(--sunk); }
  .head:hover .n { background: var(--card); }
  .chev { justify-self: end; align-self: center; margin-right: -1px; color: var(--ink-3); transition: transform 220ms var(--ease); }
  .open .chev { transform: rotate(90deg); color: var(--ink-2); }
  .values {
    grid-column: 1 / -1; margin-top: 2px; font-size: 13.5px; color: var(--ink-3); font-variant-numeric: tabular-nums;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .items { margin: 2px 0 8px 14px; padding-left: 4px; border-left: 2px solid var(--rule); }
</style>
