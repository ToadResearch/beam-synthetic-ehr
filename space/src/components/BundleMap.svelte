<script>
  // What a bundle is, drawn: one Patient, and every other resource pointing at it.
  import { TYPE_INFO, title } from '../lib/fhir.js'

  let { groups, onpick } = $props()

  const patient = $derived(groups.find((g) => g.type === 'Patient')?.items[0] || null)
  const clinical = $derived(groups.filter((g) => !g.internal))
  const internal = $derived(groups.filter((g) => g.internal && g.type !== 'Patient'))
  const most = $derived(Math.max(1, ...clinical.map((g) => g.items.length)))
</script>

<figure class="map">
  <div class="patient">
    <span class="label">Patient</span>
    <span class="pname">{patient ? title(patient) : 'No Patient resource'}</span>
    <span class="pnote">{TYPE_INFO.Patient}</span>
  </div>
  <ol class="types">
    {#each clinical as g, i (g.type)}
      <li style="--d: {i * 45}ms">
        <button onclick={() => onpick?.(g.type)}>
          <span class="edge" aria-hidden="true"></span>
          <span class="tname mono">{g.type}</span>
          <span class="count"><span class="bar" style="width: {Math.max(3, (g.items.length / most) * 100)}%"></span><span class="n mono">{g.items.length}</span></span>
          <span class="tinfo">{TYPE_INFO[g.type] || ''}</span>
        </button>
      </li>
    {/each}
  </ol>
  {#if internal.length}
    <p class="about">
      <span class="label">About the record</span>
      {#each internal as g, i (g.type)}
        <button class="mono" onclick={() => onpick?.(g.type)} title={TYPE_INFO[g.type]}>{g.type}{g.items.length > 1 ? ` ×${g.items.length}` : ''}</button>{i < internal.length - 1 ? ', ' : ':'}
      {/each}
      <span class="muted">who compiled it, from what, with the extraction packet attached.</span>
    </p>
  {/if}
</figure>

<style>
  .map {
    margin: 0; display: grid; grid-template-columns: 220px minmax(0, 1fr); column-gap: 0;
    padding: 22px 24px 18px; border: 1px solid var(--rule); border-radius: 12px; background: var(--card);
  }
  .patient {
    align-self: start; position: sticky; top: 16px; display: flex; flex-direction: column; gap: 6px;
    padding: 14px 16px; border-radius: 10px; border: 1px solid var(--rule-strong); background: var(--paper);
  }
  .pname { font: 500 16px/1.3 var(--serif); }
  .pnote { font-size: 12.5px; line-height: 1.45; color: var(--ink-3); }
  .types { list-style: none; margin: 0; padding: 4px 0 0; position: relative; }
  .types::before { content: ''; position: absolute; left: 0; top: 0; bottom: 22px; width: 1px; background: var(--rule-strong); }
  li { animation: rise 420ms var(--ease) both; animation-delay: var(--d); }
  li button {
    position: relative; width: 100%; display: grid; grid-template-columns: 72px minmax(0, 1fr) 170px; grid-template-rows: auto auto;
    align-items: baseline; column-gap: 16px; row-gap: 1px; padding: 8px 12px 9px 0; text-align: left; border-radius: 8px;
    transition: background-color 160ms var(--ease);
  }
  li button:hover { background: var(--sunk); }
  .edge { position: relative; grid-row: 1 / 3; align-self: center; height: 1px; background: var(--rule-strong); }
  .edge::after { content: ''; position: absolute; left: -3px; top: -3px; width: 7px; height: 7px; border-radius: 50%; background: var(--card); border: 1px solid var(--rule-strong); }
  .tname { font-size: 13px; color: var(--ink); }
  .count { grid-column: 3; grid-row: 1 / 3; align-self: center; display: flex; align-items: center; gap: 8px; }
  .bar { height: 6px; border-radius: 3px; background: var(--ink-3); opacity: 0.55; transform-origin: left; animation: grow 700ms var(--ease) both; animation-delay: calc(var(--d) + 120ms); }
  @keyframes grow { from { transform: scaleX(0); } to { transform: none; } }
  .n { font-size: 12.5px; color: var(--ink-2); }
  .tname { grid-column: 2; }
  .tinfo { grid-column: 2; font-size: 13px; line-height: 1.45; color: var(--ink-3); }
  .about { grid-column: 1 / -1; margin: 16px 0 0; padding-top: 14px; border-top: 1px solid var(--rule); font-size: 13px; color: var(--ink-2); line-height: 1.6; }
  .about .label { margin-right: 10px; }
  .about button { font-size: 12.5px; color: var(--ink); text-decoration: underline; text-decoration-color: var(--rule-strong); text-underline-offset: 3px; }
  .about button:hover { text-decoration-color: currentColor; }
  @media (max-width: 1100px) {
    li button { grid-template-columns: 48px minmax(0, 1fr) 110px; }
  }
  @media (max-width: 720px) {
    .map { grid-template-columns: minmax(0, 1fr); padding: 16px; }
    .patient { position: static; margin-bottom: 14px; }
    li button { grid-template-columns: 24px minmax(0, 1fr) 76px; column-gap: 10px; }
  }
</style>
