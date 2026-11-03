<script>
  import { tick } from 'svelte'
  import { focus } from '../lib/focus.svelte.js'
  import { runs } from '../lib/marks.js'
  import { find, findAll } from '../lib/find.svelte.js'
  import ArticleTable from './ArticleTable.svelte'

  let { blocks, scroller } = $props()

  // Evidence to mark, by segment: the pinned fact first, then the one under the pointer.
  const marks = $derived.by(() => {
    const out = new Map()
    for (const [target, kind] of [[focus.pinned, 'pin'], [focus.hover, 'hover']]) {
      if (!target) continue
      for (const e of target.evidence || []) {
        if (!out.has(e.seg)) out.set(e.seg, [])
        out.get(e.seg).push({ quote: e.quote, kind })
      }
    }
    return out
  })

  const markedSegments = $derived(new Set(marks.keys()))

  // Scroll the newly pinned evidence into view, vertically only: scrollIntoView would also scroll a wide
  // table back to its first marked cell (the row label), and each table scrolls itself sideways to its value.
  $effect(() => {
    const r = focus.reveal
    if (!r || !scroller) return
    tick().then(() => {
      const scope = scroller.querySelector(`[data-seg="${CSS.escape(r.seg || '')}"]`)
      const target = scope?.querySelector('mark.pin, .cell-pin') || scope
      if (!target) return
      const box = scroller.getBoundingClientRect()
      const t = target.getBoundingClientRect()
      scroller.scrollTo({ top: scroller.scrollTop + t.top - box.top - (box.height - Math.min(t.height, box.height)) / 2, behavior: 'smooth' })
    })
  })
</script>

{#snippet text(seg, value)}
  {@const found = find.query ? [{ ranges: findAll(value, find.query), kind: 'hit' }] : []}
  {#each runs(value, [...(marks.get(seg) || []), ...found]) as run}
    {#if run.kind}<mark class={run.kind}>{run.text}</mark>{:else}{run.text}{/if}
  {/each}
{/snippet}

<div class="reader">
  {#each blocks as block (block.id || block.text)}
    {#if block.type === 'heading'}
      <h2>{block.text}</h2>
    {:else if block.type === 'p'}
      <p class="seg" class:marked={markedSegments.has(block.id)} data-seg={block.id}>
        <span class="sid">{block.id}</span>{@render text(block.id, block.text)}
      </p>
    {:else if block.type === 'table'}
      <ArticleTable {block} />
    {:else if block.type === 'figure'}
      <figure class="fig" data-seg={block.captionId}>
        {#each block.images as src}
          <img {src} alt={block.caption} loading="lazy" />
        {/each}
        <figcaption><strong>{block.label}</strong> {@render text(block.captionId, block.caption)}</figcaption>
      </figure>
    {/if}
  {/each}
</div>

<style>
  .reader { font: 17px/1.75 var(--serif); color: var(--ink); }
  h2 { font: 600 21px/1.3 var(--serif); letter-spacing: -0.01em; margin: 44px 0 14px; }
  .seg { position: relative; margin: 0 0 18px; text-wrap: pretty; hyphens: auto; scroll-margin: 80px; }
  .sid {
    position: absolute; left: -46px; top: 0.55em; width: 38px; text-align: right;
    font: 10px/1 var(--mono); color: var(--ink-3); opacity: 0; user-select: none;
    transition: opacity 200ms var(--ease), color 200ms var(--ease);
  }
  .seg:hover .sid { opacity: 0.9; }
  .seg.marked .sid { opacity: 1; color: var(--ink-2); }
  figure { margin: 32px 0 34px; }
  figcaption { font: 14px/1.6 var(--sans); color: var(--ink-2); margin-top: 12px; text-wrap: pretty; }
  figcaption strong { color: var(--ink); font-weight: 600; margin-right: 6px; }
  .fig img { display: block; width: 100%; max-height: 460px; object-fit: contain; margin: 0 auto 4px; border-radius: 12px; background: var(--sunk); }
  mark { cursor: default; }
  :global(mark.hit) { background: var(--find); box-shadow: none; border-radius: 3px; }
  :global(mark.hit.current) { background: var(--find-now); box-shadow: 0 0 0 2px var(--find-now); }
  @media (max-width: 1200px) { .sid { display: none; } }
</style>
