# VoiceClaw — Claude Code Instructions

Read this before writing any code in this repo.

## Workflow

**`TODO.md` at the repo root is the single source of truth for what to build next.**

At the start of every session:
1. Read `TODO.md` — pick up the next unchecked task in the current phase
2. Read `voice/CLAUDE.md` before writing code in the voice layer
3. Build, test, get approval
4. Check the task off in `TODO.md`
5. Complete all tasks in a phase (including Railway deploy) before starting the next phase

---

## What This Project Is

VoiceClaw is a **voice-first AI agent**. The user speaks, Pipecat handles real-time audio (STT/TTS), an LLM via OpenRouter handles reasoning and tool calls, and Voice Bridge Skills (`SKILL.md` files) teach the agent how to translate spoken intent into actions.

The core innovation is **Voice Bridge Skills**: `SKILL.md` files injected as system prompt context that teach the LLM how to handle specific domains (calendar, email, etc.). A **Skill Builder Skill** (meta-skill) auto-generates these from any MCP server's tool schema.

---

## Architecture

```
PWA (React — orb UI)  →WebRTC→  Pipecat Voice Pipeline (Python)
                                      │ VAD → STT → LLM (OpenRouter) → TTS
                                      │
                                 Skills injected as system prompt context
                                      │
                                 MCP Tool Layer (Composio + custom) — Phase 2
```

### Directory layout

```
voice/
├── upstream/pipecat/   ← Pipecat fork — touch minimally
├── adapters/           ← OUR interface to Pipecat (pipeline.py, transport.py, events.py, skills.py)
└── voiceclaw/          ← VoiceClaw voice logic (server.py)

pwa/                    ← Vite + React PWA (orb UI)
skills/                 ← Voice Bridge Skill .md files
infra/                  ← Railway + Docker configs
```

---

## Non-negotiable Architectural Rules

1. **Adapter layer only.** Never import directly from `voice/upstream/pipecat/` internals. All access goes through `voice/adapters/`. Use Pipecat's public API only.

2. **No hardcoded keys.** Every API key and model name is read from environment variables. See `.env.example`.

3. **PWA only — no native apps.** Browser-native WebRTC. No Expo, React Native, or Capacitor.

4. **OpenRouter for all LLM calls.** One key (`OPENROUTER_API_KEY`), model set via `LLM_MODEL` env var.

5. **Railway deploy must work at every phase.** Phase 1 = 1 service (`pipecat-backend`).

6. **Voice Bridge Skills are SKILL.md files — not code.** Natural language instruction files injected into the LLM system prompt via `voice/adapters/skills.py`.

7. **Stay aligned with upstream Pipecat public APIs.** When a seam doesn't exist, add it via an Observer or FrameProcessor subclass in `adapters/` — never by patching upstream code.

---

## Environment Variables

```
OPENROUTER_API_KEY=     # required
LLM_MODEL=              # required, e.g. anthropic/claude-sonnet-4-6
DEEPGRAM_API_KEY=       # required
CARTESIA_API_KEY=       # required
CARTESIA_VOICE_ID=      # optional — override TTS voice
LOG_LEVEL=              # optional — debug|info|warning|error
```

---

## Tech Stack

| Component | Package / version |
|---|---|
| Python | `>=3.12` |
| Python package manager | `uv` |
| Pipecat | `pipecat-ai[webrtc,deepgram,cartesia,silero,openai]` local fork |
| Web framework | `fastapi[standard]` latest |
| React | `^19` |
| Vite | `^6` |
| Pipecat JS SDK | `@pipecat-ai/client-react` + `@pipecat-ai/voice-ui-kit` latest |

---

## OrbState Machine

Five states driven by Pipecat pipeline frame events, exposed via SSE at `GET /state/{pc_id}`:

| State | Trigger |
|---|---|
| `idle` | `BotStoppedSpeakingFrame` / pipeline start |
| `listening` | `VADUserStartedSpeakingFrame` |
| `thinking` | `UserStoppedSpeakingFrame` / `LLMFullResponseStartFrame` |
| `tool_running` | `FunctionCallsStartedFrame` |
| `speaking` | `TTSStartedFrame` |
