<script>
  // Pretty-printed JSON with quiet syntax tones.
  let { value } = $props()

  const html = $derived.by(() => {
    const text = JSON.stringify(value, null, 2).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    return text.replace(/("(?:\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g, (m) => {
      const kind = m.startsWith('"') ? (m.trimEnd().endsWith(':') ? 'k' : 's') : /^(true|false)$/.test(m) ? 'b' : m === 'null' ? 'z' : 'n'
      return `<span class="${kind}">${m}</span>`
    })
  })
</script>

<pre class="json">{@html html}</pre>

<style>
  .json {
    margin: 16px 0 0; padding: 16px 18px; border-radius: 8px; background: var(--paper); border: 1px solid var(--rule);
    font: 12px/1.65 var(--mono); color: var(--ink-3); white-space: pre-wrap; overflow-wrap: anywhere;
  }
  .json :global(.k) { color: var(--ink); }
  .json :global(.s) { color: var(--ink-2); }
  .json :global(.n), .json :global(.b), .json :global(.z) { color: var(--ink); font-weight: 500; }
</style>
