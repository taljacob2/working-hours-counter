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
2. Open **SQL Editor** and run the entire contents of [`supabase-schema.sql`](./supabase-schema.sql). *(This includes the table creations, RLS policies, and explicit `GRANT` permissions to prevent "permission denied" errors).*
3. Go to **Authentication → Users** and create a user account for yourself.
4. Go to **Project Settings → API** and copy:
   - **Project URL** — `https://xxxx.supabase.co`
   - **Anon (public) key** — `eyJ…`

### 2. (Optional) Let users sign in immediately, without email confirmation

By default Supabase requires new users to click a confirmation link in their
email before they can sign in — after signup they'll see "check your email
to confirm it, then sign in."

Some users don't want that extra step. This isn't controlled by this app's
code — email confirmation is a setting enforced by Supabase Auth on the
server, so it has to be turned off on the Supabase project itself:

1. In your Supabase project, go to **Authentication → Providers** (or
   **Authentication → Sign In / Providers** on newer dashboards).
2. Open the **Email** provider.
3. Turn **Confirm email** off, then save.

With this off, `supabase.auth.signUp()` returns an active session straight
away, and the app (see `signUp()` in
[`src/screens/SignInScreen.svelte`](./src/screens/SignInScreen.svelte))
already detects that automatically and takes the new user straight to the
main screen — no app changes or redeploy needed.

This is a project-wide setting: it applies to every user signing up on that
Supabase project, since Supabase doesn't offer a per-user opt-out. If you
want confirmation required for most users but skippable for a few, you'd
need a server-side component (e.g. a Supabase Edge Function using the
service-role key to force-confirm specific accounts) — outside the scope of
this static, backend-less app.

Separately, make sure **Authentication → Providers → Email → Allow new
users to sign up** is on (it's on by default for new projects) — this is
what lets the app's own "Create an account" form actually register anyone,
not just accounts you create manually from the dashboard.

### 3. Configure credentials (optional — recommended for local dev)

Instead of entering credentials in the browser Config screen every time, you can supply them via a `.env` file:

```bash
cp .env.template .env
# then open .env and fill in your values
```

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL (`https://xxxx.supabase.co`) |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Your Supabase anon/public key |

Vite automatically loads `.env` during `npm run dev` and `npm run build`. When these variables are present the app skips the Config screen entirely and the **Reconfigure** button is locked, so credentials cannot be overwritten at runtime.

> **Note:** `.env` is listed in `.gitignore` — your secrets will never be committed. The checked-in `.env.template` contains only placeholder values and serves as documentation.

### 4. Run locally

```bash
npm install
npm run dev
```

Open http://localhost:5173/working-hours-counter/ — if you filled in `.env` you will land directly on the sign-in screen.

### 5. Deploy to GitHub Pages

```bash
npm run deploy
```

This builds the app and pushes the `dist/` folder to the `gh-pages` branch. Enable GitHub Pages in your repo settings to serve from that branch.

---

## GitHub Actions secrets & variables

The workflows under `.github/workflows/` need these configured in **repo Settings → Secrets and variables → Actions**. Where a workflow reads `secrets.X || vars.X`, the value isn't sensitive (it's already public in the built app) and can go in either — Secret if you'd rather not have it visible in the Actions UI, Variable if you want to read it back later.

