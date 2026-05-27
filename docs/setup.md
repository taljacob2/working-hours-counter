# Working Hours Counter — Setup & CI/CD Guide

Complete guide for setting up the app from scratch: Supabase backend, GitHub Pages web deployment, and Android APK build pipeline.

---

## Overview

Two independent CI/CD pipelines run on every push to `master`:

| Pipeline | Workflow file | What it produces |
|---|---|---|
| **Web** | `.github/workflows/deploy.yml` | Live web app on GitHub Pages |
| **Android** | `.github/workflows/build-android.yml` | Downloadable APK artifact |

Both pipelines trigger automatically and run in parallel. A failure in one does not affect the other.

---

## Prerequisites

- A [GitHub](https://github.com) account with this repository forked/cloned
- A [Supabase](https://supabase.com) account (free tier is enough)
- **For Android signing only:** Java JDK installed locally to run `keytool`
  - Windows: install [Eclipse Temurin 17](https://adoptium.net/) — verify with `keytool -version`
  - macOS: comes with the JDK, or `brew install openjdk@17`

---

## Step 1 — Supabase Setup

### 1.1 Create a project

1. Sign in at [supabase.com](https://supabase.com) → **New project**
2. Choose a name (e.g. `working-hours`), set a database password, pick a region
3. Wait ~1 minute for provisioning

### 1.2 Run the database schema

Open **SQL Editor** in the left sidebar and run:

```sql
create table public.work_logs (
  id text primary key,
  platform text not null check (platform in ('office','home')),
  action text not null check (action in ('resume','pause')),
  timestamp timestamptz not null,
  date_key text not null,
  created_at timestamptz not null default now(),
  note text default ''
);
alter table public.work_logs enable row level security;
create policy "Auth users full access" on public.work_logs
  for all to authenticated using (true) with check (true);

create table public.work_settings (
  key text primary key,
  value text not null
);
alter table public.work_settings enable row level security;
create policy "Auth users full access" on public.work_settings
  for all to authenticated using (true) with check (true);

grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on table public.work_logs to anon, authenticated;
grant select, insert, update, delete on table public.work_settings to anon, authenticated;
```

### 1.3 Enable Email Auth

1. Go to **Authentication → Providers**
2. Confirm **Email** is enabled (it is by default)
3. Optional: disable **Confirm email** for a private single-user install (skips email verification)

### 1.4 Get your API credentials

Go to **Project Settings → API** and copy:

| Value | Where |
|---|---|
| **Project URL** | "Project URL" field |
| **Publishable key** | "Project API keys" → `anon public` row |

You will add these as GitHub Secrets in the next step.

---

## Step 2 — GitHub Repository & Pages Setup

### 2.1 Enable GitHub Pages

1. Go to your repo on GitHub → **Settings → Pages**
2. Under **Source**, select **GitHub Actions**
3. Save

### 2.2 Add Supabase credentials as GitHub Secrets

Go to **Settings → Secrets and variables → Actions → Secrets** and add:

| Secret name | Value |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase Project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Your Supabase anon/public key |

> These are compiled into the web app at build time. Alternatively, the app's built-in config screen lets users enter credentials manually via the browser (stored in `localStorage`) — useful if you prefer not to bake them into the build.

### 2.3 Trigger the first deploy

Push any commit to `master`. The **Deploy to GitHub Pages** workflow runs automatically. After ~1 minute the app is live at:

```
https://<your-username>.github.io/working-hours-counter/
```

---

## Step 3 — Android APK Setup

The Android workflow produces a downloadable APK on every push to `master`. Without any signing setup it builds a **debug APK** automatically. To get a **signed release APK** (recommended for a stable long-term install), complete the steps below.

For a deeper explanation of why signing matters and how it works in CI, see [android-signing.md](android-signing.md).

### 3.1 Generate a signing keystore (one-time)

Run this on your local machine:

```bash
keytool -genkey -v \
  -keystore release.keystore \
  -alias workinghours \
  -keyalg RSA -keysize 2048 -validity 10000
```

You will be prompted for a **keystore password** and a **key password** (they can be the same). The name/organisation fields can be anything.

> **Never commit `release.keystore` to the repository.** It is already listed in `.gitignore`. Keep a backup copy somewhere safe — losing it means you cannot sign future APK upgrades with the same identity.

### 3.2 Base64-encode the keystore for GitHub Secrets

**Windows (PowerShell):**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("release.keystore")) | clip
# The base64 string is now in your clipboard
```

**macOS:**
```bash
base64 -i release.keystore | pbcopy
```

**Linux:**
```bash
base64 release.keystore | xclip -sel clip
```

### 3.3 Add Android signing secrets to GitHub

Go to **Settings → Secrets and variables → Actions → Secrets** and add:

| Secret name | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | Paste the base64 string from step 3.2 |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password chosen in step 3.1 |
| `ANDROID_KEY_ALIAS` | `workinghours` |
| `ANDROID_KEY_PASSWORD` | Key password chosen in step 3.1 |

### 3.4 Download and sideload the APK

After the next push to `master`:

1. Go to **Actions → Build Android APK → (latest run) → Artifacts**
2. Download `working-hours-counter-apk.zip`
3. Extract `app-release.apk` and transfer it to your Android device
4. On Android: **Settings → Install unknown apps** → allow your file manager → open the APK and install

On future updates, install the new APK over the existing one — Android upgrades in place as long as the signing key matches.

---

## Secrets Reference

All GitHub Secrets used by both workflows:

| Secret | Workflow | Required | Description |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Both | Yes\* | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Both | Yes\* | Supabase anon key |
| `ANDROID_KEYSTORE_BASE64` | Android | No† | Signing keystore, base64-encoded |
| `ANDROID_KEYSTORE_PASSWORD` | Android | No† | Keystore password |
| `ANDROID_KEY_ALIAS` | Android | No† | Key alias (`workinghours`) |
| `ANDROID_KEY_PASSWORD` | Android | No† | Key password |

\* If omitted, the app shows a config screen on first load where credentials can be entered manually.  
† If any signing secret is missing, the workflow automatically falls back to a debug APK build.

---

## Local Development

```bash
npm install
npm run dev   # starts at http://localhost:5173
```

On first load the app shows a config screen — enter your Supabase URL and anon key. These are stored in `localStorage` and persist across sessions.

To test the Android build locally (requires [Android Studio](https://developer.android.com/studio)):

```bash
CAPACITOR_BUILD=true npm run build   # macOS/Linux
$env:CAPACITOR_BUILD="true"; npm run build  # Windows PowerShell

npx cap sync android
npx cap open android   # opens Android Studio — run on emulator or device from there
```

---

## How the Two Workflows Interact

```
push to master
├── deploy.yml                    (GitHub Pages)
│   ├── npm run build             (Vite base = /working-hours-counter/)
│   └── → https://<user>.github.io/working-hours-counter/
│
└── build-android.yml             (Android APK)
    ├── npm run build             (Vite base = /, via CAPACITOR_BUILD=true)
    ├── npx cap sync android
    ├── ./gradlew assembleRelease (signed) or assembleDebug (fallback)
    └── → Actions artifact: working-hours-counter-apk.zip
```

Both jobs compile the Svelte app independently with different Vite base paths. They do not share build artifacts.
