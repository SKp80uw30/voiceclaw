# VoiceClaw — Claude Code Handover

> This document is the complete handover from the Claude.ai planning session to Claude Code for the build phase. Read this in full before writing any code.

## What VoiceClaw Is

VoiceClaw is a voice-first AI agent that solves a gap no existing platform has addressed: the missing bridge between real-time voice and MCP tools. Every platform tried (VAPI, ElevenLabs, Realtime API, ChatGPT, Gemini etc.) treats voice as a bolt-on to a chat model. VoiceClaw is built voice-first.

It sits within the OpenClaw spinoff ecosystem (NemoClaw, PicoClaw, etc.) as the first **modality extension** — not a smaller OpenClaw, but one that can hear and speak.

The core innovation is **Voice Bridge Skills** — SKILL.md files that teach the OpenClaw agent how to translate spoken intent into MCP tool calls with proper context, confirmation policies, and natural speech responses. A **Skill Builder Skill** (meta-skill) can introspect any MCP server's tool schema and auto-generate a Voice Bridge Skill for it.

## Repo

**GitHub:** https://github.com/SKp80uw30/voiceclaw  
**Owner:** SKp80uw30 (FreeDAIY)  
**Default branch:** main  
**Licence:** MIT (Pipecat upstream: BSD-2-Clause, OpenClaw upstream: MIT)

## Architecture (read docs/architecture/overview.md for full detail)

```
PWA (React floating orb)
    │ WebRTC
    ▼
Pipecat Voice Pipeline (Python)
    │ VAD → STT (Deepgram streaming) → OpenClaw → TTS (Cartesia)
    │ OpenRouter API key (model agnostic)
    ▼
OpenClaw Gateway (Node.js, WebChat channel)
    │ Voice Bridge Skills (SKILL.md files)
    │ Memory in workspace Markdown files
    ▼
MCP Tool Layer
    ├── Composio (Meta MCP — OAuth, Gmail, Slack, Calendar etc.)
    └── Custom MCP servers
```

## Current Repo State

The repo was seeded in the planning session. Here is exactly what exists:

```
voiceclaw/
├── README.md                                  ✅ written
├── .env.example                               ✅ written
├── .gitignore                                 ✅ written
├── docs/
│   ├── CLAUDE_CODE_HANDOVER.md                ✅ this file
│   ├── architecture/
│   │   ├── overview.md                        ✅ written
│   │   └── upstream-compatibility.md          ✅ written
│   ├── deployment/
│   │   └── railway.md                         ✅ written
│   ├── skills/
│   │   ├── voice-bridge-skills.md             ✅ written
│   │   └── skill-builder.md                   ✅ written
│   └── roadmap.md                             ✅ written
├── skills/
│   ├── skill-builder/
│   │   └── SKILL.md                           ✅ written
│   └── calendar-voice-bridge/
│       └── SKILL.md                           ✅ written
├── voice/                                     🔲 empty (Pipecat fork goes here)
├── agent/                                     🔲 empty (OpenClaw fork goes here)
├── pwa/                                       🔲 empty (React PWA goes here)
└── infra/                                     🔲 empty (Railway/Docker configs)
```

## Key Architectural Decisions (non-negotiable)

### 1. Upstream Compatibility Layer
Pipecat and OpenClaw are forked but treated as **vendored upstream dependencies**. Our code never reaches into their internals — only through adapters we own.

```
voice/
├── upstream/pipecat/     ← fork lives here, touch minimally
├── adapters/             ← OUR interface to Pipecat
│   ├── pipeline.py       ← VoiceClawPipeline wraps Pipecat
│   ├── transport.py      ← WebRTC transport adapter
│   └── events.py         ← orb state event bridge
└── voiceclaw/            ← VoiceClaw-specific voice logic

agent/
├── upstream/openclaw/    ← fork lives here, touch minimally
├── adapters/             ← OUR interface to OpenClaw
│   ├── gateway.py        ← HTTP bridge: Pipecat → OpenClaw
│   ├── session.py        ← session lifecycle
│   └── skills.py         ← Voice Bridge Skill loader
└── voiceclaw/            ← VoiceClaw-specific agent logic
```

When upstream updates: `git fetch upstream` → merge into `upstream/` dir → run adapter tests → fix only adapters.

