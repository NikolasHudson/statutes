// Brand names, in one place. Every user-visible occurrence of the product or
// company name should import from here rather than hard-coding a string, so a
// rename is an edit to this file rather than a sweep across the app.
//
// The backend has a matching module at backend/core/brand.py — keep them in
// step. (They are separate files rather than one served value because these
// strings appear in server-rendered <title> metadata, before any fetch.)

// The product.
export const BRAND_NAME = "Hudson Corpus";

// The company — used where we speak as the operator (Terms, the footer).
export const COMPANY_NAME = "Hudson Legal Technologies";

// The MCP server's connector key — the name users type into `claude mcp add`
// and that lands in their local client config. Renaming it breaks every existing
// connector, which is why it is being renamed NOW, while there are zero
// registered clients, and frozen permanently after: it must survive any future
// rebrand, so treat it as a wire identifier and not as a brand string.
export const MCP_SERVER_ID = "hudson-corpus";

// --- Origins ---------------------------------------------------------------
// This app is served FROM the app origin, so it can derive its own URL and needs
// no hard-coded domain. NEXT_PUBLIC_APP_URL (inlined at build time) wins when set
// — it is the only source available during SSR, where `window` does not exist.
// These are functions, not module consts, precisely because of that: the module
// is imported by server-rendered metadata, and a const would freeze in the
// window-less value.

/** Absolute origin the app is served from ("https://app.hudsonlegal.tech"), or "". */
export function appOrigin(): string {
  const configured = process.env.NEXT_PUBLIC_APP_URL;
  if (configured) return configured.replace(/\/+$/, "");
  if (typeof window !== "undefined") return window.location.origin;
  return "";
}

/** Host portion of the app origin ("app.hudsonlegal.tech"), for display. */
export function appHost(): string {
  const origin = appOrigin();
  if (!origin) return "";
  try {
    return new URL(origin).host;
  } catch {
    return origin.replace(/^https?:\/\//, "");
  }
}

/** The MCP endpoint external clients connect to, on this same origin. */
export function mcpUrl(): string {
  return `${appOrigin()}/mcp`;
}
