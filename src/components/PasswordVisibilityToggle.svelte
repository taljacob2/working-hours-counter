<script>
  export let visible = false
</script>

<button type="button" class="password-toggle-btn" tabindex="-1"
  aria-label={visible ? 'Hide password' : 'Show password'} on:click>
  {#if visible}
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  {:else}
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  {/if}
</button>

<style>
  .password-toggle-btn {
    position: absolute; top: 50%; right: var(--space-2); transform: translateY(-50%);
    display: flex; align-items: center; justify-content: center;
    width: 1.75rem; height: 1.75rem;
    border-radius: var(--radius-sm);
    color: var(--color-text-muted);
  }
  .password-toggle-btn:hover { background: var(--color-surface-2); color: var(--color-text); }
  .password-toggle-btn svg { width: 18px; height: 18px; }
</style>
