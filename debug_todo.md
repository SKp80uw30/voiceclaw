# VoiceClaw Debug Tracker

## Known State (2026-03-30 — updated after fix session)

### Fix Status

| # | Issue | Root Cause | Status |
|---|---|---|---|
| 1 | `:8000` flashes ~500x/s | Old `sw.js` had `autoUpdate`/`skipWaiting` — PWA wasn't rebuilt before Docker | **FIXED**: PWA rebuilt (`registerType: 'prompt'`), Docker rebuilt, new sw.js deployed. Clear browser SW once. |
| 2 | Voice capture silent (any port) | **Root cause: Docker container `172.19.0.3` is unreachable from macOS browser via UDP**. WebRTC ICE times out (60s). Docker on macOS puts containers in a VM subnet not bridged to host. Only TCP ports are forwarded. | **FIXED**: Run pipecat-backend natively (outside Docker). ICE now finds `192.168.20.7` (WiFi) and `100.109.83.52` (Tailscale) — browser can reach both. |
| 3 | `missing scope: operator.write` | `VOICECLAW_CLIENT_ID = "gateway-client"` → `isControlUi=false` → gateway stripped scopes on token-auth without device | **FIXED** (deployed): Changed to `"openclaw-tui"` → `isControlUi=true` → `dangerouslyDisableDeviceAuth` bypass → scopes preserved. **Needs end-to-end voice test to confirm.** |

### server.py bug fixed
- `server.py:323` was checking `if _PWA_STATIC_DIR.exists()` before mounting `/assets`, but `pwa/assets/` doesn't exist (assets are in `pwa/dist/assets/`). Changed to `if (_PWA_STATIC_DIR / "assets").exists()` so the server starts cleanly without `VOICECLAW_PWA_DIR` set.

### Previously Tried / Failed

| Attempt | What it was | Result | Why it didn't help |
|---|---|---|---|
| Fix `.env` STT/TTS vars | `STT_PROVIDER=deepgram`, `TTS_PROVIDER=cartesia` | No effect | `pipeline.py` reads `DEEPGRAM_API_KEY` / `CARTESIA_API_KEY` directly — never reads `STT_PROVIDER`/`TTS_PROVIDER` |
| Fix `OPENCLAW_MODEL` prefix | `minimax/minimax-m2.7` (removed `openrouter/` prefix) | Possibly helpful | Gateway shows `anthropic/claude-opus-4-6` regardless — `OPENCLAW_MODEL` may only affect Pipecat's LLM node, not the gateway |
| `registerType: 'prompt'` in `vite.config.ts` | Changed from `autoUpdate` | Fix is in source but NOT in `pwa/dist/sw.js` | PWA was NOT rebuilt before Docker rebuild — old sw.js is still being served |
| `VOICECLAW_CLIENT_ID = "openclaw-tui"` | Changed from `"gateway-client"` | Deployed in last Docker build | Intended to fix scope error; may have introduced voice capture regression at :5173 (unconfirmed) |

---

## Config Reference

### Token / Key Alignment Matrix

| Variable | Set In | Used By | Value |
|---|---|---|---|
| `OPENCLAW_GATEWAY_TOKEN` | `.env`, `docker-compose.yml` | pipecat-backend (gateway.py), openclaw-gateway | `voiceclaw-dev` |
| `OPENROUTER_API_KEY` | `.env`, `docker-compose.yml` | openclaw-gateway (LLM calls) | `sk-or-v1-…` |
| `OPENCLAW_MODEL` | `.env` | pipecat-backend? (unconfirmed if gateway reads it) | `minimax/minimax-m2.7` |
| `DEEPGRAM_API_KEY` | `.env` | pipecat-backend `pipeline.py` directly | `0edae12b…` |
| `CARTESIA_API_KEY` | `.env` | pipecat-backend `pipeline.py` directly | `sk_car_NDX…` |
| `OPENCLAW_DEVICE_AUTH_DISABLED` | `docker-compose.yml` only | pipecat-backend `gateway.py` — omits `device` object | `true` |
| `VOICECLAW_CLIENT_ID` | `agent/adapters/device.py` | gateway.py handshake `client.id` | `openclaw-tui` |

