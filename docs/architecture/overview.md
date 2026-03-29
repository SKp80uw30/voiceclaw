# VoiceClaw Architecture Overview

## System Diagram

```
PWA (Floating Orb — React)
    │
    │  WebRTC (browser-native, no app store)
    ▼
Pipecat Voice Pipeline (Python backend)
    │  VAD → STT (Deepgram streaming) → OpenClaw → TTS (Cartesia)
    │                    │
    │            OpenRouter API Key
    │            (model agnostic — swap Claude/Gemini/Mistral freely)
    ▼
OpenClaw Gateway (WebChat channel / HTTP API)
    │  Skills layer — SKILL.md files
    │  Voice Bridge Skills
    │  Memory: ~/.openclaw/workspace/
    ▼
MCP Tool Layer
    ├── Composio (Meta MCP — OAuth, Gmail, Slack, Calendar, etc.)
    ├── Custom MCP servers
    └── ClawHub skills (community extensions)
```

## Component Responsibilities

### Pipecat (voice/)
Owns the entire audio pipeline:
- Voice Activity Detection (VAD) — Silero or Deepgram
- Speech-to-Text — Deepgram streaming (lowest latency)
- Text-to-Speech — Cartesia (lowest latency) or ElevenLabs
- WebRTC transport to/from PWA
- Pipeline state events → PWA orb state machine
- **Does NOT own agent logic or tool dispatch**

### OpenClaw (agent/)
Owns agent reasoning and tool dispatch:
- Receives transcripts from Pipecat via WebChat channel / HTTP
- Loads relevant Voice Bridge Skills before reasoning
- Decides when and which MCP tools to call
- Returns spoken response text to Pipecat for TTS
- Maintains session memory in workspace Markdown files
- **Does NOT own audio**

### Voice Bridge Skills (skills/)
The novel layer — context-aware glue between voice intent and MCP tools:
- Per-tool-category SKILL.md files
- Disambiguation patterns for ambiguous voice commands
- Confirmation policies before destructive operations
- Natural language response templates for tool results
- Error recovery scripts for voice context

### PWA Orb (pwa/)
Minimal floating orb UI — state machine only:
- `idle` → soft glow/pulse
- `listening` → tighter pulse reacting to mic input
- `thinking` → slow rotational shimmer
- `tool-running` → ring sweep badge
- `speaking` → waveform halo synced to audio

State driven by Pipecat pipeline events via the JS SDK.

## Data Flow: Voice → Tool → Response

1. User speaks → Pipecat VAD activates
2. Deepgram streams transcript in real-time
3. Pipecat sends final transcript to OpenClaw via HTTP
4. OpenClaw loads relevant Voice Bridge Skill
5. OpenClaw reasons + decides tool call
6. OpenClaw calls MCP server (via Composio or direct)
7. Tool result returned to OpenClaw
8. OpenClaw generates spoken response text
9. Pipecat TTS converts to audio
10. Audio streams back to PWA via WebRTC
11. Orb state transitions to `speaking`

## Model Agnosticism via OpenRouter

A single `OPENROUTER_API_KEY` in the environment routes to any model. Pipecat's OpenRouter LLM provider handles this natively. Swap models by changing one env var — no code changes.

Recommended defaults:
- Fast/cheap: `google/gemini-flash-1.5`
- Quality: `anthropic/claude-sonnet-4-5`  
- Open source: `mistralai/mistral-large`
