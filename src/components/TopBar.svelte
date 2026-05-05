<script>
  import { screen, user, theme } from '../stores/appStore.js'
  import { getSupabase } from '../lib/supabase.js'
  import { showToast } from '../stores/appStore.js'

  const tabs = [
    { id: 'main',     icon: '🏠', label: 'Main' },
    { id: 'logs',     icon: '📋', label: 'Logs' },
    { id: 'settings', icon: '⚙️', label: 'Settings' },
  ]

  function toggleTheme() {
    theme.update(t => {
      const next = t === 'light' ? 'dark' : 'light'
      localStorage.setItem('whl_theme', next)
      document.documentElement.setAttribute('data-theme', next)
      return next
    })
  }

  async function signOut() {
    const sb = getSupabase()
    await sb.auth.signOut()
    screen.set('signin')
    showToast('Signed out', 'info')
  }
</script>

<header class="topbar">
  <div class="topbar__brand">
    <span class="topbar__logo">⏱</span>
    <span class="topbar__name">Work Hours</span>
  </div>

  <nav class="topbar__nav">
    {#each tabs as tab}
      <button
        class="tab-btn"
        class:active={$screen === tab.id}
        on:click={() => screen.set(tab.id)}
      >
        <span class="tab-icon">{tab.icon}</span>
        <span class="tab-label">{tab.label}</span>
      </button>
    {/each}
  </nav>

  <div class="topbar__actions">
    <span class="topbar__email">{$user?.email ?? ''}</span>
    <button class="icon-btn" on:click={toggleTheme} title="Toggle dark mode" aria-label="Toggle dark mode">
      {$theme === 'dark' ? '☀️' : '🌙'}
    </button>
    <button class="icon-btn" on:click={signOut} title="Sign out" aria-label="Sign out">
      🚪
    </button>
  </div>
</header>

<style>
  .topbar {
    position: sticky; top: 0; z-index: 100;
    display: flex; align-items: center; gap: 1rem;
    padding: 0 1.5rem;
    height: 56px;
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
    box-shadow: var(--shadow-sm);
  }
  .topbar__brand { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }
  .topbar__logo { font-size: 1.25rem; }
  .topbar__name { font-weight: 700; font-size: 1rem; color: var(--color-primary); }
  .topbar__nav { display: flex; gap: 0.25rem; flex: 1; justify-content: center; }
  .tab-btn {
    display: flex; align-items: center; gap: 0.375rem;
    padding: 0.375rem 1rem;
    border-radius: var(--radius-sm);
    font-size: 0.875rem; font-weight: 500;
    color: var(--color-text-muted);
    transition: background var(--transition), color var(--transition);
    min-height: 36px;
  }
  .tab-icon { font-size: 1.1em; }
  .tab-btn:hover { background: var(--color-surface-2); color: var(--color-text); }
  .tab-btn.active { background: var(--color-primary-subtle); color: var(--color-primary); font-weight: 600; }
  .topbar__actions { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }
  .topbar__email { font-size: 0.8rem; color: var(--color-text-muted); max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .icon-btn { width: 36px; height: 36px; border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; font-size: 1.1rem; transition: background var(--transition); }
  .icon-btn:hover { background: var(--color-surface-2); }
  @media (max-width: 600px) {
    .topbar { padding: 0 0.5rem; justify-content: space-between; }
    .topbar__name { display: none; }
    .topbar__email { display: none; }
    .topbar__nav { 
      position: fixed; bottom: 0; left: 0; right: 0;
      background: var(--color-surface);
      border-top: 1px solid var(--color-border);
      padding: 0.375rem; padding-bottom: calc(0.375rem + env(safe-area-inset-bottom));
      justify-content: space-around;
      box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
      z-index: 1000;
    }
    .tab-btn { 
      flex-direction: column; gap: 0.125rem; justify-content: center;
      padding: 0.25rem 0.5rem; font-size: 0.7rem; 
      min-height: 48px; border-radius: var(--radius-md); 
      flex: 1; max-width: 30%;
    }
    .tab-icon { font-size: 1.25rem; }
    .topbar__actions { gap: 0.125rem; }
    .icon-btn { width: 32px; height: 32px; font-size: 1rem; }
  }
</style>
