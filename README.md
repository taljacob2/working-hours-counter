# Work Hours Logger

A personal work-hours tracking app built with **Svelte + Supabase**, deployed to **GitHub Pages**.

## Features

- **Two platforms** — Office and Home, each with Resume/Pause buttons
- **Idempotent logging** — duplicate consecutive presses are silently ignored
- **Live timers** — net worked time updates every second
- **Overtime tracking** — daily OT and cumulative monthly OT (only logged days count)
- **Calendar view** — per-day summaries with color-coded OT borders
- **Editable logs** — edit timestamp, platform, action, and note; or delete
- **CSV export** — filter by month and download
- **Dark / light mode** — auto-detected, manually toggleable
- **Supabase backend** — data persists across devices and browser restarts

---

## Setup

### 1. Create a Supabase project

1. Go to [supabase.com](https://supabase.com) and create a free project.
2. Open **SQL Editor** and run [`supabase-schema.sql`](./supabase-schema.sql).
3. Go to **Authentication → Users** and create a user account for yourself.
4. Go to **Project Settings → API** and copy:
   - **Project URL** — `https://xxxx.supabase.co`
   - **Anon (public) key** — `eyJ…`

### 2. Run locally

```bash
npm install
npm run dev
```

Open http://localhost:5173/working-hours-counter/ and follow the on-screen Config screen to paste your Supabase URL and anon key.

### 3. Deploy to GitHub Pages

```bash
npm run deploy
```

This builds the app and pushes the `dist/` folder to the `gh-pages` branch. Enable GitHub Pages in your repo settings to serve from that branch.

---

## Project structure

```
src/
├── lib/
│   ├── supabase.js      # Supabase client singleton
│   ├── timeUtils.js     # Duration math & formatting
│   └── exportUtils.js   # CSV download
├── stores/
│   └── appStore.js      # Svelte stores (state, toasts)
├── screens/
│   ├── ConfigScreen.svelte
│   ├── SignInScreen.svelte
│   ├── MainScreen.svelte
│   ├── LogsScreen.svelte
│   └── SettingsScreen.svelte
├── components/
│   ├── TopBar.svelte
│   ├── Toast.svelte
│   └── Spinner.svelte
├── App.svelte
├── main.js
└── app.css
```

---

## Security note

The Supabase **anon key** is stored in `localStorage` and is safe for this use case — it is publicly designed to be client-side, and all data access is gated by Row Level Security (RLS) requiring an authenticated session. Never use the **service role key** in the browser.
