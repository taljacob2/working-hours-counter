<script>
  import { toasts } from '../stores/appStore.js'
</script>

<div class="toast-container" aria-live="polite">
  {#each $toasts as t (t.id)}
    <div class="toast toast--{t.type}" role="alert">
      {#if t.type === 'error'}⚠️{:else if t.type === 'success'}✅{:else}ℹ️{/if}
      <span>{t.message}</span>
    </div>
  {/each}
</div>

<style>
  .toast-container {
    position: fixed;
    bottom: 1.5rem;
    right: 1.5rem;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    pointer-events: none;
  }
  .toast {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1rem;
    border-radius: var(--radius-sm);
    font-size: 0.875rem;
    font-weight: 500;
    box-shadow: var(--shadow-md);
    background: var(--color-surface);
    border: 1.5px solid var(--color-border);
    color: var(--color-text);
    animation: slideIn 0.2s ease, fadeOut 0.3s ease 2.5s forwards;
    max-width: 340px;
  }
  .toast--error  { border-color: var(--color-ot-neg);  background: var(--color-ot-neg-subtle); color: var(--color-ot-neg); }
  .toast--success{ border-color: var(--color-ot-pos);  background: var(--color-ot-pos-subtle); color: var(--color-ot-pos); }
  @keyframes slideIn {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes fadeOut {
    to { opacity: 0; transform: translateX(20px); }
  }
</style>
