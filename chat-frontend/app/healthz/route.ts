// App Platform's container health probe hits the pod directly — no
// Cloudflare, no X-Origin-Lock header — so it needs a path the origin-lock
// middleware exempts. Referenced by the chat-frontend component's
// health_check.http_path in .do/app.yaml; keep the two in sync.
export function GET() {
  return Response.json({ status: "ok" });
}
