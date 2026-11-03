<script>
  import { fade, fly } from 'svelte/transition'
  import { href } from '../lib/router.svelte.js'
  import { ink } from '../lib/ink.js'
  import { sourceOf, title, when, value, codings, systemName, TYPE_INFO, fieldInfo, extensionInfo, extensionName, concept } from '../lib/fhir.js'
  import Json from './Json.svelte'

  let { resource, record, onclose } = $props()

  const src = $derived(sourceOf(resource))
  const isBundle = $derived(resource.resourceType === 'Bundle')
  let tab = $state('read')
  $effect(() => { if (isBundle) tab = 'json' })

  const article = $derived(record.article?.id && (!record.uploaded || record.linkable) ? record.article : null)
  const link = (seg, quote, cells) => href('articles', article.id, { p: record.patient?.id, seg, quote: quote?.slice(0, 120), cells: cells?.join(',') })

  // A readable value for any field: codes, references, quantities, short arrays.
  function show(key, v) {
    if (v == null) return ''
    if (typeof v !== 'object') return String(v)
    if (Array.isArray(v)) return v.map((x) => show(key, x)).filter(Boolean).join(' · ')
    if (v.reference) return v.reference.startsWith('urn:uuid:') ? `${patientRef(v.reference) ? 'Patient' : 'Resource'} ${v.reference.slice(9, 17)}…` : v.reference
    if (v.coding || v.text) return [v.text, ...(v.coding || []).map((c) => [c.code, c.display].filter(Boolean).join(' '))].filter(Boolean).join(' · ')
    if ('value' in v && ('unit' in v || 'code' in v)) return `${v.value} ${v.unit || v.code || ''}`.trim()
    if (v.text != null) return v.text
    if (v.low || v.high) return `${v.low?.value ?? ''}–${v.high?.value ?? ''} ${v.high?.unit || v.low?.unit || ''}`.trim()
    return null
  }
  const patientId = $derived((record.bundle?.entry || []).find((e) => e.resource?.resourceType === 'Patient')?.fullUrl || null)
  const patientRef = (ref) => ref && patientId && ref === patientId

  const SKIP = new Set(['resourceType', 'extension'])
  const fields = $derived(Object.entries(resource).filter(([k]) => !SKIP.has(k)).map(([k, v]) => {
    const text = k === 'text' ? (v?.div || '').replace(/<[^>]+>/g, '').trim() : k === 'meta' ? (v?.tag || []).map((t) => t.display || t.code).join(' · ') : show(k, v)
    return { key: k, text, info: fieldInfo(k), raw: text == null ? v : null }
  }))
  const extensions = $derived((resource.extension || []).map((x) => ({ name: extensionName(x.url), url: x.url, info: extensionInfo(x.url), value: x.valueString ?? x.valueBoolean ?? x.valueCode ?? null })))
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<div class="scrim" transition:fade={{ duration: 180 }} onclick={onclose} role="presentation"></div>
<aside class="drawer" transition:fly={{ x: 40, duration: 300, opacity: 0 }} aria-label="FHIR resource">
  <header>
    <h2>{isBundle ? record.patient?.label || 'Bundle' : title(resource)}</h2>
    <p class="sub">
      <span class="mono">{resource.resourceType}</span>
      {#if !isBundle}{#each [resource.resourceType === 'Observation' ? value(resource) : null, when(resource)].filter(Boolean) as part}<span>{part}</span>{/each}{/if}
      {#if resource.id}<span class="id mono">{resource.id.slice(0, 8)}</span>{/if}
    </p>
    {#if TYPE_INFO[resource.resourceType]}<p class="what">{TYPE_INFO[resource.resourceType]}</p>{/if}
    <button class="close" onclick={onclose} aria-label="Close">
      <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg>
    </button>
    <div class="tabs" role="tablist" use:ink>
      {#if !isBundle}<button role="tab" aria-selected={tab === 'read'} class:on={tab === 'read'} onclick={() => (tab = 'read')}>Explained</button>{/if}
      <button role="tab" aria-selected={tab === 'json'} class:on={tab === 'json'} onclick={() => (tab = 'json')}>JSON</button>
    </div>
  </header>
  <div class="body">
    {#key tab}
      <div in:fade={{ duration: 160 }}>
        {#if tab === 'read'}
          {#if src}
            <section>
              <h3 class="label">From the article</h3>
              {#if src.cells}
                <div class="cellcard">
                  <p class="ctable">{src.cells.table || 'Table'} · row and column it was read from</p>
                  <dl>
                    <dt>Row</dt><dd>{src.cells.row}</dd>
                    {#if src.cells.column}<dt>Column</dt><dd>{src.cells.column}</dd>{/if}
                    {#if src.cells.value}<dt>Cell</dt><dd class="mono">{src.cells.value}</dd>{/if}
                  </dl>
                  {#if article && src.cells.seg}<a class="go" href={link(src.cells.seg, null, src.cells.ids)}>Show the cell in the article</a>{/if}
                </div>
              {/if}
              {#each src.quotes as e}
                <blockquote>
                  <p>{e.quote}</p>
                  <footer>
                    <span class="mono">{e.seg}</span>
                    {#if article}<a href={link(e.seg, e.quote)}>Show in the article</a>{/if}
                  </footer>
                </blockquote>
              {/each}
            </section>
          {/if}

          {#if codings(resource.code).length}
            <section>
              <h3 class="label">Coding</h3>
              {#each codings(resource.code) as code}
                <p class="coding"><span class="mono">{code.code}</span><span>{code.display || ''}</span><span class="muted">{systemName(code.system)}</span></p>
              {/each}
              <p class="fine">Chosen by Beam from retrieved ICD-10-CM candidates, or left out when none matched. Not clinically reviewed.</p>
            </section>
          {/if}

          <section>
            <h3 class="label">Field by field</h3>
            <dl class="fields">
              {#each fields as f (f.key)}
                <div class="f">
                  <dt class="mono">{f.key}</dt>
                  <dd>
                    {#if f.raw != null}<span class="mono small">{JSON.stringify(f.raw)}</span>{:else}{f.text || '—'}{/if}
                    {#if f.info}<span class="info">{f.info}</span>{/if}
                  </dd>
                </div>
              {/each}
              {#each extensions as x (x.url)}
                <div class="f">
                  <dt class="mono">extension<br /><span class="xname">{x.name}</span></dt>
                  <dd>
                    {#if x.name === 'source-fact' && src}<span>The fact, as extracted ({src.quotes.length ? `${src.quotes.length} quote${src.quotes.length === 1 ? '' : 's'}` : 'table cells'}), shown above.</span>
                    {:else}<span class="mono small">{String(x.value).length > 160 ? `${String(x.value).slice(0, 160)}…` : x.value}</span>{/if}
                    {#if x.info}<span class="info">{x.info}</span>{/if}
                  </dd>
                </div>
              {/each}
            </dl>
          </section>
        {:else}
          <Json value={resource} />
        {/if}
      </div>
    {/key}
  </div>
</aside>

<style>
  .scrim { position: fixed; inset: var(--bar) 0 0 0; background: color-mix(in oklab, var(--paper) 40%, transparent); backdrop-filter: blur(1.5px); z-index: 30; }
  .drawer {
    position: fixed; top: var(--bar); right: 0; bottom: 0; width: min(620px, 100vw); z-index: 31;
    background: var(--card); border-left: 1px solid var(--rule); display: flex; flex-direction: column;
    box-shadow: -24px 0 60px -32px var(--shade);
  }
  header { position: relative; padding: 24px 28px 0; border-bottom: 1px solid var(--rule); }
  h2 { font: 600 23px/1.28 var(--serif); letter-spacing: -0.008em; margin: 0 44px 6px 0; text-wrap: balance; }
  .sub { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 14px; margin: 0; color: var(--ink-2); font-size: 14px; }
  .sub .mono { font-size: 12.5px; color: var(--ink); }
  .id { color: var(--ink-3); font-size: 11px !important; }
  .what { margin: 10px 0 0; font-size: 13px; color: var(--ink-3); line-height: 1.5; max-width: 520px; }
  .close { position: absolute; top: 16px; right: 16px; width: 32px; height: 32px; display: grid; place-items: center; border-radius: 8px; color: var(--ink-2); transition: background-color 160ms var(--ease); }
  .close:hover { background: var(--sunk); color: var(--ink); }
  .tabs { position: relative; display: flex; gap: 22px; margin-top: 18px; }
  .tabs button { position: relative; padding-bottom: 12px; color: var(--ink-3); font-size: 14px; transition: color 160ms var(--ease); }
  .tabs button:hover, .tabs button.on { color: var(--ink); }
  .tabs :global(.tab-ink) { bottom: 0; }
  .body { flex: 1; overflow-y: auto; padding: 6px 28px 80px; }
  section { margin-top: 22px; }
  section h3 { margin: 0 0 10px; }
  blockquote { margin: 0 0 10px; padding: 12px 16px; border-radius: 8px; background: var(--paper); box-shadow: inset 2px 0 0 var(--hl-edge); }
  blockquote p { margin: 0; font: italic 16.5px/1.55 var(--serif); }
  blockquote footer { display: flex; justify-content: space-between; gap: 12px; margin-top: 8px; font-size: 12.5px; color: var(--ink-3); }
  blockquote a, .go { color: var(--ink); font-size: 12.5px; }
  .cellcard { padding: 12px 16px; border-radius: 8px; background: var(--paper); box-shadow: inset 2px 0 0 var(--hl-edge); margin-bottom: 10px; }
  .ctable { margin: 0 0 8px; font-size: 12.5px; color: var(--ink-3); }
  .cellcard dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0 0 8px; font-size: 14px; }
  .cellcard dt { color: var(--ink-3); }
  .cellcard dd { margin: 0; }
  .coding { display: flex; gap: 12px; align-items: baseline; margin: 0 0 4px; font-size: 14px; }
  .coding .mono { font-size: 13.5px; padding: 1px 7px; border-radius: 5px; border: 1px solid var(--rule); }
  .fine { margin: 6px 0 0; font-size: 12.5px; color: var(--ink-3); }
  .fields { margin: 0; border-top: 1px solid var(--rule); }
  .f { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 16px; padding: 10px 0; border-bottom: 1px solid var(--rule); }
  .f dt { font-size: 12.5px; color: var(--ink); padding-top: 1px; overflow-wrap: anywhere; }
  .xname { color: var(--ink-3); }
  .f dd { margin: 0; font-size: 14px; color: var(--ink); overflow-wrap: anywhere; }
  .small { font-size: 12px; color: var(--ink-2); }
  .info { display: block; margin-top: 3px; font-size: 12.5px; color: var(--ink-3); line-height: 1.45; }
  @media (max-width: 640px) {
    header { padding: 20px 18px 0; }
    .body { padding: 4px 18px 60px; }
    .f { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  }
</style>
