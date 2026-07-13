// Same-origin proxy for the newsletter form — see app/api/contact/route.ts for
// why the visitor's address is carried in X-Real-Client-IP (which Cloudflare
// overwrites, so it cannot be forged) rather than in the X-Forwarded-For chain
// (which is appended to, so relaying it would let a visitor choose the IP their
// submissions are throttled under).

import { NextResponse } from "next/server";
import { API_ORIGIN } from "@/lib/api";

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
		const res = await fetch(`${API_ORIGIN}/api/marketing/subscribe`, {
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
