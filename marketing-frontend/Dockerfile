# Two-stage Next.js build for the marketing site (its own App Platform app, at
# the apex). Node 20 matches the runtime the platform's nodejs buildpack ships
# and satisfies Next 16's >=20.9 floor.

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

# ---------------------------------------------------------------------------
# DELTA 1 vs chat-frontend/Dockerfile — THESE `ARG`s ARE LOAD-BEARING.
#
# App Platform passes every BUILD_TIME-scoped env to a Dockerfile build as
# `--build-arg`. A Dockerfile with no matching `ARG` line SILENTLY DISCARDS it:
# no warning, exit 0, green deploy. chat-frontend declares zero ARGs and does
# not need any (it reads nothing at build). Copy that file over this one and
# every value below vanishes — the site would build clean and ship pointing at
# localhost.
#
# NEXT_PUBLIC_* are inlined into the bundle at build and CANNOT be supplied at
# runtime; lib/site.ts hard-fails a production build when one is missing, which
# is what turns "silently wrong site" into "red build". API_ORIGIN is read at
# build too (the corpus numbers, the articles, the sitemap are prerendered).
#
# Pass LITERALS from the app spec, never App Platform's bindable variables
# (${APP_URL}, ${APP_DOMAIN}, ${db.*}): those are RUNTIME-only for a Dockerfile
# build, they pass `doctl apps spec validate`, and they arrive here EMPTY.
# ---------------------------------------------------------------------------
#
# Every NEXT_PUBLIC_* that lib/site.ts reads needs a line here — INCLUDING the
# optional ones. NEXT_PUBLIC_CONTACT_EMAIL has no build-time guard (it falls back
# to a default rather than failing the build), so a missing ARG for it is the
# silent case this whole comment block warns about: set it in the app spec, get a
# GREEN build, and ship the hardcoded consulting@ default anyway. An unguarded
# var is exactly the one that most needs its ARG.
# ---------------------------------------------------------------------------
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_ASSISTANT_ADDRESS
ARG NEXT_PUBLIC_BILLING_LIVE
ARG NEXT_PUBLIC_CONTACT_EMAIL
ARG API_ORIGIN
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL
ENV NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL
ENV NEXT_PUBLIC_ASSISTANT_ADDRESS=$NEXT_PUBLIC_ASSISTANT_ADDRESS
ENV NEXT_PUBLIC_BILLING_LIVE=$NEXT_PUBLIC_BILLING_LIVE
ENV NEXT_PUBLIC_CONTACT_EMAIL=$NEXT_PUBLIC_CONTACT_EMAIL
ENV API_ORIGIN=$API_ORIGIN

RUN npm run build

# ---- Stage 2: runtime ----
FROM node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080
# CRITICAL: Next.js's standalone server defaults HOSTNAME to localhost, which
# means App Platform's health probe (sourced from outside the container) can
# never reach it and the component never goes live.
ENV HOSTNAME=0.0.0.0

# Deliberately NOT re-declaring API_ORIGIN here. It is a RUNTIME env in the app
# spec (the ISR revalidations below re-fetch through it), and an `ENV` baked in
# from the build stage would shadow whatever the spec sets at container start.

# Standalone output bundles only the files needed for `next start`.
# DELTA 3: marketing ships real screenshots under public/, which the standalone
# trace does not include — chat-frontend copies public/ for the same reason.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# ---------------------------------------------------------------------------
# DELTA 2 — the ISR write path. Unlike chat-frontend, this app has ISR: the
# articles pages, the sitemap and the home page's corpus counts revalidate on a
# timer. Next 16 writes to .next/cache/fetch-cache, .next/cache/images, AND
# .next/server/app/*.{html,rsc,meta} — it rewrites the PRERENDERED PAGE IN
# PLACE. Under `USER node` with a root-owned .next, all three EACCES, and Next
# does not crash: it logs a warning and serves the build-time HTML forever. A
# newly published article would simply never appear on the site.
#
# Chown only the .next subtree. server.js, node_modules and public stay
# root-owned and read-only to the runtime user (least privilege — SOC2 CC6.1).
# ---------------------------------------------------------------------------
RUN mkdir -p .next/cache && chown -R node:node .next

USER node

EXPOSE 8080
CMD ["node", "server.js"]
