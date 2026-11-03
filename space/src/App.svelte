<script>
  import { fade } from 'svelte/transition'
  import { route } from './lib/router.svelte.js'
  import { uploads } from './lib/uploads.svelte.js'
  import TopBar from './components/TopBar.svelte'
  import Home from './components/Home.svelte'
  import ArticleView from './components/ArticleView.svelte'
  import RecordsView from './components/RecordsView.svelte'
  import Walkthrough from './components/Walkthrough.svelte'
  import CohortView from './components/CohortView.svelte'
  import DropZone from './components/DropZone.svelte'
</script>

<TopBar />
<div class="stage">
  {#key route.view}
    <div class="view" in:fade={{ duration: 260 }}>
      {#if route.view === 'articles'}
        <ArticleView />
      {:else if route.view === 'records'}
        <RecordsView />
      {:else if route.view === 'cohort'}
        <CohortView />
      {:else if route.view === 'how'}
        <Walkthrough />
      {:else}
        <Home />
      {/if}
    </div>
  {/key}
</div>
<DropZone />

{#if uploads.error}
  <div class="toast" role="alert" transition:fade={{ duration: 160 }}>
    <span>{uploads.error}</span>
    <button onclick={() => (uploads.error = null)} aria-label="Dismiss">×</button>
  </div>
{/if}

<style>
  .stage { flex: 1; min-height: 0; position: relative; }
  .view { position: absolute; inset: 0; }
  .toast {
    position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%);
    display: flex; gap: 14px; align-items: center; max-width: min(560px, calc(100vw - 32px));
    padding: 10px 12px 10px 16px; border-radius: 10px;
    background: var(--ink); color: var(--card); font-size: 14px; z-index: 50; box-shadow: 0 16px 40px -20px var(--shade);
  }
  .toast button { font-size: 18px; line-height: 1; opacity: 0.7; padding: 2px 6px; }
</style>
