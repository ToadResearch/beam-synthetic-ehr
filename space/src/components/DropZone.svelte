<script>
  import { fade } from 'svelte/transition'
  import { openFiles } from '../lib/uploads.svelte.js'

  let depth = $state(0)
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files')
</script>

<svelte:window
  ondragenter={(e) => { if (hasFiles(e)) { e.preventDefault(); depth++ } }}
  ondragover={(e) => { if (hasFiles(e)) e.preventDefault() }}
  ondragleave={() => { depth = Math.max(0, depth - 1) }}
  ondrop={(e) => { if (hasFiles(e)) { e.preventDefault(); depth = 0; openFiles(e.dataTransfer.files) } }}
/>

{#if depth > 0}
  <div class="drop" transition:fade={{ duration: 140 }}>
    <div class="card">
      <p class="title">Drop to open</p>
      <p>A FHIR R4 bundle or resources (JSON or NDJSON), a row of the dataset, or an extraction record with its source packet.</p>
      <p class="muted">Files stay in this tab.</p>
    </div>
  </div>
{/if}

<style>
  .drop {
    position: fixed; inset: 0; z-index: 60; display: grid; place-items: center;
    background: color-mix(in oklab, var(--paper) 80%, transparent);
    backdrop-filter: blur(3px);
  }
  .card {
    max-width: 440px; padding: 30px 32px; border-radius: 14px;
    border: 1.5px dashed var(--rule-strong); background: var(--card); box-shadow: 0 30px 60px -40px var(--shade);
  }
  .title { font: 600 24px/1.2 var(--serif); margin: 0 0 10px; }
  p { margin: 0 0 8px; color: var(--ink-2); }
</style>
