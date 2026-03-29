# Railway Deployment Guide

VoiceClaw is designed for one-click Railway deployment. The deployment is phased — each phase adds a Railway service and keeps the deploy button working.

## Phase 1: Core Voice Agent (MVP)

**Services:** 2
- `pipecat-backend` — Python voice pipeline
- `openclaw-gateway` — Node.js agent gateway

**What you get:**
- Working voice agent in browser
- OpenRouter model routing
- Basic MCP tool support
- Push-to-talk PWA (served as static from pipecat-backend)

**Environment variables needed:**
```
OPENROUTER_API_KEY=
DEEPGRAM_API_KEY=
CARTESIA_API_KEY=
OPENCLAW_MODEL=openai/gpt-4o  # or any OpenRouter model slug
```

[![Deploy Phase 1 on Railway](https://railway.com/button.svg)](https://railway.com/template/voiceclaw-phase1)

## Phase 2: PWA + Skills Registry

**Services:** 3 (adds)
- `voiceclaw-pwa` — React PWA static site

**What you get:**
- Standalone PWA with proper manifest + service worker
- Installable on iOS/Android home screen
- Full orb state machine UI
- Persistent sessions

## Phase 3: Skills Registry Service

**Services:** 4 (adds)
- `skills-registry` — Voice Bridge Skills API

**What you get:**
- Browse and install Voice Bridge Skills
- Skill Builder Skill UI
- Community skill sharing
- ClawHub integration

## Phase 4: Multi-tenant / SaaS

**Services:** 5 (adds)
- `auth-service` — User auth + Composio OAuth management

**What you get:**
- Multi-user support
- Per-user tool connections via Composio Connect Links
- Usage metering
- Managed skill sets per user

## railway.toml Structure

```toml
[build]
docker_compose_file = "docker-compose.railway.yml"

[[services]]
name = "pipecat-backend"
source = "voice/"
start_command = "python -m voiceclaw.server"

[[services]]
name = "openclaw-gateway"
source = "agent/"
start_command = "openclaw gateway start"
```

## Local Development

```bash
# Clone
git clone https://github.com/SKp80uw30/voiceclaw
cd voiceclaw

# Copy env
cp .env.example .env
# Fill in your API keys

# Start all services
docker compose up

# Or individually
cd voice && uv run python -m voiceclaw.server
cd agent && openclaw gateway start
cd pwa && npm run dev
```
