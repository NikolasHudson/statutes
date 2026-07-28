// Where the extension talks, and who it says it is.
//
// The backend origin is overridable from the options page for exactly one
// reason — pointing a dev build at a local Django — and that override is the
// only genuinely device-local setting left. Everything else (folders, naming,
// contribution opt-in) lives server-side, because the server needs it anyway to
// resolve a destination and a second copy on each device is a second answer.

export const DEFAULT_BACKEND_URL = "https://app.hudsonlegal.tech";

// Must match core/brand.py EDMS_OAUTH_CLIENT_ID, and the row that
// `manage.py seed_edms_oauth_client` writes. Frozen once a build ships.
export const OAUTH_CLIENT_ID = "hudson-edmspro-extension";

// The scope this extension asks for. An `mcp` token opens nothing on
// /api/edms, and this one opens nothing on the MCP surface.
export const OAUTH_SCOPE = "edms";

export const PRODUCT_NAME = "Hudson EDMSpro";

// Deep link for every "Settings" affordance in the extension. Product settings
// live in the app, on their own page — the extension never grows a second,
// drifting copy of them.
export const SETTINGS_PATH = "/account/edms";
export const FILINGS_PATH = "/filings";

// Everything this extension holds flows through this origin: the authorize URL,
// the PKCE code exchange, and every Bearer-authenticated API call. This check
// refuses plaintext transports — https anywhere; http only for loopback, which
// is what a dev build needs and what browsers already treat as a secure
// context. Returning "" makes backendUrl() fall back to the real backend, so a
// refused value fails closed rather than being trusted.
//
// What it does NOT do: pin the origin to Hudson. Any https origin is accepted,
// so "paste this URL into the Hudson options, then sign in" remains a
// social-engineering path to the tokens and the pasted API key. That is the
// price of the dev override existing at all; if v2 ever drops the need for it,
// drop the field and this function with it.
export function normalizeBackendUrl(url) {
  const raw = (url || "").trim().replace(/\s+/g, "").replace(/\/+$/, "");
  if (!raw) return "";
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return "";
  }
  const loopback =
    parsed.hostname === "localhost" ||
    parsed.hostname === "127.0.0.1" ||
    parsed.hostname === "[::1]";
  if (parsed.protocol === "https:" || (parsed.protocol === "http:" && loopback)) {
    return raw;
  }
  return "";
}

export async function backendUrl() {
  const stored = await chrome.storage.local.get({ backendUrl: DEFAULT_BACKEND_URL });
  return normalizeBackendUrl(stored.backendUrl) || DEFAULT_BACKEND_URL;
}

export async function appUrl(path) {
  return (await backendUrl()) + path;
}
