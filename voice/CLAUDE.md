# voice/ — Pipecat Integration Layer

This directory contains VoiceClaw's voice pipeline. Read this before touching any file under `voice/`.

> Pipecat's own CLAUDE.md is at `voice/upstream/pipecat/CLAUDE.md`. Read it too when working on adapters — its architecture section explains the frame pipeline in full detail.

---

## Directory Layout

```
voice/
├── upstream/pipecat/   ← Pipecat fork — DO NOT edit except for bug fixes contributed back
├── adapters/           ← VoiceClaw's stable interface to Pipecat — all our integration code lives here
│   ├── events.py       ← OrbState enum + frame → state mapping
│   ├── transport.py    ← WebRTC transport adapter
│   ├── pipeline.py     ← VoiceClawPipeline (wraps Pipecat Pipeline)
│   └── tests/          ← Adapter unit tests
└── voiceclaw/
    └── server.py       ← FastAPI entry point
```

**Rule:** Never import from `voice/upstream/pipecat/src/pipecat/` with a relative path that reaches into internals. Only use Pipecat's public API (`Pipeline`, `PipelineTask`, `PipelineRunner`, frame types, service base classes). If a seam doesn't exist in the public API, add it via an Observer or FrameProcessor subclass in `adapters/` rather than patching upstream code.

---

## Pipecat Architecture (summary — read upstream CLAUDE.md for full detail)

Pipecat is a **frame-based pipeline**. All data flows as `Frame` objects through a chain of `FrameProcessor` nodes.

```
Transport (WebRTC input)
  → VAD (SileroVADAnalyzer)
  → STT (DeepgramSTTService)
  → LLM (OpenAILLMService via OpenRouter)
  → TTS (CartesiaTTSService)
  → Transport (WebRTC output)
```

Key abstractions:
- **`Frame`** — data unit (audio, text, control signal). Defined in `src/pipecat/frames/frames.py`
- **`FrameProcessor`** — receives frames, processes, pushes downstream (or upstream)
- **`Pipeline`** — chains processors
- **`PipelineTask`** — runs a pipeline, sends `StartFrame` to begin
- **`PipelineRunner`** — entry point, handles SIGINT/SIGTERM
- **`Observer`** — monitors frame flow *without* modifying the pipeline; use these for OrbState events

**Always use `self.create_task()` instead of raw `asyncio.create_task()`** inside FrameProcessors — the TaskManager tracks and cleans up automatically.

---

## OrbState ↔ Pipecat Frame Mapping

These are the canonical mappings. Defined in `voice/adapters/events.py`.

| OrbState | Trigger Frame(s) | Direction |
|---|---|---|
| `idle` | `BotStoppedSpeakingFrame` / pipeline `StartFrame` | downstream |
| `listening` | `VADUserStartedSpeakingFrame` / `UserStartedSpeakingFrame` | downstream |
| `thinking` | `UserStoppedSpeakingFrame` / `LLMFullResponseStartFrame` | downstream |
| `tool_running` | `FunctionCallsStartedFrame` / `FunctionCallInProgressFrame` | downstream |
| `speaking` | `TTSStartedFrame` | downstream |
| back to `idle` | `TTSStoppedFrame` / `BotStoppedSpeakingFrame` | downstream |

`VADUserStartedSpeakingFrame` is preferred over the deprecated `UserStartedSpeakingFrame` / `StartInterruptionFrame` variants (those are deprecated upstream).

Use a **Pipeline Observer** (not a FrameProcessor in the chain) to intercept these frames and emit SSE events to the PWA without disturbing the audio pipeline.

---

## Services We Use

| Service | Pipecat class | Import path |
|---|---|---|
| VAD | `SileroVADAnalyzer` | `pipecat.audio.vad.silero` |
| STT | `DeepgramSTTService` | `pipecat.services.deepgram.stt` |
| LLM | `OpenAILLMService` (base_url=OpenRouter) | `pipecat.services.openai` |
| TTS | `CartesiaTTSService` | `pipecat.services.cartesia` |
| Transport | `SmallWebRTCTransport` | `pipecat.transports.network.small_webrtc` |

All service credentials come from env vars. No hardcoded values.

**Pipecat uses `@dataclass` for frames and internal data, and Pydantic `BaseModel` for service configuration.** Mirror this in our adapter code.

---

## Code Style (mirrors Pipecat conventions for seamless integration)

- Python `>=3.12`, managed with `uv`
- Ruff for linting and formatting (line length 100)
- Google-style docstrings
- Type hints required on all async functions
- `@dataclass` for VoiceClaw frame types and internal data containers
- Pydantic `BaseModel` for config/params that cross service boundaries
- Always `await self.push_error(msg, exception, fatal=False)` on service errors — never raise naked exceptions through the pipeline

---

## Adapter Tests

Tests live in `voice/adapters/tests/`. Run with:

```bash
cd voice && uv run pytest adapters/tests/
```

Use Pipecat's `run_test()` utility (`src/pipecat/tests/utils.py`) to send frames through a processor and assert outputs. This is the upstream-blessed pattern — use it rather than hand-rolling test harnesses.

---

## Upstream Compatibility

When Pipecat releases an update:
1. `git fetch pipecat-upstream main`
2. Merge into `voice/upstream/pipecat/` only
3. Run `uv run pytest voice/adapters/tests/`
4. Fix only `voice/adapters/` if tests break — `voice/voiceclaw/` should be unaffected

Anything built in `voice/adapters/` that is generally useful should be proposed back to Pipecat as a PR (e.g. the pipeline state event API for orb state machines).
