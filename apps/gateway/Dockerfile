# ─────────────────────────────────────────────────────────────────
# AG3NT Gateway — multi-stage Docker build
# Build context: project root (set by docker-compose.yml)
# ─────────────────────────────────────────────────────────────────
FROM node:22-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 make g++ && rm -rf /var/lib/apt/lists/*

# Install dependencies
FROM base AS deps
COPY apps/gateway/package.json apps/gateway/package-lock.json ./
RUN npm ci --omit=dev

# Build stage (TypeScript → JavaScript)
FROM base AS build
COPY apps/gateway/package.json apps/gateway/package-lock.json ./
RUN npm ci
COPY apps/gateway/tsconfig.json ./
COPY apps/gateway/src/ src/
RUN npx tsc -p tsconfig.json

# Production image
FROM node:22-slim AS runtime
WORKDIR /app

# Install runtime dependency for better-sqlite3
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r ag3nt && useradd -r -g ag3nt -m ag3nt
RUN mkdir -p /home/ag3nt/.ag3nt/data /home/ag3nt/.ag3nt/memory && \
    chown -R ag3nt:ag3nt /home/ag3nt

# Copy production node_modules and compiled JS
COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/package.json ./

# Environment
ENV NODE_ENV=production
ENV AG3NT_GATEWAY_HOST=0.0.0.0
ENV AG3NT_GATEWAY_PORT=18789

EXPOSE 18789

USER ag3nt

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://localhost:18789/api/health').then(r=>{if(!r.ok)throw 1}).catch(()=>process.exit(1))"

CMD ["node", "dist/index.js"]
