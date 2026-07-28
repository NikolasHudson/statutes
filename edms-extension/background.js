// Hudson EDMSpro service worker — the only place in the extension that talks to
// Hudson or to Microsoft.
//
// Everything here runs in the service worker rather than the content script for
// one concrete reason: extension service-worker fetches are exempt from CORS
// (host permissions cover them), so the backend needs no CORS entries and no CSP
// changes for the extension to exist. Move a fetch into the page and that stops
// being true.
//
// v1 does not save anywhere. The extension previews a filing and downloads it
// locally with the server-defined naming template; filing bytes never reach
// Hudson and never reach Microsoft. The OneDrive route/upload/complete flow and
// the contribution intake that rode on it are preserved server-side behind
// EDMS_CLOUD_ENABLED, and lib/upload.js + picker.js are parked here unwired for
// when v2 turns them back on.

import { SETTINGS_PATH, appUrl } from "./lib/config.js";
import { accountEmail, isSignedIn, signIn, signOut } from "./lib/auth.js";
import * as api from "./lib/api.js";

chrome.runtime.onInstalled.addListener(async () => {
  // Only device-local things get defaults now. Folders, naming and the
  // contribution opt-in live on the server — the route endpoint reads them on
  // every save, so a second copy here could only ever be wrong.
  const defaults = { backendUrl: "", edmsApiKey: "" };
  const existing = await chrome.storage.local.get(defaults);
  await chrome.storage.local.set(existing);
});

// The toolbar icon keeps its popup; the side panel is opened deliberately, from
// the popup or from a docket row's preview button.
chrome.sidePanel?.setPanelBehavior?.({ openPanelOnActionClick: false }).catch(() => {});

// --- helpers ---------------------------------------------------------------

async function openApp(path) {
  chrome.tabs.create({ url: await appUrl(path) });
}

function errorPayload(err) {
  const status = err?.status;
  // Translate the statuses the server uses into something a docket page can
  // show a lawyer without a second lookup.
  if (status === 401) return { ok: false, error: "Sign in to Hudson EDMSpro.", code: "signin" };
  if (status === 402 || status === 403) {
    return { ok: false, error: err.detail || "Not available on your plan.", code: "plan" };
  }
  if (status === 409) {
    return { ok: false, error: err.detail || "Connect OneDrive first.", code: "connect" };
  }
  if (status === 429) {
    return { ok: false, error: err.detail || "Daily limit reached.", code: "limit" };
  }
  return { ok: false, error: err?.message || String(err) };
}


// --- local download --------------------------------------------------------

function triggerLocalDownload({ url, filename }) {
  return new Promise((resolve) => {
    try {
      chrome.downloads.download(
        { url, filename: filename || undefined, saveAs: false, conflictAction: "uniquify" },
        (downloadId) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, error: chrome.runtime.lastError.message });
          } else if (downloadId == null) {
            resolve({ ok: false, error: "download not started" });
          } else {
            resolve({ ok: true, downloadId });
          }
        },
      );
    } catch (err) {
      resolve({ ok: false, error: String(err?.message || err) });
    }
  });
}

// --- preview ---------------------------------------------------------------
//
// The content script fetches the PDF (it is same-origin there, so the court
// session is guaranteed to ride along) and hands us the bytes; we stash them and
// open the side panel, which renders them from the extension origin where the
// host page's CSP cannot interfere. Nothing is sent to Hudson — this is the same
// request the user's own click on the link would have made.

let previewBuffer = null;

async function openPreview(payload, tabId) {
  previewBuffer = { bytes: payload.bytes, title: payload.title, meta: payload.meta };
  try {
    // Must be called while the user's click is still the reason we are here;
    // Chrome rejects an ungestured open. The content script sends this straight
    // from its click handler for that reason.
    await chrome.sidePanel.open({ tabId });
  } catch {
    previewBuffer = null;
    return { ok: false, error: "Chrome would not open the side panel." };
  }
  chrome.runtime.sendMessage({ type: "cv:previewReady" }).catch(() => {});
  return { ok: true };
}

// --- message router --------------------------------------------------------

const HANDLERS = {
  "cv:authStatus": async () => ({
    ok: true,
    signedIn: await isSignedIn(),
    email: await accountEmail(),
  }),
  "cv:signIn": async () => {
    try {
      const { email } = await signIn();
      return { ok: true, email };
    } catch (err) {
      return { ok: false, error: err.message };
    }
  },
  "cv:signOut": async () => {
    await signOut();
    return { ok: true };
  },
  "cv:openSettings": async () => {
    await openApp(SETTINGS_PATH);
    return { ok: true };
  },
  "cv:openDemo": async () => {
    chrome.tabs.create({ url: chrome.runtime.getURL("demo/docket.html") });
    return { ok: true };
  },
  "cv:getSettings": async () => {
    try {
      return { ok: true, settings: await api.getSettings() };
    } catch (err) {
      return errorPayload(err);
    }
  },
  "cv:getSafety": async () => {
    try {
      return { ok: true, safety: await api.getSafety() };
    } catch (err) {
      return errorPayload(err);
    }
  },
  "cv:downloadLocal": async (msg) => {
    if (!msg.url) return { ok: false, error: "missing url" };
    return triggerLocalDownload(msg);
  },
  "cv:openPreview": async (msg, sender) => openPreview(msg, sender?.tab?.id),
  "cv:takePreview": async () => {
    const payload = previewBuffer;
    previewBuffer = null;
    return { ok: Boolean(payload), preview: payload };
  },
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const handler = HANDLERS[msg?.type];
  if (!handler) return false;
  handler(msg, sender)
    .then(sendResponse)
    .catch((err) => sendResponse({ ok: false, error: err?.message || String(err) }));
  return true; // async response
});
