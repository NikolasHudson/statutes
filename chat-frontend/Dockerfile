# Two-stage Next.js build. We compile against Node 20 (the runtime App
# Platform's nodejs buildpack ships) and run a slim standalone server.

# ---- Stage 1: deps + build ----
FROM node:20-slim AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# basePath is applied in next.config.ts when NODE_ENV=production so
# the static asset paths and router know they live at /chat/*.
RUN npm run build

# ---- Stage 2: runtime ----
FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080

# Standalone output bundles only the files needed for `next start`.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 8080
CMD ["node", "server.js"]
