<script>
  // A quiet line chart that draws itself once; points can be hovered and picked.
  let { points, active = -1, height = 48, onhover, onpick } = $props()

  let width = $state(280)
  const pad = 5
  const values = $derived(points.map((p) => p.value).filter((v) => v != null))
  const lo = $derived(Math.min(...values))
  const hi = $derived(Math.max(...values))
  const xy = $derived(points.map((p, i) => ({
    x: pad + (points.length === 1 ? (width - 2 * pad) / 2 : (i * (width - 2 * pad)) / (points.length - 1)),
    y: p.value == null ? null : pad + (hi === lo ? (height - 2 * pad) / 2 : (1 - (p.value - lo) / (hi - lo)) * (height - 2 * pad)),
  })))
  const path = $derived(xy.filter((p) => p.y != null).map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(''))
</script>

<div class="spark" bind:clientWidth={width}>
  <svg {width} {height} role="img" aria-label="Values in table order">
    <line class="base" x1={pad} x2={width - pad} y1={height - 0.5} y2={height - 0.5} />
    {#if active >= 0 && xy[active]}
      <line class="guide" x1={xy[active].x} x2={xy[active].x} y1="0" y2={height} />
    {/if}
    <path d={path} pathLength="1" />
    {#each xy as p, i}
      {#if p.y != null}
        <circle cx={p.x} cy={p.y} r={active === i ? 4 : 2.5} class:on={active === i} style="animation-delay: {240 + i * 50}ms" />
        <rect class="hit" x={p.x - 9} y="0" width="18" height={height} role="presentation"
          onmouseenter={() => onhover?.(i)} onmouseleave={() => onhover?.(-1)} onclick={() => onpick?.(i)} />
      {/if}
    {/each}
  </svg>
</div>

<style>
  .spark { width: 100%; }
  svg { display: block; overflow: visible; }
  .base { stroke: var(--rule); stroke-width: 1; }
  .guide { stroke: var(--rule-strong); stroke-width: 1; stroke-dasharray: 2 3; }
  path {
    fill: none; stroke: var(--ink-2); stroke-width: 1.4; stroke-linejoin: round; stroke-linecap: round;
    stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 900ms var(--ease) 60ms forwards;
  }
  circle {
    fill: var(--card); stroke: var(--ink-2); stroke-width: 1.4; opacity: 0; pointer-events: none;
    animation: fade-in 260ms var(--ease) forwards; transition: r 160ms var(--ease), fill 160ms var(--ease);
  }
  circle.on { fill: var(--hl-edge); stroke: var(--hl-edge); }
  .hit { fill: transparent; cursor: pointer; }
  @keyframes draw { to { stroke-dashoffset: 0; } }
</style>
