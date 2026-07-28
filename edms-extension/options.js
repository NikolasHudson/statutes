// Options — what is left of it.
//
// The prototype's options page was the product's settings screen: provider,
// folders, naming, opt-in, safety list. All of that now lives at /account/edms
// in the app, for two reasons. The server needs those values anyway to resolve a
// destination, so a device-local copy was always a second answer waiting to
// disagree; and enabling contribution sharing is session-only server-side, so an
// extension-side control for it could never have worked.
//
// What is genuinely device-local, and therefore still here: which Hudson to talk
// to, the API-key fallback, and the sign-in state itself.

// A module (options.html loads it with type="module") so the backend-URL rule
// is imported from the one place that defines it rather than restated here —
// a second copy of a security check is a second copy to get wrong.
import { DEFAULT_BACKEND_URL, normalizeBackendUrl } from "./lib/config.js";

const els = {
  backendUrl: document.getElementById("backendUrl"),
  apiKey: document.getElementById("apiKey"),
  savedHint: document.getElementById("savedHint"),
  authLoggedOut: document.getElementById("authLoggedOut"),
  authLoggedIn: document.getElementById("authLoggedIn"),
  authEmailDisplay: document.getElementById("authEmailDisplay"),
  authStatus: document.getElementById("authStatus"),
  signInBtn: document.getElementById("signInBtn"),
  signOutBtn: document.getElementById("signOutBtn"),
  openSettings: document.getElementById("openSettings"),
  openDemo: document.getElementById("openDemo"),
};

function send(message) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(message, (resp) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        resolve(resp || { ok: false, error: "no response" });
      }
    });
  });
}

let savedTimer = null;
function flashSaved() {
  els.savedHint.classList.add("is-on");
  clearTimeout(savedTimer);
  savedTimer = setTimeout(() => els.savedHint.classList.remove("is-on"), 1400);
}

function status(text, kind = "info") {
  if (!text) {
    els.authStatus.hidden = true;
    return;
  }
  els.authStatus.textContent = text;
  els.authStatus.className = `auth__status auth__status--${kind}`;
  els.authStatus.hidden = false;
}

async function renderAuth() {
  const resp = await send({ type: "cv:authStatus" });
  const signedIn = Boolean(resp.signedIn);
  els.authLoggedOut.hidden = signedIn;
  els.authLoggedIn.hidden = !signedIn;
  els.authEmailDisplay.textContent = resp.email || "your Hudson account";
}

// --- device-local settings -------------------------------------------------

chrome.storage.local.get({ backendUrl: "", edmsApiKey: "" }, (stored) => {
  els.backendUrl.value = stored.backendUrl || "";
  els.apiKey.value = stored.edmsApiKey || "";
});

// `change` alone fires only on blur, so typing a URL and closing the tab
// discarded it silently — and a wrong backend URL surfaces as an opaque "auth
// page could not be loaded" from launchWebAuthFlow, a long way from the cause.
// Save on `input` too, so the field persists as typed.
for (const ev of ["change", "input"]) {
  els.backendUrl.addEventListener(ev, () => {
    const typed = els.backendUrl.value.trim();
    chrome.storage.local.set({ backendUrl: typed });
    // normalizeBackendUrl refuses anything that is not https (or http on
    // loopback) and falls back to the real backend. Say so — a silently
    // ignored setting is how you end up debugging the wrong layer.
    if (typed && !normalizeBackendUrl(typed)) {
      status(
        `Ignoring "${typed}" — must be https, or http on localhost. Using ${DEFAULT_BACKEND_URL}.`,
        "warn",
      );
      return;
    }
    status("");
    flashSaved();
  });

  els.apiKey.addEventListener(ev, () => {
    chrome.storage.local.set({ edmsApiKey: els.apiKey.value.trim() });
    flashSaved();
  });
}

// --- auth ------------------------------------------------------------------

els.signInBtn.addEventListener("click", async () => {
  els.signInBtn.disabled = true;
  status("Opening the Hudson sign-in window…");
  const resp = await send({ type: "cv:signIn" });
  els.signInBtn.disabled = false;
  if (resp.ok) {
    status(`Signed in as ${resp.email || "your account"}.`, "ok");
    await renderAuth();
  } else {
    status(resp.error || "Sign-in failed.", "error");
  }
});

els.signOutBtn.addEventListener("click", async () => {
  await send({ type: "cv:signOut" });
  status("Signed out. Access for this device has been revoked.", "ok");
  await renderAuth();
});

els.openSettings.addEventListener("click", () => send({ type: "cv:openSettings" }));
els.openDemo.addEventListener("click", () => send({ type: "cv:openDemo" }));

void renderAuth();
