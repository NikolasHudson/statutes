import type { NextConfig } from "next";

// Public marketing site (separate deployment from the app at app.hudsonlegal.tech).
// Mostly static/SSG; the browser never talks to the backend directly. The two
// same-origin route handlers (app/api/contact, app/api/subscribe) and the
// articles pages call the backend SERVER-side via API_ORIGIN (lib/api.ts), so
// CSP stays self-only and backend CORS is untouched. CTAs link out to the app
// via NEXT_PUBLIC_APP_URL (see lib/site.ts).
const isProd = process.env.NODE_ENV === "production";

// Content-Security-Policy. Marketing is self-contained today: Next injects
// inline bootstrap <script> + inline styles (needs 'unsafe-inline'), fonts are
// self-hosted by next/font at build time, images are local. When analytics or
// embeds are added, widen script-src/connect-src/img-src here accordingly.
const cspDirectives = [
	"default-src 'self'",
	`script-src 'self' 'unsafe-inline'${isProd ? "" : " 'unsafe-eval'"}`,
	"style-src 'self' 'unsafe-inline'",
	"img-src 'self' data: blob:",
	"font-src 'self' data:",
	`connect-src 'self'${isProd ? "" : " ws:"}`,
	"base-uri 'self'",
	"form-action 'self'",
	"frame-ancestors 'none'",
	"object-src 'none'",
	...(isProd ? ["upgrade-insecure-requests"] : []),
];

const securityHeaders = [
	{ key: "Content-Security-Policy", value: cspDirectives.join("; ") },
	{ key: "X-Frame-Options", value: "DENY" },
	{ key: "X-Content-Type-Options", value: "nosniff" },
	{ key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
	{
		// No `preload` token: the decision (DOMAIN_AND_BRAND_PLAN, open decision #2)
		// is to keep strong HSTS but NOT submit to hstspreload.org, so that an
		// HTTP staging/partner subdomain stays possible later. Advertising `preload`
		// invites list operators to enrol the apex + all subdomains irreversibly,
		// which is exactly what that decision declined. includeSubDomains stays.
		key: "Strict-Transport-Security",
		value: "max-age=63072000; includeSubDomains",
	},
];

const nextConfig: NextConfig = {
	// Emit .next/standalone for a slim production image (DO App Platform).
	output: "standalone",

	async headers() {
		return [{ source: "/:path*", headers: securityHeaders }];
	},
};

export default nextConfig;
