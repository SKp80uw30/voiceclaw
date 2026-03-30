# syntax=docker/dockerfile:1.7
# VoiceClaw — agent/Dockerfile
# SPDX-License-Identifier: MIT
#
# Build context: ./agent  (the agent/ sub-directory of the repo root)
# Produces: OpenClaw gateway server on port 18789.
#
# Adapts agent/upstream/openclaw/Dockerfile for use within the ./agent context.
# All COPY paths are prefixed with upstream/openclaw/ instead of ./.
#
# Usage (from repo root):
#   docker build -f agent/Dockerfile -t voiceclaw-agent ./agent

ARG OPENCLAW_NODE_IMAGE="node:24-bookworm"
ARG OPENCLAW_NODE_SLIM_IMAGE="node:24-bookworm-slim"
ARG OPENCLAW_DOCKER_APT_UPGRADE=1


# ── Stage 1: ext-deps — extract extension package.json files ─────────────────
FROM ${OPENCLAW_NODE_IMAGE} AS ext-deps

ARG OPENCLAW_EXTENSIONS=""
COPY upstream/openclaw/extensions /tmp/extensions

RUN mkdir -p /out && \
    for ext in $OPENCLAW_EXTENSIONS; do \
      if [ -f "/tmp/extensions/$ext/package.json" ]; then \
        mkdir -p "/out/$ext" && \
        cp "/tmp/extensions/$ext/package.json" "/out/$ext/package.json"; \
      fi; \
    done


# ── Stage 2: build ────────────────────────────────────────────────────────────
FROM ${OPENCLAW_NODE_IMAGE} AS build

# Install Bun (required by OpenClaw build scripts)
RUN set -eux; \
    for attempt in 1 2 3 4 5; do \
      if curl --retry 5 --retry-all-errors --retry-delay 2 -fsSL https://bun.sh/install | bash; then \
        break; \
      fi; \
      [ "$attempt" -eq 5 ] && exit 1; \
      sleep $((attempt * 2)); \
    done

ENV PATH="/root/.bun/bin:${PATH}"

RUN corepack enable

WORKDIR /app

# Install deps (layer-cached until lockfile changes)
COPY upstream/openclaw/package.json \
     upstream/openclaw/pnpm-lock.yaml \
     upstream/openclaw/pnpm-workspace.yaml \
     upstream/openclaw/.npmrc \
     ./
COPY upstream/openclaw/ui/package.json ./ui/package.json
COPY upstream/openclaw/patches ./patches
COPY --from=ext-deps /out/ ./extensions/

RUN --mount=type=cache,id=openclaw-pnpm-store,target=/root/.local/share/pnpm/store,sharing=locked \
    NODE_OPTIONS=--max-old-space-size=2048 pnpm install --frozen-lockfile

# Copy full source (after deps to benefit from layer cache)
COPY upstream/openclaw/ .

# Normalize extension file modes before runtime COPY
RUN for dir in /app/extensions /app/.agent /app/.agents; do \
      if [ -d "$dir" ]; then \
        find "$dir" -type d -exec chmod 755 {} +; \
        find "$dir" -type f -exec chmod 644 {} +; \
      fi; \
    done

# A2UI bundle may fail under QEMU cross-compilation; stub it so arm64/amd64
# cross-arch local builds still succeed.
RUN pnpm canvas:a2ui:bundle || \
    (echo "A2UI bundle: creating stub (non-fatal)" && \
     mkdir -p src/canvas-host/a2ui && \
     echo "/* A2UI bundle unavailable in this build */" > src/canvas-host/a2ui/a2ui.bundle.js && \
     echo "stub" > src/canvas-host/a2ui/.bundle.hash && \
     rm -rf vendor/a2ui apps/shared/OpenClawKit/Tools/CanvasA2UI)

RUN pnpm build:docker
ENV OPENCLAW_PREFER_PNPM=1
RUN pnpm ui:build


# ── Stage 3: prune dev deps ───────────────────────────────────────────────────
FROM build AS runtime-assets

RUN CI=true pnpm prune --prod && \
    find dist -type f \( -name '*.d.ts' -o -name '*.d.mts' -o -name '*.d.cts' -o -name '*.map' \) -delete


# ── Stage 4: runtime ──────────────────────────────────────────────────────────
FROM ${OPENCLAW_NODE_SLIM_IMAGE} AS runtime

ARG OPENCLAW_DOCKER_APT_UPGRADE

RUN --mount=type=cache,id=openclaw-bookworm-apt-cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=openclaw-bookworm-apt-lists,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    if [ "${OPENCLAW_DOCKER_APT_UPGRADE}" != "0" ]; then \
      DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --no-install-recommends; \
    fi && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      procps hostname curl git lsof openssl

WORKDIR /app
RUN chown node:node /app && \
    install -d -m 0700 -o node -g node /home/node/.openclaw && \
    echo '{"gateway":{"controlUi":{"dangerouslyAllowHostHeaderOriginFallback":true,"dangerouslyDisableDeviceAuth":true}}}' \
      > /home/node/.openclaw/openclaw.json && \
    chown node:node /home/node/.openclaw/openclaw.json

COPY --from=runtime-assets --chown=node:node /app/dist ./dist
COPY --from=runtime-assets --chown=node:node /app/node_modules ./node_modules
COPY --from=runtime-assets --chown=node:node /app/package.json .
COPY --from=runtime-assets --chown=node:node /app/openclaw.mjs .
COPY --from=runtime-assets --chown=node:node /app/extensions ./extensions
COPY --from=runtime-assets --chown=node:node /app/docs ./docs

# Copy upstream skills (OpenClaw built-in skills)
COPY --from=runtime-assets --chown=node:node /app/skills ./skills

ENV OPENCLAW_BUNDLED_PLUGINS_DIR=/app/extensions
ENV COREPACK_HOME=/usr/local/share/corepack
ENV NODE_ENV=production

RUN install -d -m 0755 "$COREPACK_HOME" && \
    corepack enable && \
    corepack prepare "$(node -p "require('./package.json').packageManager")" --activate && \
    chmod -R a+rX "$COREPACK_HOME"

RUN ln -sf /app/openclaw.mjs /usr/local/bin/openclaw && \
    chmod 755 /app/openclaw.mjs

USER node

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:18789/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

EXPOSE 18789

# Default: bind to all interfaces so docker bridge networking works.
# Use --bind loopback for host-network deployments.
CMD ["node", "openclaw.mjs", "gateway", "--bind", "lan", "--allow-unconfigured"]
