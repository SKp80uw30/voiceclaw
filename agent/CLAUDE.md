# agent/ — OpenClaw Integration Layer

This directory contains VoiceClaw's agent gateway. Read this before touching any file under `agent/`.

> OpenClaw's own CLAUDE.md is at `agent/upstream/openclaw/CLAUDE.md`. Read it too when working on adapters — its architecture section explains the plugin/channel boundary, gateway protocol, and SDK rules in full detail.

---

## Directory Layout

```
agent/
├── upstream/openclaw/  ← OpenClaw fork — DO NOT edit except for bug fixes contributed back
├── adapters/           ← VoiceClaw's stable interface to OpenClaw — all our integration code lives here
│   ├── gateway.py      ← WebSocket bridge: Pipecat → OpenClaw gateway → spoken text back
│   ├── session.py      ← Per-user session lifecycle
│   ├── skills.py       ← Voice Bridge Skill loader (scans skills/, injects into context)
│   └── tests/          ← Adapter unit tests
└── voiceclaw/          ← VoiceClaw-specific agent logic
```

**Rule:** Never import from `agent/upstream/openclaw/src/` internals directly. VoiceClaw connects to OpenClaw as an **external client** over the documented gateway protocol — the same way the CLI, mobile apps, and web UI do. If a new seam is needed, request it via the plugin SDK, not by reaching into core internals.

---

## OpenClaw Gateway Protocol (IMPORTANT — read before implementing gateway.py)

**OpenClaw's gateway uses WebSocket, not plain HTTP POST.**

The wire protocol (`agent/upstream/openclaw/docs/gateway/protocol.md`):

1. Connect via WebSocket to `ws://localhost:18789`
2. Receive a `connect.challenge` event with a nonce
3. Send a `connect` request frame with role, scopes, auth token, and client metadata
4. Receive `hello-ok` to confirm the session is open
5. Send/receive JSON frames with `type: "req"` | `"res"` | `"event"` structure

VoiceClaw's `gateway.py` adapter must implement this handshake, then send transcripts as chat messages and receive agent responses.

Default gateway port: **18789** (confirmed from OpenClaw source).

The relevant OpenClaw channel for VoiceClaw is the **web channel** (`src/channel-web.ts` in upstream). Study this to understand the message format the gateway expects for a chat turn.

---

## SKILL.md Files

Voice Bridge Skills are loaded by `adapters/skills.py` before each agent turn. Rules:

- Skills live under `skills/` at the repo root
- Each skill is a `SKILL.md` file in its own subdirectory
- Skills are **natural language instruction files** — never convert them to code
- `skills.py` scans the directory, selects relevant skills based on transcript intent, and prepends them to the OpenClaw context before the chat turn
- The Skill Builder Skill (`skills/skill-builder/SKILL.md`) can auto-generate new skills from MCP tool schemas — support this workflow

OpenClaw itself uses `SKILL.md` files natively (see `agent/upstream/openclaw/.agents/skills/` for examples). Our skills follow the same format.

---

## OpenClaw Plugin SDK Boundary

When VoiceClaw needs functionality from OpenClaw:
- **Allowed:** `openclaw/plugin-sdk/*` public surface, gateway protocol, manifest metadata
- **Not allowed:** importing `src/**` internals, reaching into `extensions/<id>/src/**`, or bypassing the plugin contract

If a capability isn't exposed via the plugin SDK, the right path is to open a PR to OpenClaw adding a new documented seam — not to reach around the boundary. This is what keeps us compatible with upstream updates.

---

## OpenClaw Runtime Commands (useful for local dev and testing)

```bash
# Start gateway
openclaw gateway run --bind loopback --port 18789

# Check channel status
openclaw channels status --probe

# Run a test message
openclaw message send "test message"
```

Node.js `>=22` required. Use `pnpm` as the package manager (matches OpenClaw upstream).

---

## Code Style (mirrors OpenClaw adapter conventions)

Our adapters in `agent/adapters/` are Python (bridging Pipecat's Python world to OpenClaw's Node.js world). Follow VoiceClaw Python conventions (see root `CLAUDE.md`).

For any Node.js code added under `agent/voiceclaw/`:
- TypeScript (strict, no `any`)
- ESM modules
- Mirror OpenClaw's naming: `openclaw` (lowercase) for CLI/paths, `OpenClaw` for prose
- American English in all strings, docs, and comments (matches upstream)

---

## Adapter Tests

```bash
cd agent && uv run pytest adapters/tests/
```

Test the WebSocket handshake with a mock OpenClaw gateway — do not depend on a live OpenClaw instance for unit tests.

---

## Upstream Compatibility

When OpenClaw releases an update:
1. `git fetch openclaw-upstream main`
2. Merge into `agent/upstream/openclaw/` only
3. Run adapter tests
4. Fix only `agent/adapters/` if tests break
5. Pay special attention to `docs/gateway/protocol.md` — protocol changes are contract changes that require explicit versioning on OpenClaw's side, so they will be announced in their changelog
