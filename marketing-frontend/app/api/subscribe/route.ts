// Same-origin proxy for the newsletter form — see app/api/contact/route.ts.

import { NextResponse } from "next/server";
import { API_ORIGIN } from "@/lib/api";

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
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(body),
		});
		return NextResponse.json(await res.json().catch(() => ({})), {
			status: res.status,
		});
	} catch {
		return NextResponse.json({ ok: false }, { status: 502 });
	}
}
