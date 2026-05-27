# Android Signing Reference

Details on APK signing — useful if you need to regenerate a keystore, understand the CI signing flow, or troubleshoot install issues.

---

## First-time setup: generate keystore and add GitHub Secrets

Do this once before your first release build. You need a local Java JDK for `keytool`.

### 1 — Install Java 21 JDK (Windows)

Open **PowerShell as Administrator** and run:

```powershell
winget install EclipseAdoptium.Temurin.21.JDK
```

After it finishes, **close the terminal and open a new one** so the PATH updates. Confirm it worked:

```powershell
keytool -version
# Expected output: keytool 21.0.x  (or similar)
```

> macOS: `brew install openjdk@21`  
> Linux: `sudo apt install openjdk-21-jdk`

### 2 — Generate the keystore

From the project root:

```powershell
cd "i:\Tal\Code\other\working-hours-counter"

keytool -genkey -v -keystore release.keystore -alias workinghours -keyalg RSA -keysize 2048 -validity 10000
```

Answer the prompts:

```
Enter keystore password:       <choose a strong password — remember it>
Re-enter new password:         <same password>
What is your first and last name?     Tal Jacob     (or anything)
What is your organizational unit?     [press Enter]
What is your name of your organization? [press Enter]
What is your City or Locality?        [press Enter]
What is your State or Province?       [press Enter]
What is your two-letter country code: IL            (or your country)
Is CN=..., C=IL correct?             yes
Enter key password for <workinghours>: [press Enter to use same as keystore password]
```

This creates `release.keystore` in the project folder. It is already in `.gitignore` — **never commit it**.  
Keep a backup in a password manager or encrypted storage.

### 3 — Base64-encode the keystore and copy to clipboard

**Windows (PowerShell):**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("i:\Tal\Code\other\working-hours-counter\release.keystore")) | Set-Clipboard
```

**macOS:**
```bash
base64 -i release.keystore | pbcopy
```

**Linux:**
```bash
base64 release.keystore | xclip -sel clip
```

### 4 — Add the 4 secrets to GitHub

Go to **Settings → Secrets and variables → Actions → Secrets** in your GitHub repo  
(direct link: `https://github.com/taljacob2/working-hours-counter/settings/secrets/actions`)

Click **New repository secret** and add all four:

| Secret name | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | Paste from clipboard (Step 3) |
| `ANDROID_KEYSTORE_PASSWORD` | The keystore password you chose |
| `ANDROID_KEY_ALIAS` | `workinghours` |
| `ANDROID_KEY_PASSWORD` | The key password (same as keystore if you pressed Enter) |

### 5 — Trigger a build

Merge `add-location-detection` into `master` (or push any commit to `master`). The **Build Android APK** workflow will run automatically, produce a signed release APK, and upload it as a downloadable artifact under **Actions → Build Android APK → Artifacts**.

---

## Debug vs Release APK

| | Debug | Release |
|---|---|---|
| Signing key | Auto-generated throwaway key | Your keystore (`release.keystore`) |
| Setup needed | None | Steps 3.1–3.3 in [setup.md](setup.md) |
| Stable identity across installs | No (key changes if environment changes) | Yes |
| Play Store distribution | No | Yes |
| Personal sideloading | Works | Works (preferred) |

The CI workflow builds a **release APK** when all four signing secrets are present, and falls back to **debug** if any are missing.

---

## How signing works in CI

The workflow passes signing credentials to Gradle via command-line properties instead of hardcoding them in `build.gradle`. This means the Android project files stay clean and signing is entirely controlled by GitHub Secrets:

```bash
./gradlew assembleRelease \
  -Pandroid.injected.signing.store.file=$(pwd)/app/release.keystore \
  -Pandroid.injected.signing.store.password=$KEYSTORE_PASSWORD \
  -Pandroid.injected.signing.key.alias=$KEY_ALIAS \
  -Pandroid.injected.signing.key.password=$KEY_PASSWORD
```

The keystore is decoded from `ANDROID_KEYSTORE_BASE64` at the start of the job, written to a temp file on the runner, and used only for that build. It is never persisted or accessible after the job ends.

---

## Re-encoding an existing keystore

If you already have a `release.keystore` and need to re-add it as a GitHub Secret (e.g. after rotating secrets or moving to a new repo):

**Windows (PowerShell):**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("release.keystore")) | clip
```

**macOS:**
```bash
base64 -i release.keystore | pbcopy
```

**Linux:**
```bash
base64 release.keystore | xclip -sel clip
```

Paste the result into `ANDROID_KEYSTORE_BASE64` in **Settings → Secrets and variables → Actions**.

---

## If you lose the keystore

Android ties APK upgrades to the signing key. If you lose `release.keystore`:

- You **cannot** upgrade an existing install silently — Android will reject the new APK
- Users must **uninstall** the old app and install fresh (all data stored in Supabase is safe)
- Generate a new keystore with the same `keytool` command in [setup.md](setup.md)
- Update all four `ANDROID_*` secrets with the new keystore's values

To avoid this: keep a backup of `release.keystore` in a password manager or encrypted storage.

---

## Sideloading step by step

1. Go to **Actions → Build Android APK → (latest run)**
2. Under **Artifacts**, download `working-hours-counter-apk`
3. Unzip — you'll find `app-release.apk` (or `app-debug.apk`)
4. Transfer to your Android device (USB cable, Google Drive, email, etc.)
5. Open the APK on the device
6. If Android blocks the install: **Settings → Apps → Special app access → Install unknown apps** → find your file manager or browser → enable **Allow from this source**
7. Tap **Install**

For subsequent updates, just install the new APK over the existing one without uninstalling first (as long as the signing key is the same).
