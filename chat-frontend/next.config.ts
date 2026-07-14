import type { NextConfig } from "next";

// The Next.js app serves the whole frontend at the root of app.hudsonlegal.tech
// in production (App Platform routes / → chat-frontend; /api and /admin
// go to Django). No basePath: same URL in dev and prod.
const isProd = process.env.NODE_ENV === "production";

// Content-Security-Policy. Everything the app talks to is same-origin:
//   - API/auth/chat/verify all hit relative /api/* paths (DJANGO_BASE = ""),
//     routed to Django by App Platform ingress in prod and a dev rewrite
//     locally — so connect-src 'self' covers them.
//   - Fonts use next/font/google, which self-hosts the font files at build
//     time under /_next, so no external font origin is required.
// Next.js injects inline bootstrap/runtime <script> and inline styles
// (styled-jsx + framework style tags); without a nonce middleware these
// require 'unsafe-inline'. Dev additionally needs 'unsafe-eval' and a ws:
// connection for React Refresh / HMR. frame-ancestors 'none' backstops the
// X-Frame-Options header against clickjacking.
const cspDirectives = [
	"default-src 'self'",
	`script-src 'self' 'unsafe-inline'${isProd ? "" : " 'unsafe-eval'"}`,
	"style-src 'self' 'unsafe-inline'",
	"img-src 'self' data: blob:",
	"font-src 'self' data:",
	`connect-src 'self'${isProd ? "" : " ws: http://localhost:8000"}`,
	"base-uri 'self'",
	"form-action 'self'",
	"frame-ancestors 'none'",
	"object-src 'none'",
	...(isProd ? ["upgrade-insecure-requests"] : []),
];

const securityHeaders = [
	{
		key: "Content-Security-Policy",
		value: cspDirectives.join("; "),
	},
	{ key: "X-Frame-Options", value: "DENY" },
	{ key: "X-Content-Type-Options", value: "nosniff" },
	{ key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
	{
		// No `preload` token — see the note in marketing-frontend/next.config.ts:
		// the decision is strong HSTS without hstspreload.org submission, so an
		// HTTP staging/partner subdomain remains possible later.
		key: "Strict-Transport-Security",
		value: "max-age=63072000; includeSubDomains",
	},
];

const nextConfig: NextConfig = {
	// `output: "standalone"` makes `next build` emit .next/standalone/ which
	// bundles only the files the production server needs — half the image
	// size of a full node_modules copy.
	output: "standalone",

	// Dev only: forward /api/* server-side to Django on :8000 so the browser
	// stays same-origin (works in Codespaces port-forwarding and keeps
	// session cookies happy). In production /api/* is routed to the Django
	// component by App Platform's ingress rules — the Next.js app never
	// proxies anything itself.
	async rewrites() {
		if (isProd) return [];
		return [
			{
				source: "/api/:path*",
				destination: "http://localhost:8000/api/:path*",
			},
		];
	},

	// The Carbon app moved from /v2 to the root routes when it became the
	// official frontend; keep old /v2 links working. Not `permanent` (308
	// caches aggressively) so the prefix stays reusable.
	async redirects() {
		return [
			{ source: "/v2", destination: "/", permanent: false },
			{ source: "/v2/:path*", destination: "/:path*", permanent: false },
		];
	},

	// Defense-in-depth security response headers for every Next-served route.
	// App Platform does not add these at the edge, so they ship from the app
	// itself. Confirm with `curl -I` against / and /browse after deploy.
	async headers() {
		return [
			{
				source: "/:path*",
				headers: securityHeaders,
			},
		];
	},
};

export default nextConfig;
