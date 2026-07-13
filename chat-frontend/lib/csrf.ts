// CSRF token plumbing for credentialed requests to the Django session API.
//
// The session-cookie routes (/api/auth/*, /api/account/*, /api/chat*,
// /api/verify/*) enforce Django's CSRF token on unsafe methods. Django sets a
// readable CSRF cookie (CSRF_COOKIE_HTTPONLY is False); the browser must echo it
// back as the `X-CSRFToken` header on every POST/PATCH/DELETE. These helpers read
// that cookie and bootstrap it from GET /api/auth/csrf when it is not yet present.
//
// The cookie has two names. Prod uses `__Host-csrftoken`; dev serves Django over
// plain HTTP, where a __Host- cookie is silently dropped for want of Secure, so it
// stays `csrftoken` there. One build ships to both, so read either.

// Django's default CSRF header name (settings.CSRF_HEADER_NAME → X-CSRFToken).
export const CSRF_HEADER = "X-CSRFToken";

// Anchored on `^` or `;` so neither pattern can match a cookie whose name merely
// ENDS in "csrftoken" (and so the plain pattern can't match the prefixed cookie).
const HOST_PREFIXED_COOKIE = /(?:^|;\s*)__Host-csrftoken=([^;]+)/;
const PLAIN_COOKIE = /(?:^|;\s*)csrftoken=([^;]+)/;

/** Read the CSRF cookie Django set, under either name, or null if absent. */
export function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  // Prefixed first: if a stale plain cookie lingers past a cutover, the __Host-
  // one is the one the server just issued and the one it will validate against.
  const m =
    document.cookie.match(HOST_PREFIXED_COOKIE) ??
    document.cookie.match(PLAIN_COOKIE);
  return m ? decodeURIComponent(m[1]) : null;
}

/**
 * Ensure the CSRF cookie exists, fetching it from the backend bootstrap
 * endpoint if Django hasn't set it on this browser yet. Safe to call often:
 * once the cookie is present it returns immediately without a network round
 * trip. Returns the token, or null if the bootstrap request failed.
 */
export async function ensureCsrfToken(): Promise<string | null> {
  const existing = getCsrfToken();
  if (existing) return existing;
  try {
    // Same-origin in prod; the Next dev server proxies /api to Django.
    await fetch("/api/auth/csrf", { credentials: "include" });
  } catch {
    return null;
  }
  return getCsrfToken();
}

/**
 * Headers to merge into a credentialed unsafe request. Resolves to the
 * `X-CSRFToken` header when a token is available, or `{}` when it can't be
 * obtained (the request will then fail the server's CSRF check, which is the
 * correct, safe outcome).
 */
export async function csrfHeaders(): Promise<Record<string, string>> {
  const token = await ensureCsrfToken();
  return token ? { [CSRF_HEADER]: token } : {};
}
