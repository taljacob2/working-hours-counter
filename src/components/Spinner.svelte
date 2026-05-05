<script>
  import { loading } from '../stores/appStore.js'
</script>

{#if $loading}
  <div class="overlay" role="status" aria-label="Loading">
    <div class="spinner-wrap">
      <div class="spinner"></div>
      <p>Loading…</p>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.35);
    backdrop-filter: blur(4px);
    z-index: 8888;
    display: flex; align-items: center; justify-content: center;
  }
  .spinner-wrap {
    background: var(--color-surface);
    border-radius: var(--radius-md);
    padding: 2rem 2.5rem;
    display: flex; flex-direction: column; align-items: center; gap: 1rem;
    box-shadow: var(--shadow-lg);
  }
  .spinner {
    width: 40px; height: 40px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  p { font-size: 0.9rem; color: var(--color-text-muted); font-weight: 500; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
