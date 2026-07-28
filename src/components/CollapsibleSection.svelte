<script>
  export let title = ''
  export let icon = ''
  export let open = false
</script>

<section class="collapsible">
  <button type="button" class="collapsible-header" on:click={() => open = !open} aria-expanded={open}>
    <span class="collapsible-title">
      {#if icon}<span class="collapsible-icon">{icon}</span>{/if}
      {title}
    </span>
    <span class="collapsible-chevron" class:open>▾</span>
  </button>
  {#if open}
    <div class="collapsible-body">
      <slot />
    </div>
  {/if}
</section>

<style>
  .collapsible {
    background: var(--color-surface);
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    box-shadow: var(--shadow-sm);
    overflow: hidden;
  }
  /* Adjacent-sibling spacing lives in the global stylesheet (app.css) —
     Svelte's scoped CSS can't apply a "+" combinator across separate
     component instances. */

  .collapsible-header {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    background: none;
    border: none;
    padding: var(--space-4) var(--space-5);
    cursor: pointer;
    font: inherit;
    color: var(--color-text);
    text-align: inherit;
  }

  .collapsible-title {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1rem;
    font-weight: 600;
  }

  .collapsible-icon { font-size: 1.15rem; }

  .collapsible-chevron {
    font-size: 0.85rem;
    color: var(--color-text-muted);
    transition: transform 0.2s ease;
    flex-shrink: 0;
  }
  .collapsible-chevron.open { transform: rotate(180deg); }

  .collapsible-body {
    padding: 0 var(--space-5) var(--space-5);
    border-top: 1px solid var(--color-border);
    padding-top: var(--space-4);
  }
</style>