### Gateway Auth Flow (Docker dev)

```
pipecat-backend  →  WS connect  →  openclaw-gateway
  client.id = "openclaw-tui"         isOperatorUiClient() = true
  auth.token = "voiceclaw-dev"        → isControlUi = true
  no device object                    → dangerouslyDisableDeviceAuth bypass
                                      → allowBypass = true → scopes preserved
  scopes = ["operator.read", "operator.write"]
```

---

## Local Dev Workflow (CONFIRMED WORKING)

WebRTC + Docker Desktop on macOS is fundamentally broken for local dev: the Docker container's UDP port is unreachable from the macOS browser (container is in a VM subnet, not bridged to host). Only TCP ports work via Docker's port forwarding.

**Correct local dev setup: only openclaw-gateway in Docker (TCP only). pipecat-backend runs natively.**

```bash
# Terminal 1: openclaw-gateway only
cd /Users/stevekelly/Library/Developer/voiceclaw
docker compose up openclaw-gateway

# Terminal 2: pipecat server natively (WebRTC ICE uses real macOS IPs)
cd /Users/stevekelly/Library/Developer/voiceclaw/voice
PYTHONPATH=/Users/stevekelly/Library/Developer/voiceclaw \
  uv run uvicorn voiceclaw.server:app --host 0.0.0.0 --port 8000

# Terminal 3: PWA dev (proxies /offer and /state to localhost:8000)
cd /Users/stevekelly/Library/Developer/voiceclaw/pwa && npm run dev

# Open: http://localhost:5173
```

For Railway/production: full docker-compose still works (server has a routable public IP there).

---

## Fix Sequence (ordered by dependency)

### Fix 1 — Rebuild PWA so sw.js has `registerType: 'prompt'`

**Why first:** The flash loop poisons `:8000` entirely, and the browser's cached SW may also affect dev-mode behaviour.

```bash
# 1a. Confirm vite.config.ts has the fix
grep "registerType" pwa/vite.config.ts
# Expected: registerType: 'prompt'

# 1b. Install deps if needed
cd /Users/stevekelly/Library/Developer/voiceclaw/pwa && npm install

# 1c. Build the PWA
npm run build

# 1d. Confirm sw.js no longer has skipWaiting
grep -c "skipWaiting\|SKIP_WAITING" dist/sw.js
# Expected: 0

cd /Users/stevekelly/Library/Developer/voiceclaw
```

- [ ] PWA built
- [ ] `sw.js` confirmed clean (0 matches)

---

### Fix 2 — Rebuild Docker with new sw.js

```bash
cd /Users/stevekelly/Library/Developer/voiceclaw
docker compose down
docker compose up --build -d
docker compose ps
# Both containers should show "healthy"

# Confirm new sw.js is being served
curl -s http://localhost:8000/sw.js | grep -c "skipWaiting"
# Expected: 0
```

- [ ] Docker rebuilt and healthy
- [ ] Served `sw.js` confirmed clean

---

### Fix 3 — Clear browser service worker for localhost:8000

Do this in the browser (Chrome/Safari):

**Chrome:**
1. Open DevTools → Application → Service Workers
2. For `localhost:8000` — click "Unregister"
3. Hard-refresh: Cmd+Shift+R

**Or via DevTools console at localhost:8000:**
```js
navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister()))
```

- [ ] SW unregistered in browser
- [ ] :8000 no longer flashing

---

### Test 1 — Verify :8000 flash is fixed

```
Navigate to localhost:8000
Expected: page loads once, stays stable, no reload loop
```

If still flashing: check `curl -s http://localhost:8000/sw.js | grep skipWaiting` again.

- [ ] :8000 stable

