# Android Signing Reference

Details on APK signing — useful if you need to regenerate a keystore, understand the CI signing flow, or troubleshoot install issues.

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
