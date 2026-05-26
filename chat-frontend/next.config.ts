import type { NextConfig } from "next";

// Production deploy: chat-frontend mounts at /chat under the same domain as
// Django, so basePath tells the router and asset URLs to live there.
// In dev we keep root '/' so the local URL stays http://localhost:3100/.
const isProd = process.env.NODE_ENV === "production";

const nextConfig: NextConfig = {
  basePath: isProd ? "/chat" : undefined,
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
};

export default nextConfig;