| Name | Kind | Used by | What it's for |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Secret or Variable | `deploy.yml`, `build-android.yml`, `build-ios.yml`, `notification-scheduler.yml` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Secret or Variable | `deploy.yml`, `build-android.yml`, `build-ios.yml` | Supabase anon/public key |
| `VAPID_PUBLIC_KEY` | Secret or Variable | `deploy.yml`, `build-android.yml`, `build-ios.yml`, `notification-scheduler.yml` | Web Push VAPID public key (`npx web-push generate-vapid-keys`) |
| `VAPID_PRIVATE_KEY` | Secret | `notification-scheduler.yml` | Web Push VAPID private key — never expose this one |
| `SUPABASE_SERVICE_ROLE_KEY` | Secret | `notification-scheduler.yml` | Bypasses RLS to send reminders across all users — Project Settings → API |
| `SUPABASE_ACCESS_TOKEN` | Secret | `deploy-edge-functions.yml`, `check-supabase-token.yml` | Personal access token used to deploy Edge Functions via the Supabase CLI — [dashboard → Account → Access Tokens](https://supabase.com/dashboard/account/tokens). Expires (1 year when last generated); `check-supabase-token.yml` opens a GitHub issue if it stops working |
| `SUPABASE_PROJECT_REF` | Variable | `deploy-edge-functions.yml`, `check-supabase-token.yml` | Your project ref, e.g. `jdxeuirbmpaeetisrolu` (visible in any Supabase URL for the project) |
| `NOTIF_TIMEZONE` | Variable (optional) | `notification-scheduler.yml` | IANA timezone for reminder scheduling, e.g. `Asia/Jerusalem` — defaults to `Asia/Jerusalem` if unset |
| `ANDROID_KEYSTORE_BASE64` / `ANDROID_KEYSTORE_PASSWORD` / `ANDROID_KEY_ALIAS` / `ANDROID_KEY_PASSWORD` | Secrets | `build-android.yml` | APK signing — only needed for a signed release build |

## Enabling OAuth sign-in (Google / GitHub)

Google and GitHub sign-in are feature-flagged in
[`src/lib/authProviders.js`](./src/lib/authProviders.js) — both `false` by
default, so a half-configured provider never shows a button that doesn't
work. Enabling one is three steps: register an OAuth app with the
provider, plug its credentials into Supabase, then flip the flag.

Both providers redirect back to the same Supabase callback URL:
`https://<your-project-ref>.supabase.co/auth/v1/callback` — find the exact
one under Supabase → Authentication → Providers → (Google or GitHub), it's
shown on that screen. Separately, add your app's real URL (and
`http://localhost:5173` for local testing) under Supabase →
**Authentication → URL Configuration → Redirect URLs**, or the redirect
back from the provider gets rejected regardless of correct credentials.

### GitHub

1. [github.com/settings/developers](https://github.com/settings/developers) → **OAuth Apps** → **New OAuth App**.
2. Homepage URL: your deployed app's URL. Authorization callback URL: the Supabase callback URL above.
3. Register, then copy the **Client ID** and generate + copy a **Client Secret**.
4. Supabase → **Authentication → Providers → GitHub** → enable → paste both → Save.
5. Flip `github: false` to `true` in `authProviders.js`, commit, deploy.

### Google

More involved — Google requires a consent screen and, to avoid an
"unverified app" warning, domain ownership proof.

1. [console.cloud.google.com](https://console.cloud.google.com/) → create or select a project.
2. **APIs & Services → OAuth consent screen**: User type **External**; fill in app name, support email, developer contact email, homepage URL, and — required — a **Privacy Policy URL**. This repo already ships [`public/privacy.html`](./public/privacy.html) and [`public/terms.html`](./public/terms.html) as static pages for exactly this (served at `/privacy.html` / `/terms.html`); use those. Set the **Authorized domain** to whatever your app is hosted under (e.g. `github.io`).
3. **Verify domain ownership** in [Google Search Console](https://search.google.com/search-console): add the site as a **URL-prefix** property (not Domain — you likely don't control DNS for a shared host like `github.io`), and use the **HTML tag** method. Google gives you a `<meta name="google-site-verification" ...>` tag — add it to [`index.html`](./index.html)'s `<head>` (already there; if you ever re-verify with a new project, swap in the new tag).
4. Click **Publish App** to move it from Testing to Production. For basic scopes only (email/profile/openid — all this app requests), that's usually enough; Google's full manual review is only triggered by sensitive/restricted scopes.
5. **APIs & Services → Credentials → Create Credentials → OAuth client ID**, type **Web application**. Authorized JavaScript origins: your app's origin. Authorized redirect URIs: the Supabase callback URL.
6. Copy the **Client ID** and **Client Secret** → Supabase → **Authentication → Providers → Google** → enable → paste both → Save.
7. Flip `google: false` to `true` in `authProviders.js`, commit, deploy.

Even with all of the above done, first-time sign-in may still show a mild
"unverified app" screen since this app was never submitted for Google's
full review (not required at this scope) — clicking through
**Advanced → Go to [app name] (unsafe)** works fine and is expected for
small apps.

### Letting an existing account link a second provider

Once a provider is enabled, a signed-in user can attach it to their
existing email/password account from **Settings → Account & Connection →
Linked sign-in methods**, rather than it creating a separate account. This
uses Supabase's identity-linking API, which needs **manual linking**
enabled — Supabase → Authentication settings (exact location varies by
dashboard version; look under **Providers** or a general **Settings**
page). If the in-app "Link" button errors with something like "manual
linking is disabled," that's the toggle to find.

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
