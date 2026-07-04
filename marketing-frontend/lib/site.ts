// Single source of truth for cross-origin + canonical URLs. Domain-agnostic:
// override per environment with NEXT_PUBLIC_* envs (see .env.example). The
// marketing domain is intentionally not hard-coded — only the app origin has a
// stable default, since the app already lives at corpus.nick.law.

export const APP_URL =
	process.env.NEXT_PUBLIC_APP_URL ?? "https://corpus.nick.law";

export const SITE_URL =
	process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3001";

// Where marketing CTAs send people into the app. Both land on the app's
// sign-in / sign-up screen today; split later if the app gets dedicated routes.
export const SIGN_IN_URL = APP_URL;
export const GET_STARTED_URL = APP_URL;

// The live MCP endpoint external clients depend on (stays on the app origin).
export const MCP_URL = `${APP_URL}/mcp`;
