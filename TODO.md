# VoiceClaw — Build Plan

> **Workflow:** This is the single source of truth for build progress. At the start of each session, read this file and pick up the next unchecked task. When a task is complete, tested, and approved, check it off. Complete all tasks in a phase before starting the next.
>
> Each phase ends with a working Railway deploy. Do not mark a phase complete until `railway up` succeeds.

---

## Phase 1 — Core Voice Pipeline (MVP)

**Goal:** Voice works end-to-end. Model-agnostic. Locally runnable. Railway-deployable.

### 1.1 — Upstream Forks

- [x] **Fork Pipecat** into `voice/upstream/pipecat/` using `git read-tree`
  - Verified: `voice/upstream/pipecat/src/pipecat/` exists
- [x] **Fork OpenClaw** into `agent/upstream/openclaw/` using `git read-tree`
  - Verified: `agent/upstream/openclaw/` exists (Node.js/TypeScript monorepo)

### 1.2 — Pipecat Adapter Layer

- [x] `voice/adapters/events.py` — `OrbState` enum + `OrbStateObserver` (BaseObserver subclass)
  - Frame→state mapping confirmed from Pipecat source. Documented in `voice/CLAUDE.md`.
- [x] `voice/adapters/transport.py` — WebRTC transport adapter (`create_connection`, `create_transport`)
  - `SmallWebRTCTransport` supports the pattern cleanly. Audio-only params set.
- [x] `voice/adapters/pipeline.py` — `VoiceClawPipeline` + `OpenClawBridgeProcessor`
  - Chain: transport.input → STT → OpenClawBridgeProcessor → TTS → transport.output
  - `OpenClawBridgeProcessor` replaces LLM slot; calls `on_transcript` callback to OpenClaw
  - All config from env vars. 12/12 tests passing.

### 1.3 — OpenClaw Adapter Layer

- [x] `agent/adapters/skills.py` — scans `skills/` for SKILL.md files, returns concatenated context string
- [x] `agent/adapters/session.py` — per-session lifecycle, derives session key from pc_id, injects skills
- [x] `agent/adapters/gateway.py` — WebSocket client, full v3 challenge/sign/hello-ok handshake,
  chat.send + delta event collection. 25/25 tests passing.
- [x] `agent/adapters/device.py` — Ed25519 device identity (mirrors OpenClaw TS reference exactly)

### 1.4 — Pipecat Server

- [ ] `voice/voiceclaw/server.py` — FastAPI app
  - `GET /` → serves PWA `index.html`
  - `POST /offer` → WebRTC SDP offer/answer
  - `GET /state` → SSE stream of OrbState events
  - On new WebRTC connection: instantiate `VoiceClawPipeline`, connect to OpenClaw gateway
- [ ] `voice/pyproject.toml` (uv) — all Python deps declared

### 1.5 — PWA Orb UI (see investigation note below)

> **Investigation required before building:** Pipecat ships a `@pipecat-ai/voice-ui-kit` (React, BSD-2-Clause, built on Tailwind 4 + Shadcn). It provides `VoiceVisualizer`, `ConnectButton`, `UserAudioControl`, and a full `ConsoleTemplate`. It uses `small-WebRTC` or Daily as transport, and integrates with `@pipecat-ai/client-react`.
>
> **The kit does NOT ship a floating orb component.** It is console/panel style. Options:
> - **Option A (recommended for MVP):** Use `voice-ui-kit` `ConsoleTemplate` as the Phase 1 UI. Fast to ship, tested, supports all orb states via `VoiceVisualizer`. Replace with custom orb in Phase 3.
> - **Option B:** Build the custom floating orb from scratch now using `@pipecat-ai/client-react` hooks, skipping the kit's templates.
>
> **Decision needed from owner before starting 1.5.** Default plan below assumes Option A.

- [x] **Owner decision recorded:** Option A — use `ConsoleTemplate` for Phase 1 MVP. Custom floating orb deferred to Phase 3.
- [ ] Scaffold `pwa/` with Vite + React + Tailwind 4
- [ ] Install `@pipecat-ai/voice-ui-kit`, `@pipecat-ai/client-react`, `@pipecat-ai/client-js`, `small-webrtc`
- [ ] **(Option A)** Wrap `ConsoleTemplate` + `ThemeProvider`, point at Pipecat server `/offer` endpoint
- [ ] **(Option B)** Build custom floating orb, wire 5 OrbStates to CSS animations, subscribe to `/state` SSE
- [ ] `pwa/vite.config.ts` — `vite-plugin-pwa` for manifest + service worker

### 1.6 — Local Dev

- [ ] `docker-compose.yml` at repo root
  - `pipecat-backend` service: `./voice`, port 8000
  - `openclaw-gateway` service: `./agent`, port 18789
  - Both consume `.env`
- [ ] `voice/Dockerfile`
- [ ] `agent/Dockerfile`
- [ ] Smoke test: `docker compose up` → no errors, PWA loads at `http://localhost:8000`

### 1.7 — Railway Phase 1

- [ ] `infra/railway.toml`
- [ ] `infra/docker-compose.railway.yml`
- [ ] Deploy to Railway and verify deploy button works

### Phase 1 Acceptance Criteria

- [ ] `docker compose up` starts both services with no errors
- [ ] Browser opens PWA, orb / voice UI is visible
- [ ] Hold push-to-talk (or equivalent in chosen UI), speak a sentence, release
- [ ] Orb/UI transitions: idle → listening → thinking → speaking
- [ ] Agent responds via audio in browser
- [ ] Model can be swapped by changing `OPENCLAW_MODEL` in `.env` only — no code changes
- [ ] `railway up` (or deploy button) deploys Phase 1 to Railway successfully

