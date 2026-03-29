# Upstream Compatibility Strategy

## The Problem

VoiceClaw forks both Pipecat and OpenClaw. Without a deliberate strategy, upstream updates (new STT providers, agent improvements, bug fixes) become painful merges into a diverged codebase.

## The Solution: Adapter Layer Pattern

VoiceClaw treats Pipecat and OpenClaw as **vendored upstream dependencies** with clean adapter interfaces. Our own code never directly imports from deep within upstream internals — only from stable public interfaces that we define.

```
voice/
├── upstream/          # Pipecat fork — touch minimally
│   └── pipecat/       # Upstream code lives here
├── adapters/          # VoiceClaw's interface to Pipecat — OUR code
│   ├── pipeline.py    # VoiceClawPipeline wraps Pipecat pipeline
│   ├── transport.py   # WebRTC transport adapter
│   └── events.py      # Orb state event bridge
└── voiceclaw/         # VoiceClaw-specific voice logic

agent/
├── upstream/          # OpenClaw fork — touch minimally
│   └── openclaw/      # Upstream code lives here
├── adapters/          # VoiceClaw's interface to OpenClaw — OUR code
│   ├── gateway.py     # HTTP bridge: Pipecat → OpenClaw
│   ├── session.py     # Session lifecycle management
│   └── skills.py      # Voice Bridge Skill loader
└── voiceclaw/         # VoiceClaw-specific agent logic
```

## Upgrade Process

When Pipecat or OpenClaw releases an update:

1. `git fetch upstream` in the relevant fork
2. Merge/rebase upstream into `voice/upstream/pipecat` or `agent/upstream/openclaw`
3. Run adapter tests: `pytest voice/adapters/tests/` and `pytest agent/adapters/tests/`
4. Fix only the adapter layer if tests break
5. VoiceClaw-specific code in `voiceclaw/` should be unaffected

## What We Modify in Upstream

We aim to modify upstream code **as little as possible**. Acceptable upstream modifications:
- Bug fixes we contribute back via PRs
- Hooks/events that upstream doesn't expose but we need

Not acceptable:
- Business logic changes to upstream
- Restructuring upstream files
- Adding VoiceClaw-specific features directly into upstream code

## Contributing Back

Anything we build in the adapter layer that is generally useful should be proposed back to Pipecat or OpenClaw as a PR. This is how VoiceClaw becomes a good citizen of the ecosystem rather than a permanent fork.
