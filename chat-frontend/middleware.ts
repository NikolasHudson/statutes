// Cloudflare origin lock. A request-header Transform Rule on the zone stamps
// every proxied request with X-Origin-Lock: <ORIGIN_LOCK_SECRET>; anything
// arriving without it came straight to the public *.ondigitalocean.app origin
// and skipped every edge control (WAF, rate limits, CF-Connecting-IP). Same
// contract as the Django OriginLockMiddleware (backend/core/middleware.py).
//
// Inert while ORIGIN_LOCK_SECRET is unset (dev, local builds). /healthz stays
// open: App Platform's container probe hits the pod directly, so it never
// transits Cloudflare — health_check.http_path in .do/app.yaml points there.
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

export function middleware(request: NextRequest) {
  const secret = process.env.ORIGIN_LOCK_SECRET ?? "";
  if (!secret) return NextResponse.next();
  if (request.nextUrl.pathname === "/healthz") return NextResponse.next();
  const supplied = request.headers.get("x-origin-lock") ?? "";
  if (!constantTimeEqual(supplied, secret)) {
    return new NextResponse("Forbidden.", { status: 403 });
  }
  return NextResponse.next();
}
