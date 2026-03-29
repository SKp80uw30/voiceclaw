# 🦞 VoiceClaw

> Voice-first AI agent built on the OpenClaw ecosystem. Pipecat voice runtime + OpenClaw agent brain + MCP tool bridge. PWA-native, one-click Railway deploy, OpenRouter model-agnostic.

## What is VoiceClaw?

VoiceClaw is the missing piece between real-time voice AI and the MCP tool ecosystem. Every existing voice AI platform (VAPI, ElevenLabs, Realtime API, etc.) treats voice as a bolt-on to a chat model. VoiceClaw is built voice-first, with a dedicated bridge layer — **Voice Bridge Skills** — that translates spoken intent into MCP tool calls with the right context, confirmation patterns, and natural speech responses.

It sits within the OpenClaw spinoff ecosystem alongside NemoClaw, PicoClaw, and others — but as the first **modality extension** rather than a size variant.

## Stack

| Layer | Technology |
|---|---|
| Voice Runtime | [Pipecat](https://github.com/pipecat-ai/pipecat) (BSD-2-Clause) |
| Agent Brain | [OpenClaw](https://github.com/openclaw/openclaw) (MIT) |
| Tool Layer | MCP servers + [Composio](https://composio.dev) (recommended, optional) |
| Model Router | [OpenRouter](https://openrouter.ai) — one key, model agnostic |
| Frontend | React PWA — floating orb UI, no app store |
| Deployment | Railway — one-click deploy |

## Key Innovation: Voice Bridge Skills

Voice Bridge Skills are `SKILL.md` files that teach OpenClaw how to:
- Translate spoken intent into specific MCP tool calls
- Know which fields to confirm before destructive actions
- Speak tool results back naturally
- Handle disambiguation ("which 3pm? You have two")
- Recover gracefully from tool failures in voice context

A **Skill Builder Skill** can introspect any MCP server's tool schema and auto-generate a Voice Bridge Skill for it.

## PWA First, No App Stores

VoiceClaw runs entirely in the browser via WebRTC. Install on iOS/Android via "Add to Home Screen". No App Store approval, no update gating, no platform fees.

## One-Click Railway Deploy

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/voiceclaw)

See [docs/deployment/railway.md](docs/deployment/railway.md) for the phased deployment guide.

## Upstream Compatibility

VoiceClaw forks Pipecat and OpenClaw but treats them as **vendored upstream dependencies** via a clean adapter interface. When upstream releases updates, only the adapter layer needs review — not the whole codebase. See [docs/architecture/upstream-compatibility.md](docs/architecture/upstream-compatibility.md).

## Repo Structure

```
voiceclaw/
├── voice/          # Pipecat fork — voice pipeline
├── agent/          # OpenClaw fork — agent brain  
├── skills/         # Voice Bridge Skills library
│   ├── skill-builder/        # Meta-skill: generates bridge skills from MCP schemas
│   ├── calendar-voice-bridge/
│   ├── email-voice-bridge/
│   └── ...
├── pwa/            # React PWA — floating orb UI
├── docs/           # Architecture, deployment, skills guides
└── infra/          # Railway + Docker configs
```

## Licence

MIT — see [LICENSE](LICENSE). Upstream components retain their original licences (Pipecat: BSD-2-Clause, OpenClaw: MIT).
