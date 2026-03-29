# VoiceClaw — Claude Code Instructions

Read this before writing any code in this repo.

## Workflow

**`TODO.md` at the repo root is the single source of truth for what to build next.**

At the start of every session:
1. Read `TODO.md` — pick up the next unchecked task in the current phase
2. Read the relevant sub-directory CLAUDE.md before writing code in that area:
   - `voice/CLAUDE.md` — Pipecat integration layer
   - `agent/CLAUDE.md` — OpenClaw integration layer
3. Build, test, get approval
4. Check the task off in `TODO.md`
5. Complete all tasks in a phase (including Railway deploy) before starting the next phase

Full planning context: `docs/CLAUDE_CODE_HANDOVER.md`

---

## What This Project Is

VoiceClaw is a **voice-first AI agent** that bridges real-time voice (Pipecat) with MCP tools (via OpenClaw). It is a modality extension in the OpenClaw spinoff ecosystem — not a smaller OpenClaw, but one that can hear and speak.

The core innovation is **Voice Bridge Skills**: `SKILL.md` files that teach OpenClaw how to translate spoken intent into MCP tool calls. A **Skill Builder Skill** (meta-skill) auto-generates these from any MCP server's tool schema.

---

## Architecture (do not violate)

```
PWA (React — orb UI)  →WebRTC→  Pipecat Voice Pipeline (Python)
                                      │ VAD → STT → OpenClaw → TTS
                                      ▼
                                 OpenClaw Gateway (Node.js)
                                      │ Voice Bridge Skills
                                      ▼
                                 MCP Tool Layer (Composio + custom)
```

### Directory layout

```
voice/
├── upstream/pipecat/   ← Pipecat fork — touch minimally
├── adapters/           ← OUR interface to Pipecat (pipeline.py, transport.py, events.py)
└── voiceclaw/          ← VoiceClaw voice logic (server.py lives here)

agent/
├── upstream/openclaw/  ← OpenClaw fork — touch minimally
├── adapters/           ← OUR interface to OpenClaw (gateway.py, session.py, skills.py)
└── voiceclaw/          ← VoiceClaw agent logic

pwa/                    ← Vite + React PWA (orb UI)
skills/                 ← Voice Bridge Skill .md files
infra/                  ← Railway + Docker configs
```

---

## Non-negotiable Architectural Rules

1. **Adapter layer only.** Never import directly from `upstream/pipecat/` or `upstream/openclaw/` internals. All access goes through `voice/adapters/` or `agent/adapters/`. VoiceClaw connects to OpenClaw as an external client over the documented gateway protocol — exactly as the CLI and mobile apps do.

2. **No hardcoded keys.** Every API key and model name is read from environment variables. See `.env.example`.

3. **PWA only — no native apps.** Browser-native WebRTC. No Expo, React Native, or Capacitor.

4. **OpenRouter for all LLM calls.** One key (`OPENROUTER_API_KEY`), model set via `OPENCLAW_MODEL` env var.

5. **Railway deploy must work at every phase.** Phase 1 = 2 services. Each phase adds exactly one service.

6. **Voice Bridge Skills are SKILL.md files — not code.** Natural language instruction files loaded into OpenClaw context.

7. **Stay aligned with upstream public APIs.** When a seam doesn't exist in Pipecat's public API or OpenClaw's plugin SDK, add it via the correct extension point (Observer, FrameProcessor subclass, or plugin SDK seam) — never by patching upstream internals. This is what makes upstream upgrades a one-day job instead of a rewrite.

## Upstream Alignment Reference

| Concern | Where to look | Key rule |
|---|---|---|
| Pipecat frame types | `voice/upstream/pipecat/src/pipecat/frames/frames.py` | Use dataclasses; push errors upstream with `push_error()` |
| Pipecat services | `voice/upstream/pipecat/src/pipecat/services/` | Extend `STTService`, `TTSService`, `LLMService` base classes |
| Pipecat pipeline monitoring | `voice/upstream/pipecat/src/pipecat/observers/` | Use Observers, not in-chain FrameProcessors, for state events |
| OpenClaw gateway protocol | `agent/upstream/openclaw/docs/gateway/protocol.md` | WebSocket, JSON frames; protocol changes are versioned contracts |
| OpenClaw plugin SDK | `agent/upstream/openclaw/src/plugin-sdk/` | Only cross-package import surface for extensions |
| OpenClaw SKILL.md format | `agent/upstream/openclaw/.agents/skills/` | Our skills follow the same format natively |

---

## PWA UI — voice-ui-kit Investigation (Phase 1 decision point)

Pipecat ships `@pipecat-ai/voice-ui-kit` (React, BSD-2-Clause, Tailwind 4 + Shadcn). It provides:
- `VoiceVisualizer`, `ConnectButton`, `UserAudioControl`, `ConsoleTemplate`
- Transport via `small-webrtc` or Daily
- Integrates with `@pipecat-ai/client-react`

**It does not ship a floating orb.** It is a console/panel-style UI.

Two options — owner must decide before Phase 1.5 begins (see `TODO.md`):
- **Option A (default plan):** Use `ConsoleTemplate` for Phase 1 MVP. Fast, tested, covers all states. Replace with custom orb in Phase 3.
- **Option B:** Build custom floating orb from scratch now using `@pipecat-ai/client-react` hooks.

---

## Tech Stack

| Component | Package / version |
|---|---|
| Python | `>=3.12` |
| Python package manager | `uv` |
| Pipecat | `pipecat-ai[webrtc,openrouter,deepgram,cartesia,silero]` latest |
| Web framework | `fastapi[standard]` latest |
| Node.js | `>=22` |
| React | `^19` |
| Vite | `^6` |
| Pipecat JS SDK | `@pipecat-ai/client-react` + `@pipecat-ai/voice-ui-kit` latest |

---

## OrbState Machine

Five states — driven by Pipecat pipeline frame events, exposed via SSE at `GET /state`:

| State | Visual |
|---|---|
| `idle` | soft glow / slow pulse |
| `listening` | tighter pulse reacting to mic |
| `thinking` | slow rotational shimmer |
| `tool_running` | ring sweep badge |
| `speaking` | waveform halo synced to audio |

Defined as an enum in `voice/adapters/events.py`.

---

## Environment Variables (Phase 1 minimum)

```
OPENROUTER_API_KEY=     # required
OPENCLAW_MODEL=         # required, e.g. anthropic/claude-sonnet-4-6
DEEPGRAM_API_KEY=       # required
CARTESIA_API_KEY=       # required
COMPOSIO_API_KEY=       # optional in Phase 1, required in Phase 2
```

---

## Licence Rules

- VoiceClaw code: MIT
- `voice/upstream/pipecat/`: BSD-2-Clause — keep their LICENSE file, do not claim authorship
- `agent/upstream/openclaw/`: MIT — keep their LICENSE file, do not claim authorship
- `@pipecat-ai/voice-ui-kit`: BSD-2-Clause — permissive, fine for commercial use
- Adapter and `voiceclaw/` directories are fully ours under MIT

---

## Open Questions

Tracked with resolution status in `TODO.md` (Open Questions Log section). Document answers in `docs/architecture/` as resolved.
