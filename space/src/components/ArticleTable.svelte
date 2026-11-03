<script>
  // One article table drawn as printed (spans and multi-row headers), with the cells a fact or point names marked.
  import { tick } from 'svelte'
  import { focus } from '../lib/focus.svelte.js'
  import { runs } from '../lib/marks.js'
  import { find, findAll, hits } from '../lib/find.svelte.js'

  let { block } = $props()
  let scroller = $state()

  const ID = /^(.*)-(c|h)(\d+)$/
  const keyOf = (row) => row.key ?? row.id
  const drawn = $derived([
    ...block.head.map((r) => ({ key: r.key, cells: r.cells, head: true })),
    ...block.rows.map((r) => ({ key: keyOf(r), cells: r.cells, head: r.kind !== 'row' })),
  ])
  const segments = $derived(new Set([
    ...Object.keys(block.map), ...block.rows.map((r) => r.id), ...block.head.map((r) => r.id),
  ].filter(Boolean)))
  const width = $derived(Math.max(1, ...drawn.map((r) => r.cells.reduce((n, c) => n + (c.cs || 1), 0))))

  // Where the pipeline's cell ID is drawn, as "<row key>:<cell index>".
  function locate(id) {
    const m = ID.exec(id || '')
    const key = m && block.map[m[1]]?.[m[2] === 'h' ? 0 : 1]
    return key ? `${key}:${m[3]}` : null
  }

  // A segment's own drawn row: a body row, or the header row a headerless table's first row became.
  const ownKey = (seg) => (block.rows.some((r) => r.id === seg) ? seg : block.head.find((r) => r.id === seg)?.key)

  // Whether a quote names a cell. Quotes copy the segment text: cells joined by '|' (with span markers, which
  // the drawn cell has not), header and row on separate lines; short cells only count as a whole part.
  const norm = (s) => s.replace(/\s*\[rowspan=\d+,colspan=\d+\]/g, '').replace(/\s+/g, ' ').trim()
  function names(text, quote) {
    const c = norm(text)
    if (!c) return false
    if (/[|\n]/.test(quote)) return quote.split(/[|\n]/).some((part) => norm(part) === c)
    const q = norm(quote)
    return q === c || (c.length > 3 && q.includes(c)) || (q.length > 3 && c.includes(q))
  }

  // Marks from the fact under the pointer and the pinned one (pinned wins): cells by "<row key>:<index>",
  // and quoted runs in the caption and footnotes when no cell carries the quote.
  const marked = $derived.by(() => {
    const cells = new Map()
    const caption = []
    const notes = new Map()
    for (const [target, kind] of [[focus.hover, 'hover'], [focus.pinned, 'pin']]) {
      if (!target) continue
      for (const id of target.cells || []) {
        const at = locate(id)
        if (at) cells.set(at, kind)
      }
      for (const e of target.evidence || []) {
        if (block.notes.some((n) => n.id === e.seg)) {
          if (!notes.has(e.seg)) notes.set(e.seg, [])
          notes.get(e.seg).push({ quote: e.quote, color: kind, kind })
          continue
        }
        if (!segments.has(e.seg)) continue
        const quote = e.quote
        const own = ownKey(e.seg)
        let hit = false
        for (const row of drawn) {
          if (row.key !== own) continue
          row.cells.forEach((c, j) => { if (names(c.t, quote)) { cells.set(`${row.key}:${j}`, kind); hit = true } })
        }
        if (!hit) {
          for (const row of drawn) {
            if (!row.head || row.key === own) continue
            row.cells.forEach((c, j) => { if (names(c.t, quote)) { cells.set(`${row.key}:${j}`, kind); hit = true } })
          }
        }
        if (!hit) caption.push({ quote: e.quote, color: kind, kind })
      }
    }
    return { cells, caption, notes }
  })

  const mark = (key, j) => marked.cells.get(`${key}:${j}`)
  // Short cells (values, units, time labels) stay on one line; prose wraps.
  const short = (c) => c.t.length <= 14

  // The cell a pin is about: the value cell a measurement names; else, for a fact quoting a whole row, the pinned
  // cell holding the fact's value (under the column of its time when the value repeats); else the last pinned cell.
  const number = (t) => (String(t ?? '').replace(/,/g, '').match(/-?\d+(?:\.\d+)?/) || [])[0]
  function focusCell() {
    const direct = locate(focus.pinned?.cells?.[0])
    const named = direct && scroller.querySelector(`[data-at="${CSS.escape(direct)}"]`)
    if (named) return named
    const pinned = [...scroller.querySelectorAll('tbody .cell-pin')]
    const want = number(focus.pinned?.value)
    const same = want ? pinned.filter((c) => number(c.textContent) === want) : []
    const time = focus.pinned?.time?.trim()
    if (same.length > 1 && time) {
      const heads = [...scroller.querySelectorAll('thead th, tr.sub th')].filter((h) => h.textContent.trim() === time).map((h) => h.getBoundingClientRect())
      const under = same.find((c) => {
        const b = c.getBoundingClientRect()
        const x = (b.left + b.right) / 2
        return heads.some((a) => x >= a.left && x <= a.right)
      })
      if (under) return under
    }
    return same[0] || pinned.at(-1) || null
  }

  // The reader scrolls the pinned row into view vertically; a wide table brings that cell into view sideways.
  $effect(() => {
    const r = focus.reveal
    if (!r || !scroller) return
    tick().then(() => {
      const cell = focusCell()
      if (!cell) return
      const box = scroller.getBoundingClientRect()
      const c = cell.getBoundingClientRect()
      if (c.left < box.left || c.right > box.right) {
        scroller.scrollTo({ left: scroller.scrollLeft + c.left - box.left - (box.width - c.width) / 2, behavior: 'smooth' })
      }
    })
  })