---

## Phase 2 — Voice Bridge Skills

**Goal:** Skills cleanly bridge spoken intent to MCP tool calls. Confirmation UX works by voice.

### 2.1 — Composio Integration

- [ ] Document Composio MCP setup in `docs/skills/composio.md`
- [ ] Add `COMPOSIO_API_KEY` wiring to OpenClaw adapter
- [ ] Smoke test: calendar tool reachable via Composio MCP

### 2.2 — Skill Loader Improvements

- [ ] `agent/adapters/skills.py` — intent-based skill selection (load only relevant skills per transcript, not all)
- [ ] Skill hot-reload: detect SKILL.md changes without restarting gateway

### 2.3 — Calendar Voice Bridge Skill

- [ ] Review and validate `skills/calendar-voice-bridge/SKILL.md` against live Composio Google Calendar tool schema
- [ ] Integration test: "What's on my calendar tomorrow?" → spoken response

### 2.4 — Email Voice Bridge Skill

- [ ] `skills/email-voice-bridge/SKILL.md` — generated via Skill Builder Skill from Gmail MCP schema
- [ ] Integration test: "Read my latest email" → spoken response

### 2.5 — Confirmation UX

- [ ] Design voice confirmation pattern: agent asks "Did you say [action]? Say yes to confirm."
- [ ] Implement in OpenClaw adapter: hold response, re-prompt for confirmation on destructive ops
- [ ] `tool_running` OrbState wires up to ring sweep animation

### 2.6 — Railway Phase 2

- [ ] Update `infra/` for Phase 2
- [ ] Deploy and verify

### Phase 2 Acceptance Criteria

- [ ] "Schedule a meeting tomorrow at 3pm" → confirmation prompt → confirm → calendar event created → spoken confirmation
- [ ] "Read my latest email" → spoken summary of most recent email
- [ ] `tool_running` orb state visible during MCP call
- [ ] `railway up` deploys Phase 2 successfully

---

## Phase 3 — PWA Polish + Skills Registry

**Goal:** Installable on mobile home screen. Community-ready skill sharing.

### 3.1 — Custom Floating Orb (if deferred from Phase 1)

- [ ] Build custom floating orb if Phase 1 used `ConsoleTemplate`
- [ ] 5 OrbState CSS animations
- [ ] Full-duplex barge-in (interrupt agent mid-speech)
- [ ] Mobile-first layout

### 3.2 — PWA Completeness

- [ ] PWA manifest with all required icons
- [ ] Service worker caching strategy
- [ ] Test "Add to Home Screen" on iOS Safari and Android Chrome
- [ ] Offline graceful degradation (show disconnected state, not blank screen)

### 3.3 — Skill Builder Skill UX

- [ ] Test Skill Builder Skill end-to-end: "Build a voice skill for my Notion MCP"
- [ ] Verify generated SKILL.md is valid and loads correctly
- [ ] Publish Skill Builder Skill to ClawHub (product moat — do this early)

### 3.4 — Skills Registry Service

- [ ] `skills-registry/` service — API for browsing + installing skills
- [ ] ClawHub publish integration
- [ ] Railway Phase 3 config

### Phase 3 Acceptance Criteria

- [ ] VoiceClaw installable on iOS and Android via "Add to Home Screen"
- [ ] Custom floating orb running (if applicable)
- [ ] Skill Builder Skill published to ClawHub
- [ ] `railway up` deploys Phase 3 successfully

---

## Phase 4 — Multi-tenant / SaaS

**Goal:** Multiple users, managed OAuth per user, usage metering.

- [ ] Auth service (JWT or session-based)
- [ ] Per-user Composio Connect Links (OAuth tool connections)
- [ ] Usage metering (track LLM + STT + TTS costs per user)
- [ ] Managed skill sets per user
- [ ] Railway Phase 4 config

### Phase 4 Acceptance Criteria

- [ ] Two separate users can log in, each with their own tool connections and skill sets
- [ ] `railway up` deploys Phase 4 successfully

---

## Open Questions Log

Track answers here as they are resolved. Also document in `docs/architecture/`.

| Question | Status | Answer / Notes |
|---|---|---|
| Does Pipecat WebRTC transport support push-to-talk cleanly? | ⬜ Open | `SmallWebRTCTransport` exists in `pipecat.transports.network.small_webrtc` — needs runtime testing to confirm PTT pattern |
| Does OpenClaw WebChat accept HTTP POST or need WebSocket? | ✅ Resolved | **WebSocket only.** Full WS protocol in `agent/upstream/openclaw/docs/gateway/protocol.md`. Connect → challenge/response handshake → JSON frames. Port 18789. See `agent/CLAUDE.md`. |
| Which Pipecat frame types map to each OrbState? | ✅ Resolved | `idle`=`BotStoppedSpeakingFrame`, `listening`=`VADUserStartedSpeakingFrame`, `thinking`=`UserStoppedSpeakingFrame`/`LLMFullResponseStartFrame`, `tool_running`=`FunctionCallsStartedFrame`, `speaking`=`TTSStartedFrame`. See `voice/CLAUDE.md`. |
| Does Pipecat's OpenRouter provider support streaming tool calls? | ⬜ Open | `FunctionCallInProgressFrame` and `FunctionCallsStartedFrame` exist in Pipecat — needs testing with OpenRouter specifically |
| voice-ui-kit for MVP orb — Option A (ConsoleTemplate) or Option B (custom)? | ✅ Resolved | Option A — ConsoleTemplate for Phase 1, custom orb in Phase 3 |
