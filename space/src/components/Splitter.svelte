<script>
  // The gutter between two sheets: drag (or use the arrow keys) to resize. On hover a line grows out from the
  // point where the pointer came in, and draws back to it on the way out.
  let { value = 50, onmove, onnudge, onend, label = 'Resize the panels' } = $props()

  let from = $state(50)
  let hovering = $state(false)
  let lit = $state(false)
  let dragging = $state(false)

  function enter(e) {
    hovering = true
    const r = e.currentTarget.getBoundingClientRect()
    from = Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100))
    // One frame later, so the line starts from the entry point; only if the pointer is still here.
    requestAnimationFrame(() => (lit = hovering))
  }
  function leave() { hovering = false; lit = false }
  function down(e) {
    if (e.button !== 0) return
    e.preventDefault()
    dragging = true
    e.currentTarget.setPointerCapture(e.pointerId)
    document.documentElement.classList.add('resizing')
  }
  function move(e) { if (dragging && e.buttons & 1) onmove?.(e.clientX) }
  function stop() {
    if (!dragging) return
    dragging = false
    document.documentElement.classList.remove('resizing')
    onend?.()
  }
  function key(e) {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault()
      onnudge?.(e.key === 'ArrowLeft' ? -2 : 2)
      onend?.()
    }
  }
</script>

<svelte:window onblur={stop} />

<!-- A focusable separator is the ARIA window-splitter widget: it takes the arrow keys. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<div class="splitter" class:lit={lit || dragging} role="separator" aria-orientation="vertical" aria-label={label} tabindex="0"
  aria-valuenow={Math.round(value)} aria-valuemin="30" aria-valuemax="75" title="Drag to resize"
  style="--from: {from}%"
  onpointerenter={enter} onpointerleave={leave}
  onpointerdown={down} onpointermove={move} onpointerup={stop} onpointercancel={stop} onlostpointercapture={stop}
  onkeydown={key}></div>

<style>
  .splitter { position: relative; cursor: col-resize; touch-action: none; outline: none; }
  .splitter::before {
    content: ''; position: absolute; left: calc(50% - 1px); width: 2px; border-radius: 2px;
    top: var(--from); bottom: calc(100% - var(--from)); background: var(--hl-edge); opacity: 0;
    transition: top 460ms var(--ease), bottom 460ms var(--ease), opacity 200ms var(--ease);
  }
  .splitter.lit::before, .splitter:focus-visible::before { top: 0; bottom: 0; opacity: 0.85; }
  :global(.resizing), :global(.resizing *) { cursor: col-resize !important; user-select: none; }
</style>