### 2. PWA Only — No App Stores
Browser-native WebRTC. React PWA with proper manifest + service worker. Installable on iOS/Android via "Add to Home Screen". No Expo, no React Native, no Capacitor.

### 3. Single OpenRouter Key — Model Agnostic
All LLM calls route through `OPENROUTER_API_KEY`. Pipecat has a native OpenRouter provider. Model is set via `OPENCLAW_MODEL` env var — no code changes to swap models.

### 4. Railway Deployment in Phases
See `docs/deployment/railway.md`. Phase 1 = 2 services (pipecat-backend + openclaw-gateway). Each phase adds a service. The Railway deploy button must work at every phase.

### 5. Voice Bridge Skills are SKILL.md files
Not code. Natural language instruction files that OpenClaw reads before reasoning. The Skill Builder Skill auto-generates them from MCP tool schemas. See `skills/skill-builder/SKILL.md` and `docs/skills/voice-bridge-skills.md`.

## Phase 1 Build Tasks (start here)

These are ordered. Complete them in sequence.

### Task 1: Fork Pipecat into voice/upstream/
```bash
# In the repo root
git remote add pipecat-upstream https://github.com/pipecat-ai/pipecat.git
git fetch pipecat-upstream
git read-tree --prefix=voice/upstream/pipecat/ -u pipecat-upstream/main
git commit -m "chore: add Pipecat upstream fork to voice/upstream/pipecat"
```
Verify: `voice/upstream/pipecat/src/pipecat/` exists.

### Task 2: Fork OpenClaw into agent/upstream/
```bash
git remote add openclaw-upstream https://github.com/openclaw/openclaw.git
git fetch openclaw-upstream
git read-tree --prefix=agent/upstream/openclaw/ -u openclaw-upstream/main
git commit -m "chore: add OpenClaw upstream fork to agent/upstream/openclaw"
```
Verify: `agent/upstream/openclaw/src/` exists.

### Task 3: Pipecat Adapter Layer
Create `voice/adapters/pipeline.py` — a `VoiceClawPipeline` class that:
- Wraps Pipecat's `Pipeline` with our default component chain: SileroVAD → Deepgram STT → OpenRouterLLM → CartesiaTTS
- Exposes `on_state_change(state: OrbState)` event for the PWA orb
- Exposes `on_transcript(text: str)` for routing to OpenClaw
- Reads all config from env vars (no hardcoded keys)

OrbState enum: `idle | listening | thinking | tool_running | speaking`

Create `voice/adapters/transport.py` — WebRTC transport adapter using Pipecat's built-in WebRTC support (`pipecat[webrtc]`).

Create `voice/adapters/events.py` — maps Pipecat pipeline frame types to OrbState transitions.

### Task 4: OpenClaw Adapter Layer
Create `agent/adapters/gateway.py` — HTTP bridge:
- Exposes `POST /transcript` — receives transcript from Pipecat, routes to OpenClaw WebChat session, returns spoken response text
- Manages OpenClaw session lifecycle
- Loads Voice Bridge Skills before each request

Create `agent/adapters/session.py` — per-user session management.
Create `agent/adapters/skills.py` — scans `skills/` dir, loads relevant SKILL.md files into OpenClaw context.

### Task 5: Pipecat Server Entry Point
Create `voice/voiceclaw/server.py`:
- FastAPI app
- `GET /` — serves the PWA (index.html)
- `POST /offer` — WebRTC SDP offer/answer for browser connection
- `GET /state` — SSE stream of OrbState events for the PWA orb
- On new WebRTC connection: instantiate VoiceClawPipeline, connect to OpenClaw gateway

### Task 6: Basic PWA Orb
Create `pwa/` as a Vite + React PWA:
- Single page: floating orb circle, centred
- Orb renders 5 states via CSS animations (see state machine in overview.md)
- Push-to-talk button (hold to speak, release to send) for Phase 1
- Connects to Pipecat server via Pipecat React SDK (`@pipecat-ai/client-react`)
- Subscribes to `/state` SSE for orb state transitions
- PWA manifest + service worker (Vite PWA plugin)

