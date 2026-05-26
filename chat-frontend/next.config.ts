import type { NextConfig } from "next";

// The Next.js app serves the whole frontend at the root of corpus.nick.law
// in production (App Platform routes / → chat-frontend; /api and /admin
// go to Django). No basePath: same URL in dev and prod.
const isProd = process.env.NODE_ENV === "production";

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
};

export default nextConfig;
