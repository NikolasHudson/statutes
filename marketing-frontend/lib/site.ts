// Single source of truth for cross-origin + canonical URLs, and for the brand
// names. Domain-agnostic: override per environment with NEXT_PUBLIC_* envs (see
// .env.example). Both origins are moving (marketing to the apex, the app to a
// subdomain of it), so nothing outside this file may hard-code either one.

// --- Brand -----------------------------------------------------------------
// The product. Say "Hudson Corpus" on first reference; the bare company name is
// COMPANY_NAME below. Do not introduce a third form.
export const BRAND_NAME = "Hudson Corpus";

// The company.
export const COMPANY_NAME = "Hudson Legal Technologies";

// The MCP server's connector key. Free to rename today only because no client
// has ever registered against the server; once one has, this string lives in
// users' local client config and is FROZEN — renaming it orphans their
// connector. Must stay in step with backend/core/brand.py (the wire ID).
export const MCP_SERVER_ID = "hudson-corpus";

// --- Origins ---------------------------------------------------------------

// NEXT_PUBLIC_* is INLINED AT BUILD TIME. An unset one cannot be recovered at
// runtime — the fallback is simply baked into the bundle — and the build stays
// green, so the failure is invisible until someone clicks. Measured blast
// radius of a wrong APP_URL alone: 71 clickable hrefs across 10 prerendered
// pages, plus the copy-pasteable MCP config block. Every fallback below is
// therefore a *dev* value, and a production build that reaches one is a build
// that would ship the wrong origin. Fail it instead: a red build is cheap, a
// launch pointing at a retired domain is not.
//
// Guarded on NODE_ENV only, so `next dev` still boots with nothing set.
function fromEnv(
	name: string,
	value: string | undefined,
	devFallback: string,
): string {
	// Truthiness, not `??`: a Docker `ENV FOO=$FOO` whose build-arg was never
	// passed arrives as "" — which `??` would happily accept.
	if (value) return value;
	if (process.env.NODE_ENV === "production") {
		throw new Error(
			`${name} is unset. It is baked into the bundle at build time, so a ` +
				`production build without it would silently ship "${devFallback}" to ` +
				`real users. Set it on the build environment (see .env.example).`,
		);
	}
	return devFallback;
}

// The app's origin — every marketing CTA, the MCP endpoint URL, the footer's
// legal links. This used to default to the app's old domain, which is now being
// retired: the build output is greppable for the retired hosts, so keep them out
// of this file entirely, comments included.
export const APP_URL = fromEnv(
	"NEXT_PUBLIC_APP_URL",
	process.env.NEXT_PUBLIC_APP_URL,
	"http://localhost:3000",
);

// Host only, for display strings ("app.hudsonlegal.tech"). Never build a link
// from this — links use APP_URL, which carries the scheme.
export const APP_HOST = new URL(APP_URL).host;

// This site's own canonical origin: sitemap.xml, robots.txt, every OG and
// canonical tag. Unset in production and the whole site self-identifies as
// localhost to every crawler that visits on day one.
export const SITE_URL = fromEnv(
	"NEXT_PUBLIC_SITE_URL",
	process.env.NEXT_PUBLIC_SITE_URL,
	"http://localhost:3001",
);

// Where marketing CTAs send people into the app. Both land on the app's
// sign-in / sign-up screen today; split later if the app gets dedicated routes.
export const SIGN_IN_URL = APP_URL;
export const GET_STARTED_URL = APP_URL;

// The live MCP endpoint external clients depend on (stays on the app origin).
export const MCP_URL = `${APP_URL}/mcp`;

// The inbound address the email assistant answers from (app-side, not
// marketing). Printed verbatim on /products/email as the address to write to —
// a stale value here tells visitors to email a dead mailbox.
export const ASSISTANT_ADDRESS = fromEnv(
	"NEXT_PUBLIC_ASSISTANT_ADDRESS",
	process.env.NEXT_PUBLIC_ASSISTANT_ADDRESS,
	"assistant@localhost",
);

// The human mailbox printed on /contact and /consulting. THIS ADDRESS DOES NOT
// RECEIVE MAIL YET — hudsonlegal.tech has no MX record, so anything sent to it
// today is silently dropped. It is kept as the default because the mail
// identity is Nick's call; routing every use through this one constant means
// standing up (or changing) that mailbox is a one-line edit, not a grep.
export const CONTACT_EMAIL =
	process.env.NEXT_PUBLIC_CONTACT_EMAIL || "consulting@hudsonlegal.tech";

// Privacy + data practices live in section 8 of the app's Terms of Service;
// /privacy on the app host redirects there. Absolute, because marketing is a
// different origin from the app and a bare "/privacy" would 404 here.
export const PRIVACY_URL = `${APP_URL}/privacy`;
export const TERMS_URL = `${APP_URL}/terms`;
