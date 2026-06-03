# Two-stage Next.js build. We compile against Node 20 (the runtime App
# Platform's nodejs buildpack ships) and run a slim standalone server.

# Base image pinned by immutable multi-arch index digest (not just the
# floating :20-slim tag) so a rebuild can't silently pull a different
# underlying image. Both stages share the same digest. Update it only via a
# reviewed change. Resolve a fresh digest with:
#   docker buildx imagetools inspect node:20-slim --format '{{.Manifest.Digest}}'

# ---- Stage 1: deps + build ----
FROM node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# basePath is applied in next.config.ts when NODE_ENV=production so
# the static asset paths and router know they live at /chat/*.
RUN npm run build

# ---- Stage 2: runtime ----
FROM node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080
# CRITICAL: Next.js's standalone server defaults HOSTNAME to localhost,
# which means App Platform's health probe (sourced from outside the
# container) can never reach it and the component never goes live —
# resulting in a platform-level 404 at /chat. Bind to all interfaces.
ENV HOSTNAME=0.0.0.0

# Standalone output bundles only the files needed for `next start`.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Run as the unprivileged upstream `node` user (UID 1000), not root
# (least privilege — SOC2 CC6.1). The standalone artifacts were copied as
# root but are world-readable, so `node` can read and run server.js. There is
# no ISR/image-optimization in this app, so the server writes nothing under
# .next/cache at runtime and needs no writable copy.
USER node

EXPOSE 8080
CMD ["node", "server.js"]
