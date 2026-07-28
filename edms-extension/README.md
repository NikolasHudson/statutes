# Hudson EDMSpro — browser extension

Previews and downloads filings from an Iowa Courts EDMS docket, named the way
the attorney's template says. Lives in this monorepo, next to the backend it
talks to (`backend/apps/edms`), so a change to the API and its client version
together.

Ported from the `Casevault` prototype (github.com/NikolasHudson/EDMSpro,
archived 2026-07-28). The prototype's scraping, injected UI and Carbon restyle
survive intact; its auth (djoser/JWT), its upload path (multipart to the
server) and its settings page were replaced.

## The one thing to understand

**v1 sends filing bytes nowhere.** A filing is fetched from the court
same-origin, with the user's own logged-in session — the identical request
their click on the docket link would have made — and is then either rendered in
the side panel or written to the local Downloads folder. Hudson is contacted
only for sign-in and for metadata the server owns anyway (the naming template,
the confidential-case list). Microsoft is never contacted.

The cloud save flow (route → direct browser-to-OneDrive upload → server-side
verify, with bytes never passing through Hudson) is **parked for v2**. The
server half is preserved behind `EDMS_CLOUD_ENABLED`; the client half is
`lib/upload.js` and `picker.js`, kept in-tree but imported by nothing. The
packaging script below excludes them from the Web Store zip.

## Layout

| File | What it is |
|---|---|
| `background.js` | Service worker. The only place that talks to Hudson — SW fetches are CORS-exempt, so the backend needs no CORS config for the extension to exist. Also brokers the preview buffer and local downloads. |
| `lib/auth.js` | OAuth 2.1 + PKCE sign-in via `chrome.identity.launchWebAuthFlow`. Refresh token in `chrome.storage.local`, access token in memory only. |
| `lib/api.js` | `/api/edms/*` client. Bearer first, pasted API key as fallback. The cloud endpoints at the bottom are parked for v2. |
| `lib/config.js` | Backend origin, OAuth client id + scope, deep links. |
| `content.js` | Docket scraping + injected UI (banner, per-row preview/download, download-all zip). |
| `zip.js` | Minimal STORE-only zip builder for download-all. |
| `sidepanel.*` | Sign-in and the side-by-side PDF preview. |
| `popup.*` | Toolbar launcher. |
| `options.*` | Device-local settings only (which Hudson, API-key fallback). |
| `lib/upload.js` | **Parked for v2.** Chunked PUT to a Graph upload session. Not imported. |
| `picker.js` | **Parked for v2.** In-page OneDrive folder picker. Not loaded. |
| `tokens.css` | Carbon tokens, mirrored from `chat-frontend/components/carbon/primitives.tsx`. |

Product settings — folder layout, file naming, contribution sharing, the
safety filter — are **not** here. They live at `/account/edms` in the app,
because the server reads them anyway and a second copy on each device is a
second answer waiting to disagree. Every "Settings" affordance in the extension
deep-links there.

## Loading it for development

1. `chrome://extensions` → enable Developer mode → **Load unpacked** → pick
   this directory.
2. Confirm the id is `gnkpejhcnkldfpmpokckgcipcgpbpekf`. It is pinned by the
   `key` in `manifest.json`, so it is the same on every machine and matches the
   OAuth redirect URI the server allows.
3. Point it at a backend if you are not using production: the extension's
   options page (**This device**) → *Hudson URL*. Leave it empty for
   `https://app.hudsonlegal.tech`. On the dev droplet, use the Next dev server
   (`http://localhost:3000` via SSH port-forward) — it proxies `/oauth` in dev.
4. On that backend, register the client once:

   ```
   ./manage.py seed_edms_oauth_client --extension-id gnkpejhcnkldfpmpokckgcipcgpbpekf
   ```

5. Open the side panel (toolbar icon → **Open side panel**) → **Sign in to
   Hudson**. A Hudson window opens, you approve the consent screen, and the
   panel flips to "Connected as …".

### The signing key

`manifest.json` carries a `key`, which is what fixes the extension id. Its
private half is **not** in this repo (`.gitignore` blocks `*.pem`) — it lives
at `/home/dev/edmspro-extension-key.pem` on the dev box and should be backed up
somewhere durable before the Web Store listing exists. Losing it does not break
an installed extension, but it does mean a new id, which means re-seeding the
OAuth client and re-signing in everywhere. The `key` stays in the manifest for
the Store upload — that is what makes the Store assign the same id.

## Packaging for the Web Store

```
./package-store.sh        # writes dist/hudson-edmspro-<version>.zip
```

The dev tree and the Store zip differ deliberately:

- `picker.js` and `lib/upload.js` are excluded (parked for v2 — nothing
  imports them, so shipping them would only widen the review surface).
- The `http://localhost/*` and `http://127.0.0.1/*` host permissions are
  stripped. They exist so a dev build can talk to a local Django without CORS;
  a shipped build has no business holding them.
- `demo/` ships: the demo docket is how a reviewer (or a prospect) exercises
  the extension without an Iowa Courts login.

Everything else is identical — there is no build step, so what you load
unpacked is what ships.

## Testing checklist (before the Store)

The pieces worth exercising by hand, because none of them can be unit-tested
from here:

- [ ] Sign in / sign out, including sign-out actually revoking (the next
      metadata call should 401 and the docket should drop to the signed-out
      banner).
- [ ] Preview on a real docket: the eye icon opens the side panel beside the
      docket, clicking another row swaps the PDF in place, and the docket
      stays clickable.
- [ ] Download on a real docket: the filename matches the template from
      `/account/edms`, and a re-download uniquifies rather than overwrites.
- [ ] Download-all: the zip contains every unique document, name collisions
      get ` (n)` suffixes, and a partial failure reports the count rather than
      pretending success.
- [ ] `chrome.sidePanel.open()` surviving the content-script → service-worker
      hop. It is called from inside the click handler for this reason; if
      Chrome ever tightens the gesture rule, the fallback is an in-page docked
      pane (see the plan doc).
- [ ] A confidential case type (JV/JD/AD): the banner flags it. (Nothing
      uploads in v1, so this is display-only — but the server refuses
      contribution for these types regardless, and that stays true for v2.)
- [ ] The packaged zip from `package-store.sh` loads cleanly and contains no
      localhost host permissions, no `picker.js`, no `lib/upload.js`.