### Task 7: Docker Compose (local dev)
Create `docker-compose.yml`:
```yaml
services:
  pipecat-backend:
    build: ./voice
    ports: ["8000:8000"]
    env_file: .env
  openclaw-gateway:
    build: ./agent
    ports: ["18789:18789"]
    env_file: .env
```

### Task 8: Railway Phase 1 Config
Create `infra/railway.toml` and `infra/docker-compose.railway.yml` for the Phase 1 Railway deploy template.

## Environment Variables

See `.env.example` in the repo root. The minimum set for Phase 1:

```
OPENROUTER_API_KEY=     # required
OPENCLAW_MODEL=         # required (e.g. anthropic/claude-sonnet-4-5)
DEEPGRAM_API_KEY=       # required
CARTESIA_API_KEY=       # required
COMPOSIO_API_KEY=       # optional for Phase 1, required for Phase 2
```

## Tech Stack Versions to Use

| Component | Package | Version |
|---|---|---|
| Pipecat | `pipecat-ai[webrtc,openrouter,deepgram,cartesia,silero]` | latest |
| Python | `>=3.12` | |
| Node.js | `>=22` (OpenClaw requirement) | |
| React | `^19` | |
| Vite | `^6` | |
| Pipecat React SDK | `@pipecat-ai/client-react` | latest |
| FastAPI | `fastapi[standard]` | latest |
| uv | package manager for Python | latest |

## Licence Compliance

- VoiceClaw code: MIT
- Pipecat upstream (`voice/upstream/pipecat/`): BSD-2-Clause — keep their LICENSE file, add attribution in our README (already done)
- OpenClaw upstream (`agent/upstream/openclaw/`): MIT — keep their LICENSE file
- Do not claim authorship of upstream files
- Adapter and voiceclaw/ directories are fully ours under MIT

## Key Files to Read Before Coding

In order:
1. `docs/architecture/overview.md` — full system diagram and data flow
2. `docs/architecture/upstream-compatibility.md` — adapter layer pattern
3. `docs/skills/voice-bridge-skills.md` — what skills are and how they work
4. `skills/calendar-voice-bridge/SKILL.md` — example of a complete bridge skill
5. `docs/deployment/railway.md` — Railway phase structure
6. `docs/roadmap.md` — full milestone list

## Context From Planning Conversation

- **Owner has tried:** VAPI, ElevenLabs, Realtime API, ChatGPT voice, Claude voice, Gemini Live — none felt right. The diagnosis: voice is bolted on, and there's no skill layer connecting voice to MCP tools.
- **PWA is non-negotiable** — voice will be used primarily on mobile. No App Store pain.
- **Railway one-click deploy is a first-class goal** — not an afterthought. Each phase milestone = working Railway deploy button.
- **OpenRouter is the model layer** — one key, swap models freely. Not locked to any provider.
- **Composio is the recommended Meta MCP** for OAuth tool connections but is not open source so not bundled — referenced in docs, documented in `.env.example`, users bring their own key.
- **The skill-builder-skill is the product moat** — publishing it to ClawHub early drives community adoption before the full product launches.
- **VoiceClaw is positioned as a modality extension** in the OpenClaw ecosystem, not just another size variant. This framing matters for the README and community positioning.

## Questions to Resolve During Build

- [ ] Does Pipecat's WebRTC transport support the browser push-to-talk pattern cleanly, or do we need a custom signalling layer?
- [ ] Does OpenClaw's WebChat channel accept HTTP POST cleanly enough for the gateway adapter, or do we need WebSocket?
- [ ] What is the exact Pipecat frame type that maps to each OrbState? (Check Pipecat source in `voice/upstream/pipecat/src/pipecat/frames/`)
- [ ] Does Pipecat's OpenRouter provider support streaming tool calls, or text only? (Needed for tool_running orb state)

## Definition of Phase 1 Done

- [ ] `docker compose up` starts both services with no errors
- [ ] Browser opens PWA, orb is visible
- [ ] Hold push-to-talk button, speak a sentence, release
- [ ] Orb transitions: idle → listening → thinking → speaking
- [ ] Agent responds via audio in browser
- [ ] Model can be swapped by changing `OPENCLAW_MODEL` in `.env` only
- [ ] `railway up` (or deploy button) deploys Phase 1 to Railway successfully
