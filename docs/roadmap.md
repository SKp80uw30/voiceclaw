# VoiceClaw Roadmap

## Phase 1 — Core Voice Pipeline (MVP)

Goal: Voice works. Model-agnostic. Deployable.

- [ ] Fork Pipecat → `voice/upstream/pipecat`
- [ ] Fork OpenClaw → `agent/upstream/openclaw`  
- [ ] Pipecat adapter layer (`voice/adapters/`)
- [ ] OpenClaw adapter layer (`agent/adapters/`)
- [ ] Pipecat → OpenClaw HTTP bridge (transcript in, spoken text out)
- [ ] OpenRouter LLM provider wired up
- [ ] Deepgram STT (streaming)
- [ ] Cartesia TTS
- [ ] Basic WebRTC PWA (push-to-talk)
- [ ] Orb state machine (5 states)
- [ ] Railway Phase 1 deploy template
- [ ] `.env.example` with all required keys

## Phase 2 — Voice Bridge Skills

Goal: Skills bridge voice to MCPs cleanly.

- [ ] Skill Builder Skill (meta-skill)
- [ ] `calendar-voice-bridge` (Google Calendar)
- [ ] `email-voice-bridge` (Gmail)
- [ ] Composio MCP integration (OAuth layer)
- [ ] Confirmation UX in voice ("Did you say...?")
- [ ] Tool-running orb state (ring sweep)
- [ ] Railway Phase 2 deploy template

## Phase 3 — PWA Polish + Skills Registry

Goal: Installable, shareable, community-ready.

- [ ] Full PWA manifest + service worker
- [ ] iOS/Android "Add to Home Screen" tested
- [ ] Skills Registry service
- [ ] ClawHub publish integration
- [ ] Full-duplex barge-in (interrupt agent mid-speech)
- [ ] Multi-language STT support
- [ ] Railway Phase 3 deploy template

## Phase 4 — Multi-tenant

Goal: Multiple users, managed auth, SaaS-ready.

- [ ] User auth service
- [ ] Per-user Composio Connect Links
- [ ] Usage metering
- [ ] Managed skill sets per user
- [ ] Railway Phase 4 deploy template

## Upstream Contribution Targets

Things we expect to contribute back to Pipecat or OpenClaw:
- Pipeline state event API (for orb state machine)
- MCP tool bridge pattern
- Voice Bridge Skill spec (propose as standard to OpenClaw community)
