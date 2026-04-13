# OpenMAIC Sidecar — Multi-agent Interactive Classroom
# Runs on internal Docker network only (not exposed to internet).
# Django proxy authenticates requests and injects API keys.

FROM node:20-alpine AS base
RUN apk add --no-cache git

# ── Clone & Install ───────────────────────────────────────────────────
FROM base AS deps
WORKDIR /app
RUN git clone --depth 1 https://github.com/THU-MAIC/OpenMAIC.git .
RUN npm ci --prefer-offline

# ── Build ─────────────────────────────────────────────────────────────
FROM deps AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
# Build standalone Next.js output
RUN npm run build

# ── Production ────────────────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy standalone build output
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/api/health || exit 1

CMD ["node", "server.js"]
