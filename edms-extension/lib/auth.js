// Sign-in: OAuth 2.1 authorization code + PKCE against Hudson's own
// authorization server (the one the MCP connectors use).
//
// Why this and not the prototype's email/password → JWT: an extension that
// collects a password is an extension that has to be trusted with a password.
// `chrome.identity.launchWebAuthFlow` opens a real browser window on
// app.hudsonlegal.tech, the user signs in there (or is already signed in) and
// approves a consent screen that says what the extension may do, and Chrome
// hands back only an authorization code. This extension never sees a
// credential, and the user can revoke it server-side at any time.
//
// Token discipline, unchanged from the prototype and worth keeping:
//   * refresh token → chrome.storage.local (it must survive the service worker
//     being torn down, which Chrome does aggressively)
//   * access token → memory only, so it dies with the worker
// A cold worker therefore starts by refreshing, which is one extra round trip
// and one fewer long-lived bearer token sitting in extension storage.
//
// Refresh rotation is enforced by the server (OAuth 2.1: a replayed refresh
// token revokes the whole family), so `refresh()` must be called serially —
// hence the in-flight promise below rather than one refresh per queued request.

import { OAUTH_CLIENT_ID, OAUTH_SCOPE, backendUrl } from "./config.js";

const STORAGE_KEY = "edmsRefreshToken";
const EMAIL_KEY = "edmsAccountEmail";

let accessToken = "";
let accessExpiresAt = 0;
let refreshInFlight = null;

// --- PKCE ------------------------------------------------------------------

function base64UrlEncode(bytes) {
  let binary = "";
  for (const b of new Uint8Array(bytes)) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomVerifier() {
  // 32 random bytes → 43 base64url chars, the low end of RFC 7636's 43–128.
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

async function challengeFor(verifier) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64UrlEncode(digest);
}

export function redirectUri() {
  // https://<extension-id>.chromiumapp.org/ — a plain HTTPS URL Chrome
  // intercepts. The extension id is pinned by the `key` in manifest.json, so
  // this string is stable across machines and matches the server-side
  // allowlist seeded by `manage.py seed_edms_oauth_client`.
  return chrome.identity.getRedirectURL();
}

// --- token storage ---------------------------------------------------------

async function storedRefreshToken() {
  const stored = await chrome.storage.local.get({ [STORAGE_KEY]: "" });
  return stored[STORAGE_KEY] || "";
}

async function persist(tokens) {
  accessToken = tokens.access_token || "";
  accessExpiresAt = Date.now() + (Number(tokens.expires_in) || 3600) * 1000 - 60_000;
  if (tokens.refresh_token) {
    await chrome.storage.local.set({ [STORAGE_KEY]: tokens.refresh_token });
  }
}

export async function clearTokens() {
  accessToken = "";
  accessExpiresAt = 0;
  await chrome.storage.local.remove([STORAGE_KEY, EMAIL_KEY]);
}

export async function accountEmail() {
  const stored = await chrome.storage.local.get({ [EMAIL_KEY]: "" });
  return stored[EMAIL_KEY] || "";
}

async function rememberAccount(base) {
  // Purely for the "Connected as …" line. A failure here must not fail sign-in.
  try {
    const resp = await fetch(`${base}/api/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!resp.ok) return;
    const me = await resp.json();
    if (me?.email) await chrome.storage.local.set({ [EMAIL_KEY]: me.email });
  } catch {
    /* non-fatal */
  }
}

// --- flows -----------------------------------------------------------------

export async function signIn() {
  const base = await backendUrl();
  const verifier = randomVerifier();
  const challenge = await challengeFor(verifier);
  const state = randomVerifier();

  const authorizeUrl =
    `${base}/oauth/authorize?` +
    new URLSearchParams({
      response_type: "code",
      client_id: OAUTH_CLIENT_ID,
      redirect_uri: redirectUri(),
      scope: OAUTH_SCOPE,
      state,
      code_challenge: challenge,
      code_challenge_method: "S256",
    }).toString();

  const callbackUrl = await chrome.identity.launchWebAuthFlow({
    url: authorizeUrl,
    interactive: true,
  });
  if (!callbackUrl) throw new Error("Sign-in was cancelled.");

  const params = new URL(callbackUrl).searchParams;
  if (params.get("error")) {
    throw new Error(params.get("error_description") || params.get("error"));
  }
  if (params.get("state") !== state) {
    // The only thing this can be is a response we didn't ask for.
    throw new Error("Sign-in response did not match the request.");
  }
  const code = params.get("code");
  if (!code) throw new Error("Sign-in returned no authorization code.");

  const resp = await fetch(`${base}/oauth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri(),
      client_id: OAUTH_CLIENT_ID,
      code_verifier: verifier,
    }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error_description || `Token exchange failed (${resp.status}).`);
  }
  await persist(await resp.json());
  await rememberAccount(base);
  return { email: await accountEmail() };
}

async function refresh() {
  const token = await storedRefreshToken();
  if (!token) return "";
  const base = await backendUrl();
  const resp = await fetch(`${base}/oauth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: token,
      client_id: OAUTH_CLIENT_ID,
    }),
  });
  if (!resp.ok) {
    // Expired, revoked, or replayed (which revokes the family server-side).
    // Either way this device is signed out — say so rather than retrying.
    await clearTokens();
    return "";
  }
  await persist(await resp.json());
  return accessToken;
}

/** A usable access token, refreshing if needed. "" when signed out. */
export async function getAccessToken() {
  if (accessToken && Date.now() < accessExpiresAt) return accessToken;
  // Serialize: two parallel requests must not each spend the refresh token —
  // the second use would look like a replay and revoke the whole family.
  if (!refreshInFlight) {
    refreshInFlight = refresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** Force the next request to refresh — used after a 401. */
export function invalidateAccessToken() {
  accessToken = "";
  accessExpiresAt = 0;
}

export async function isSignedIn() {
  return Boolean(await storedRefreshToken());
}

export async function signOut() {
  const token = await storedRefreshToken();
  const base = await backendUrl();
  if (token) {
    try {
      // Revokes the whole token family server-side, so signing out here
      // actually ends the grant rather than just forgetting it locally.
      await fetch(`${base}/oauth/revoke`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ token, client_id: OAUTH_CLIENT_ID }),
      });
    } catch {
      /* revoke is best-effort; local state is cleared regardless */
    }
  }
  await clearTokens();
}
