// Same-origin proxy for the contact form: the browser POSTs here (CSP stays
// 'self'), and we forward server-side to the backend, which stores the
// submission and notifies by email. Body shape is validated by the backend.
//
// The backend throttles lead capture per client IP — and every submission reaches
// it from THIS container's egress address, because a server-side fetch carries
// none of the caller's headers. Left alone, the whole internet shares one throttle
// bucket. So we carry the visitor's address across explicitly, in a dedicated
// header, with a shared secret proving the value is ours and not something a
// stranger typed into a curl. The backend honours it only with that token AND only
// on /api/marketing/* (apps/accounts/audit.client_ip).
//
// We send CF-Connecting-IP and NOT the X-Forwarded-For chain, which is a
// deliberate narrowing of the original design:
//
//   * CF-Connecting-IP is OVERWRITTEN by Cloudflare on ingress, so the browser
//     cannot forge it. App Platform is always Cloudflare-fronted (even the bare
//     *.ondigitalocean.app host resolves to Cloudflare), so it is always stamped.
//   * X-Forwarded-For is APPENDED to. Relaying it would mean the backend has to
//     guess how many entries came from infrastructure and how many the visitor
//     typed — and a visitor who guesses wrong-by-one gets to CHOOSE the IP their
//     leads are throttled and recorded under. That is the forgery this whole
//     change exists to close; re-opening it on the lead funnel to save a header is
//     a bad trade.
//
// No CF header (local dev), or no token (a deploy that hasn't set it) = send
// nothing, and the backend falls back to the connecting address. Degraded
// attribution, never a forgeable one.

import { NextResponse } from "next/server";
import { API_ORIGIN } from "@/lib/api";

// Not exported: a route.ts may only export route handlers, so the twin of this
// lives in app/api/subscribe/route.ts rather than in a shared module.
function proxyHeaders(request: Request): Record<string, string> {
	const headers: Record<string, string> = { "Content-Type": "application/json" };
	const token = process.env.MARKETING_PROXY_TOKEN;
	const clientIp = request.headers.get("cf-connecting-ip");
	if (token && clientIp) {
		headers["X-Real-Client-IP"] = clientIp;
		headers["X-Marketing-Proxy-Token"] = token;
	}
	return headers;
}

export async function POST(request: Request) {
	let body: unknown;
	try {
		body = await request.json();
	} catch {
		return NextResponse.json({ ok: false }, { status: 400 });
	}
	try {
		const res = await fetch(`${API_ORIGIN}/api/marketing/contact`, {
			method: "POST",
			headers: proxyHeaders(request),
			body: JSON.stringify(body),
		});
		return NextResponse.json(await res.json().catch(() => ({})), {
			status: res.status,
		});
	} catch {
		return NextResponse.json({ ok: false }, { status: 502 });
	}
}
