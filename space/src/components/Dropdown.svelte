<script>
  // A select that looks like a field and drops a list of options, with group headings and counts.
  // options: [{ value, label, count?, group?, indent? }]; group rows are headings, not choices.
  import { tick } from 'svelte'

  let { value = $bindable(''), options, label } = $props()

  let open = $state(false)
  let active = $state(-1)
  let trigger = $state()
  let list = $state()
  let pos = $state({ top: 0, left: 0, width: 0 })

  const current = $derived(options.find((o) => !o.group && o.value === value))
  const choices = $derived(options.map((o, i) => (o.group ? -1 : i)).filter((i) => i >= 0))

  // The list sits above the page (fixed), placed under its field, so no panel clips it or scrolls to show it.
  function place() {
    const r = trigger.getBoundingClientRect()
    const width = Math.max(r.width, 230)
    pos = { top: r.bottom + 6, left: Math.max(8, Math.min(r.left, innerWidth - width - 8)), width }
  }
  // Keep the active option visible by scrolling the list itself, never its ancestors.
  function keepVisible() {
    const el = list?.querySelector('.active')
    if (!el) return
    if (el.offsetTop < list.scrollTop) list.scrollTop = el.offsetTop - 4
    else if (el.offsetTop + el.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = el.offsetTop + el.offsetHeight - list.clientHeight + 4
  }
  async function toggle() {
    if (!open) place()
    open = !open
    if (!open) return
    active = options.findIndex((o) => !o.group && o.value === value)
    await tick()
    list?.focus({ preventScroll: true })
    keepVisible()
  }
  function choose(o) {
    if (o.group) return
    value = o.value
    open = false
    trigger?.focus({ preventScroll: true })
  }
  function key(e) {
    if (e.key === 'Escape') { e.preventDefault(); open = false; trigger?.focus({ preventScroll: true }); return }
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (active >= 0) choose(options[active]); return }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const at = choices.indexOf(active)
      active = choices[Math.min(choices.length - 1, Math.max(0, at + (e.key === 'ArrowDown' ? 1 : -1)))]
      tick().then(keepVisible)
    }
  }
  function outside(e) {
    if (open && !trigger?.contains(e.target) && !list?.contains(e.target)) open = false
  }
</script>

<svelte:window onpointerdown={outside} onresize={() => (open = false)} />

<div class="dd">
  <button class="dd-trigger" bind:this={trigger} aria-haspopup="listbox" aria-expanded={open} aria-label={label} onclick={toggle}>
    <span class="dd-value">{current?.label ?? label}</span>
  </button>
  {#if open}
    <ul class="dd-list" role="listbox" tabindex="-1" aria-label={label} bind:this={list} onkeydown={key}
      style="top: {pos.top}px; left: {pos.left}px; min-width: {pos.width}px">
      {#each options as o, i (o.group ? `g:${o.label}` : o.value)}
        <li role={o.group ? 'presentation' : 'option'} aria-selected={!o.group && o.value === value}
          class:group={o.group} class:indent={o.indent} class:active={i === active} class:selected={!o.group && o.value === value}
          onpointerenter={() => { if (!o.group) active = i }} onclick={() => choose(o)}>
          <span class="check" aria-hidden="true">
            {#if !o.group && o.value === value}<svg viewBox="0 0 16 16" width="13" height="13"><path d="m3.5 8.5 3 3 6-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg>{/if}
          </span>
          <span>{o.label}{#if o.count != null}<span class="n">({o.count})</span>{/if}</span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .dd { position: relative; min-width: 0; }
  .dd-trigger {
    width: 100%; min-width: 0; display: block; text-align: left; padding: 7px 28px 7px 10px;
    border: 1px solid var(--rule); border-radius: 10px; background: var(--card); font-size: 13px; color: var(--ink);
    background-image: linear-gradient(45deg, transparent 50%, var(--ink-3) 50%), linear-gradient(135deg, var(--ink-3) 50%, transparent 50%);
    background-position: right 15px top 50%, right 11px top 50%; background-size: 4px 4px; background-repeat: no-repeat;
    transition: border-color 150ms var(--ease), box-shadow 150ms var(--ease);
  }
  .dd-trigger:hover { border-color: var(--rule-strong); }
  .dd-trigger[aria-expanded='true'] { border-color: var(--rule-strong); box-shadow: 0 0 0 3px var(--sunk); }
  .dd-value { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dd-list {
    position: fixed; z-index: 60; max-height: min(420px, 60vh);
    margin: 0; padding: 4px; list-style: none; overflow: auto; overscroll-behavior: contain; outline: none;
    border: 1px solid var(--rule); border-radius: 12px; background: var(--card);
    box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.25), var(--shadow-card);
    font-size: 13.5px; transform-origin: top; animation: dd-in 140ms var(--ease);
  }
  @keyframes dd-in { from { opacity: 0; transform: translateY(-4px) scale(0.98); } }
  li { display: flex; align-items: center; gap: 6px; padding: 7px 10px 7px 6px; border-radius: 8px; color: var(--ink-2); white-space: nowrap; cursor: default; user-select: none; }
  li.active { background: var(--sunk); color: var(--ink); }
  li.selected { color: var(--ink); font-weight: 550; }
  li.group { font-weight: 600; color: var(--ink); padding-top: 10px; }
  li.indent { padding-left: 18px; }
  .check { display: inline-grid; place-items: center; width: 16px; flex: none; color: var(--hl-edge); }
  .n { margin-left: 5px; color: var(--ink-3); font-weight: 400; }
</style>