</script>

{#snippet text(value, marks)}
  {@const found = find.query ? [{ ranges: findAll(value, find.query), kind: 'hit' }] : []}
  {#each runs(value, [...marks, ...found]) as run}
    {#if run.kind}<mark class={run.kind}>{run.text}</mark>{:else}{run.text}{/if}
  {/each}
{/snippet}

<figure class="table">
  <figcaption>
    {#if block.label}<strong>{block.label}</strong>{/if}
    {@render text(block.caption, marked.caption)}
  </figcaption>
  {#if block.head.length || block.rows.length}
    <div class="scroll" bind:this={scroller}>
      <table>
        {#if block.head.length}
          <thead>
            {#each block.head as row (row.key)}
              <tr data-seg={row.id}>
                {#each row.cells as c, j}
                  {@const m = mark(row.key, j)}
                  <th data-at="{row.key}:{j}" colspan={c.cs} rowspan={c.rs} class:span={c.cs > 1} class:short={short(c)} class:cell-pin={m === 'pin'} class:cell-hover={m === 'hover'} class:hit={hits(c.t, find.query)}>{c.t}</th>
                {/each}
              </tr>
            {/each}
          </thead>
        {/if}
        <tbody>
          {#each block.rows as row (keyOf(row))}
            {#if row.kind === 'group'}
              {@const m = mark(row.id, 0)}
              <tr class="group" data-seg={row.id}>
                <td colspan={Math.max(row.cells[0].cs || 1, width)} class:cell-pin={m === 'pin'} class:cell-hover={m === 'hover'} class:hit={hits(row.cells[0].t, find.query)}>{row.cells[0].t}</td>
              </tr>
            {:else if row.kind === 'sub'}
              <tr class="sub">
                {#each row.cells as c, j}
                  {@const m = mark(row.key, j)}
                  <th data-at="{row.key}:{j}" colspan={c.cs} rowspan={c.rs} class:span={c.cs > 1} class:short={short(c)} class:cell-pin={m === 'pin'} class:cell-hover={m === 'hover'} class:hit={hits(c.t, find.query)}>{c.t}</th>
                {/each}
              </tr>
            {:else}
              <tr data-seg={row.id}>
                {#each row.cells as c, j}
                  {@const m = mark(row.id, j)}
                  <td data-at="{row.id}:{j}" colspan={c.cs} rowspan={c.rs} class:short={short(c)} class:cell-pin={m === 'pin'} class:cell-hover={m === 'hover'} class:hit={hits(c.t, find.query)}>{c.t}</td>
                {/each}
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
  {#each block.notes as note (note.id)}
    <p class="note" data-seg={note.id}>{@render text(note.text, marked.notes.get(note.id) || [])}</p>
  {/each}
</figure>

<style>
  .table { margin: 1.7em 0 1.9em; }
  figcaption { font: 14px/1.5 var(--sans); color: var(--ink-2); margin: 0 0 10px; text-wrap: pretty; }
  figcaption strong { color: var(--ink); font-weight: 600; margin-right: 6px; }
  .scroll {
    overflow-x: auto; margin: 0 -10px; padding: 0 0 2px;
    border-top: 1px solid var(--rule-strong); border-bottom: 1px solid var(--rule-strong);
  }
  table {
    border-collapse: collapse; width: 100%; color: var(--ink);
    font: 13.5px/1.45 var(--sans); font-variant-numeric: tabular-nums;
  }
  th, td {
    text-align: left; vertical-align: top; padding: 7px 10px; max-width: 30em;
    transition: background-color 200ms var(--ease), box-shadow 200ms var(--ease);
  }
  .short { white-space: nowrap; }
  thead th { font-weight: 600; vertical-align: bottom; border-bottom: 1px solid var(--rule-strong); }
  thead th.span { text-align: center; border-bottom-color: var(--rule); }
  tbody td { border-top: 1px solid var(--rule); }
  tbody tr:first-child td { border-top: 0; }
  tr.sub th { font-weight: 600; border-top: 1px solid var(--rule-strong); border-bottom: 1px solid var(--rule-strong); }
  tr.sub th.span { text-align: center; }
  tr.group td {
    font: 600 11px/1.2 var(--sans); letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-3);
    padding-top: 16px; padding-bottom: 6px;
  }
  .cell-pin { background: var(--hl); box-shadow: inset 0 -1.5px 0 var(--hl-edge); }
  .cell-hover { background: var(--hl-soft); }
  .hit { background: var(--find); }
  .hit:global(.current) { background: var(--find-now); }
  .note { font: 13px/1.5 var(--sans); color: var(--ink-2); margin: 8px 0 0; }
</style>
