# syntax=docker/dockerfile:1.7
# VoiceClaw — voice/Dockerfile
# SPDX-License-Identifier: MIT
#
# Build context: repo root (.)
# Produces: Pipecat FastAPI server + embedded PWA static files.
#
# Usage (from repo root):
#   docker build -f voice/Dockerfile -t voiceclaw-voice .

# ── Stage 1: Build PWA ────────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS pwa-build

WORKDIR /pwa

# Install deps first (layer-cached until package files change)
COPY pwa/package.json pwa/package-lock.json* ./
# --legacy-peer-deps: vite-plugin-pwa@1.2.0 peer dep doesn't yet list Vite 8
RUN npm ci --legacy-peer-deps

COPY pwa/ ./
RUN npm run build


# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

# OpenCV (cv2) is imported by Pipecat's SmallWebRTC transport and needs
# X11/XCB libraries not included in bookworm-slim.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxcb1 \
        libxext6 \
        libsm6 \
        libxrender1 \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy voice package manifest + lockfile for dependency layer caching.
# pipecat-ai is a local path dep → voice/upstream/pipecat must be present.
COPY voice/pyproject.toml voice/uv.lock ./voice/
COPY voice/upstream/pipecat ./voice/upstream/pipecat

# Install Python dependencies into a project-local venv.
RUN cd voice && uv sync --frozen --no-dev

# Copy remaining voice source
COPY voice/adapters ./voice/adapters
COPY voice/voiceclaw ./voice/voiceclaw

# Copy agent adapters so `from agent.adapters.X import Y` resolves at runtime.
# Python 3 namespace packages — no agent/__init__.py required.
# VoiceClaw connects to OpenClaw as an external client; no upstream internals.
COPY agent/adapters ./agent/adapters

# Copy Voice Bridge Skills
COPY skills ./skills

# Embed the built PWA so `GET /` serves the orb UI without a separate volume.
COPY --from=pwa-build /pwa/dist ./pwa/dist

# PYTHONPATH=/app lets `import agent.adapters.*` resolve without installing the
# agent package. uv manages voice's venv at /app/voice/.venv.
ENV PYTHONPATH=/app
ENV VOICECLAW_PWA_DIR=/app/pwa/dist

EXPOSE 8000

WORKDIR /app/voice
CMD ["uv", "run", "uvicorn", "voiceclaw.server:app", \
     "--host", "0.0.0.0", "--port", "8000"]