---

### Test 2 — Diagnose :5173 voice capture

```bash
# 2a. Start Vite dev server (separate terminal)
cd /Users/stevekelly/Library/Developer/voiceclaw/pwa
npm run dev
```

```
Navigate to localhost:5173
Open browser DevTools Console
Click the "Connect" button in the UI
Watch console for errors
```

Expected console path if working:
```
[VoiceClaw] transport state: connecting
[VoiceClaw] transport state: connected
```

Failure modes to look for in console:
- `getUserMedia` permission denied → browser mic permission
- WebSocket error / 500 on `/offer` → backend issue
- CORS error → CORS config
- JS uncaught exception → UI bug

```bash
# Also watch backend logs while connecting from :5173
docker compose logs -f pipecat-backend 2>/dev/null | grep -E "(offer|connect|ERROR|session)"
```

Expected backend output on connect:
```
VoiceClaw server: bootstrapping pipeline pc_id=...
WebRTC connection initialised: pc_id=...
VoiceClaw server: WebRTC connected pc_id=...
OpenClawGateway: connecting to ws://openclaw-gateway:18789
OpenClawGateway: connected (session=...)
```

- [ ] Console output captured
- [ ] Backend log output captured

---

### Test 3 — Verify scope fix (gateway handshake with openclaw-tui)

After connecting from :5173, speak a test phrase. Watch gateway logs:

```bash
docker compose logs -f openclaw-gateway 2>/dev/null
```

Expected gateway output on connect:
```
[ws] webchat connected conn=... client=openclaw-tui ...
[ws] ⇄ res ✓ connect ...
```

Expected on speech:
```
[ws] ⇄ req chat.send ...
```

Failure: if gateway log shows `DEVICE_AUTH_DEVICE_ID_MISMATCH` or scope error, the `openclaw-tui` fix needs revisiting.

- [ ] Gateway handshake succeeds with `openclaw-tui`
- [ ] `chat.send` succeeds (no scope error)
- [ ] AI responds with voice

---

## Secondary Issues to Investigate if Core Flow Fails

### S1 — `OPENCLAW_MODEL` not being used

Gateway startup log shows `agent model: anthropic/claude-opus-4-6` regardless of `OPENCLAW_MODEL`.

To check if this is correct or a config issue:
```bash
docker compose exec openclaw-gateway cat /home/node/.openclaw/openclaw.json
```

The `OPENCLAW_MODEL` env var may need to be mapped to the gateway config key `gateway.llm.model` (or equivalent). Check the OpenClaw gateway config schema:
```bash
grep -r "OPENCLAW_MODEL\|llm.*model\|model.*env" agent/upstream/openclaw/src/ 2>/dev/null | head -20
```

### S2 — HEAD /sw.js returns 405

The FastAPI `serve_root_file` route doesn't handle HEAD requests, causing 405 for `HEAD /sw.js`. The browser SW update check uses HEAD. This may prevent SW update detection.

Fix: The static files serving should use FastAPI's `StaticFiles` for `sw.js` rather than the custom `serve_root_file` route, or add a HEAD handler.

---

## Current Docker Config Summary

```
pipecat-backend:
  OPENCLAW_GATEWAY_URL=ws://openclaw-gateway:18789
  OPENCLAW_GATEWAY_TOKEN=voiceclaw-dev
  OPENCLAW_DEVICE_AUTH_DISABLED=true
  OPENROUTER_API_KEY=sk-or-v1-…
  DEEPGRAM_API_KEY=0edae12b…
  CARTESIA_API_KEY=sk_car_NDX…

openclaw-gateway:
  OPENCLAW_GATEWAY_TOKEN=voiceclaw-dev
  OPENROUTER_API_KEY=sk-or-v1-…

openclaw.json (gateway config):
  dangerouslyDisableDeviceAuth=true
  dangerouslyAllowHostHeaderOriginFallback=true
  --allow-unconfigured flag
```
