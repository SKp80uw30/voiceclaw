# VoiceClaw — ERD (v3)
## LLM as Brain · Skills as Harness · Pipecat as Runtime · Mem0 as Memory

---

## What Changed in v3

Every LLM API call is stateless. Without intervention, Flow starts each conversation
with no knowledge of the user — who they are, what they've done before, what they
prefer. This is the problem memory solves.

**Mem0** (Apache 2.0, open source) has been added as the memory layer. It sits between
conversations and the LLM, automatically extracting facts from interactions, storing
them in a hybrid vector + key-value store, and injecting the most relevant memories
into each prompt at call time.

The result: Flow feels like she already knows the user. The LLM token cost drops
because context doesn't grow unbounded — it stays compressed and relevant.

---

## Why Mem0

**TurboQuant** (the repo you linked) is not applicable here. It is a KV cache
compression algorithm for GPU-hosted LLM inference at Google scale — it solves
memory bandwidth bottlenecks on H100s, not conversational memory between API calls.

**Mem0** is exactly the right fit:
- Designed for stateless LLM API calls (exactly the pattern VoiceClaw uses)
- Open source, Apache 2.0, self-hostable on Railway
- Python + Node.js SDKs — compatible with the existing stack
- Supports OpenRouter-compatible LLMs via OpenAI-compatible API
- Hybrid store: vector search for semantic retrieval + key-value for fast fact lookup
- Scopes memory by `user_id`, `agent_id`, and `run_id` — maps cleanly to Flow vs Action Agent
- 91% lower latency vs full-context, 90% token cost reduction vs passing full history
- No enterprise lock-in for Phase 1 — local vector store (Qdrant or Chroma) works fine

---

## Memory Architecture

There are three distinct memory concerns in VoiceClaw. Mem0 handles all three
through different scoping and retrieval strategies.

```
┌────────────────────────────────────────────────────────────────┐
│                     MEM0 MEMORY LAYER                          │
│                                                                 │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  User Memory    │  │ Session Memory   │  │  Job Memory  │  │
│  │                 │  │                  │  │              │  │
│  │ Persists across │  │ Current conver-  │  │ Completed    │  │
│  │ all sessions.   │  │ sation turns.    │  │ job results  │  │
│  │ Preferences,    │  │ Flushed at end   │  │ and outcomes │  │
│  │ patterns, facts │  │ of session after │  │ stored for   │  │
│  │ about the user. │  │ extraction.      │  │ future ref.  │  │
│  │                 │  │                  │  │              │  │
│  │ scope: user_id  │  │ scope: run_id    │  │ scope:       │  │
│  └────────┬────────┘  └────────┬─────────┘  │ agent_id +   │  │
│           │                    │            │ user_id      │  │
│           └──────────┬─────────┘            └──────┬───────┘  │
│                      │                             │          │
│              memory.search()               memory.search()    │
│            (semantic + key-value)          (by agent_id)      │
└──────────────────────┬──────────────────────────┬─────────────┘
                       │                          │
                       ▼                          ▼
              Injected into                Injected into
              Flow prompt                 Action Agent
              (as RAG context)            (as job context)
```

### Memory Types in Practice

**User Memory** (`user_id` scoped)
What Flow knows about this person across all time:
- Preferences ("prefers Italian food", "morning person", "lives in Parkdale")
- Behavioural patterns ("usually books for 2", "uses calendar for everything")
- Personal facts ("name is Steve", "team is 5 people")
- Past decisions ("last time chose Tipo 00 for Italian")

Written to after each session. Read at the start of every Flow LLM call.

**Session Memory** (`run_id` scoped)
The current conversation — exact turn-by-turn exchange. Mem0 manages this as a
rolling window. At end of session, Mem0 extracts salient facts and promotes them
to User Memory automatically.

This replaces the naive pattern of appending every message to the prompt, which
causes token cost to grow unbounded.

**Job Memory** (`agent_id` + `user_id` scoped)
What jobs have been completed, what their outcomes were. Allows Flow to say
"last time I booked a restaurant for you it was Tipo 00 — shall I try there again?"
Written by the Action Agent after each completed job. Read by Flow when a similar
intent is detected.

---

## Updated System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER (voice)                            │
└────────────────────────────┬────────────────────────────────────┘
                             │ WebRTC
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PIPECAT RUNTIME                            │
│                  STT ──► Orchestrator ──► TTS                   │
└──────────────────────┬─────────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐      ┌──────────────────────────────────────┐
│   FLOW LLM CALL  │      │          ACTION LLM CALL             │
│                  │      │                                      │
│ System prompt:   │      │ System prompt:                       │
│ - Flow base      │      │ - Action base                        │
│ - User memories  │◄─┐   │ - Skill context                      │
│   (from Mem0)    │  │   │ - Job memories (from Mem0)           │
│ - Session turns  │  │   │                                      │
│   (from Mem0)    │  │   │ Tools: Skill MCP definitions only    │
│                  │  │   └────────────────┬─────────────────────┘
│ No tools         │  │                    │
└────────┬─────────┘  │                    │
         │            │                    │
         │ IntentPacket                    │ CompletionSignal
         │            │  ┌─────────────────┘
         └────────────┼──┼──► Message Bus
                      │  │
                      │  │   ┌──────────────────────────────────┐
                      │  └───┤         MEM0 LAYER               │
                      │      │                                  │
                      │      │  memory.add()  ◄── end of turn   │
                      └─────►│  memory.search() ◄── start call  │
                             │                                  │
                             │  Vector store (Qdrant/Chroma)    │
                             │  Key-value store (SQLite Ph.1)   │
                             └──────────────────────────────────┘
```

---

## Updated Entity Definitions

All V2 entities (IntentPacket, CompletionSignal, ApprovalPacket, JobState, Skill)
are unchanged. The following are added or updated.

### 1. MemoryConfig (new)
Mem0 configuration — single instance, shared across Flow and Action Agent.

```typescript
interface MemoryConfig {
  // LLM used by Mem0 internally for memory extraction
  // Use a cheap/fast model — this is not the main reasoning model
  llm: {
    provider: "openai";           // OpenAI-compatible (works with OpenRouter)
    config: {
      model: string;              // e.g. "openai/gpt-4o-mini" via OpenRouter
      api_key: string;
      api_base?: string;          // OpenRouter base URL
    };
  };

  // Phase 1: local vector store, no external service needed
  vector_store: {
    provider: "qdrant" | "chroma";
    config: {
      path: string;               // Local path e.g. "./data/mem0_vectors"
      collection_name: string;
    };
  };

  // Phase 2: swap to hosted Qdrant or Pinecone — no code changes needed
}
```

### 2. MemoryService (new)
Thin wrapper around Mem0. Single service, used by both Flow and Action Agent.
Neither agent calls Mem0 directly — always via this service.

```typescript
interface MemoryService {
  // Called at start of Flow LLM call — returns context string for prompt
  recallForFlow(userId: string, query: string, runId: string): Promise<MemoryContext>;

  // Called at end of each Flow turn — extracts and stores new memories
  learnFromTurn(
    userId: string,
    runId: string,
    messages: { role: string; content: string }[]
  ): Promise<void>;

  // Called by Action Agent — returns relevant past job context
  recallJobContext(userId: string, intentSummary: string): Promise<string>;

  // Called by Action Agent on job completion — stores outcome
  storeJobOutcome(userId: string, jobId: string, summary: string): Promise<void>;
}

interface MemoryContext {
  user_facts: string;       // Formatted string of relevant user memories
  session_history: string;  // Recent turn summary
  job_history?: string;     // Relevant past jobs (only if similar intent found)
}
```

### 3. FlowPromptContext (updated)
RAG layer is now replaced by MemoryService. The stub is gone.

```typescript
interface FlowPromptContext {
  base_prompt: string;
  memory_context: MemoryContext;    // ← was rag_context?: string (stub)
  pending_jobs: {
    job_id: string;
    resurfacing: string;
    status: string;
  }[];
  conversation_history: {           // Current session turns (from Mem0 run_id)
    role: "user" | "assistant";
    content: string;
  }[];
}
```

---

## Updated Component Responsibilities

### MemoryService

**File:** `src/memory/memory_service.ts`

The only file that imports from Mem0. Everything else calls this interface.

Key behaviours:

**On `recallForFlow()`:**
1. `memory.search(query, { user_id, run_id })` — semantic search across user + session memory
2. Format results into a clean string block for prompt injection
3. Return fast — this is on the hot path before every Flow LLM call

**On `learnFromTurn()`:**
1. Called after every assistant response (not user turn — wait for the pair)
2. `memory.add(messages, { user_id, run_id })` — Mem0 extracts facts automatically
3. Fire-and-forget — do not await on the critical path

**On `storeJobOutcome()`:**
1. Called by Action Agent after `CompletionSignal` with `stage: "final"`
2. `memory.add([{ role: "system", content: summary }], { user_id, agent_id: "action" })`
3. Tags with job_id in metadata for future retrieval

---

### Flow LLM (updated)

**File:** `src/agents/flow/flow_llm.ts`

Changes from V2:
- `rag_layer.ts` is removed entirely
- `memory_service.recallForFlow()` replaces the RAG stub — no longer a Phase 2 item
- `memory_service.learnFromTurn()` called after each response

```typescript
// Pseudocode for Flow turn
async function flowTurn(userInput: string, userId: string, runId: string) {
  // 1. Recall relevant memories (fast — vector search)
  const memCtx = await memoryService.recallForFlow(userId, userInput, runId);

  // 2. Assemble prompt with memory context injected
  const prompt = buildFlowPrompt({ memCtx, pendingJobs, conversationHistory });

  // 3. LLM call
  const response = await llmClient.call(flowConfig, prompt);

  // 4. Parse — extract IntentPacket if present
  const { text, packet } = parseFlowResponse(response);

  // 5. Learn from this turn (async, non-blocking)
  memoryService.learnFromTurn(userId, runId, [
    { role: "user", content: userInput },
    { role: "assistant", content: text }
  ]); // no await

  // 6. If packet, publish to bus
  if (packet) bus.publishIntent(packet);

  // 7. Return text for TTS
  return text;
}
```

---

### Action Agent (updated)

**File:** `src/agents/action/action_agent.ts`

Changes from V2:
- Calls `memoryService.recallJobContext()` before skill execution to inject prior outcomes
- Calls `memoryService.storeJobOutcome()` on final CompletionSignal

```typescript
// On receiving IntentPacket
async function handleIntent(packet: IntentPacket) {
  // 1. Classify to skill
  const skill = classifier.match(packet);

  // 2. Recall relevant past jobs (informs skill execution)
  const jobCtx = await memoryService.recallJobContext(userId, packet.intent_summary);

  // 3. Build LLM config with job context injected
  const config = skill.buildLLMConfig(packet, { job_history: jobCtx });

  // 4. Execute
  await skill.execute(packet, (signal) => {
    bus.publishCompletion(signal);

    // 5. On final signal, store outcome in memory
    if (signal.stage === "final" && signal.status === "success") {
      memoryService.storeJobOutcome(userId, packet.job_id, signal.result_summary);
    }
  });
}
```

---

## Updated Directory Structure

```
src/
  memory/
    memory_service.ts        ← MemoryService implementation (wraps Mem0)
    memory_config.ts         ← Mem0 configuration
    types.ts                 ← MemoryContext, MemoryConfig interfaces

  pipecat/
    orchestrator.ts
    adapter.ts

  agents/
    flow/
      flow_llm.ts            ← Updated: uses MemoryService, no rag_layer
      intent_radar.ts
      job_tracker.ts
      # rag_layer.ts         ← REMOVED (replaced by memory_service)
    action/
      action_agent.ts        ← Updated: recalls + stores job memory
      intent_classifier.ts
      job_store.ts
      mcp_executor.ts

  skills/
    base_skill.ts
    calendar/
    restaurant-booking/
    email/

  bus/
    message_bus.ts
    types.ts

  llm/
    client.ts
    prompts/
      flow_base.ts
      action_base.ts

  data/                      ← Phase 1 local storage
    mem0_vectors/            ← Qdrant/Chroma local vector store
    job_store.db             ← SQLite job state (Phase 1)
```

---

## Updated Implementation Order

The memory layer is added as a new **Step 2**, shifting everything else down by one.
This is intentional — memory must exist before Flow is built, because Flow depends on it.

### Step 1 — Types
`src/bus/types.ts` + `src/memory/types.ts` — all interfaces. No logic.

### Step 2 — Memory Service ← NEW
`src/memory/memory_config.ts` + `src/memory/memory_service.ts`

Install: `pip install mem0ai` (Python) or `npm install mem0ai` (Node)

Configure Mem0 with:
- LLM: OpenRouter (OpenAI-compatible base URL, cheap model like gpt-4o-mini)
- Vector store: local Qdrant or Chroma (no external service in Phase 1)

Implement MemoryService with all four methods.

Test:
- Add a mock conversation, verify memories extracted
- Search for a related query, verify relevant memories returned
- Confirm session memories scoped to run_id don't leak across sessions

### Step 3 — LLM Client
`src/llm/client.ts` — OpenRouter wrapper. Unchanged from V2.

### Step 4 — Message Bus
`src/bus/message_bus.ts` — Unchanged from V2.

### Step 5 — Base Skill + Three Starter Skills
Unchanged from V2. Stub execute() methods.

### Step 6 — Action Agent
Updated: inject job memory from MemoryService before skill execution.
Store job outcome after final CompletionSignal.

### Step 7 — Flow LLM
Updated: replace rag_layer stub with real MemoryService.recallForFlow() call.
Add learnFromTurn() after each response.

### Step 8 — Pipecat Orchestrator
Unchanged from V2.

### Step 9 — Real MCP Connections
Unchanged from V2. Priority: Google Calendar → Gmail → Restaurant booking.

---

## Key Constraints for Claude Code

All V2 constraints apply, plus:

- **Only `memory_service.ts` imports from Mem0.** Flow and Action Agent never call
  Mem0 directly. This keeps the memory provider swappable.

- **`learnFromTurn()` is always fire-and-forget.** Never await it on the response path.
  Memory writes are async and must not add latency to voice responses.

- **`recallForFlow()` must be fast.** If it takes >200ms, the voice response feels slow.
  Local Qdrant is fast enough for Phase 1. Monitor this in production.

- **Session memory uses `run_id`, not `user_id`.** A `run_id` is generated fresh per
  Pipecat session. This prevents session bleed while keeping user facts persistent.

- **Mem0's internal LLM for extraction should be a cheap model.** It does not need
  to be the same model as Flow's reasoning LLM. Use gpt-4o-mini or equivalent.
  This keeps memory extraction costs near zero.

- **Do not store raw transcripts in Mem0.** Mem0 extracts facts — let it do its job.
  Passing full transcripts is wasteful. Pass the last 2-4 turns only.

---

## Open Questions (updated)

1. **Memory extraction quality** — Mem0 uses an LLM to extract facts. Test with real
   voice-style short utterances ("book me a table tonight") to verify it extracts
   usefully. May need custom extraction prompts for terse voice input.

2. **Job store persistence** — in-memory Map Phase 1, SQLite local file. Abstract
   interface for Redis drop-in later.

3. **run_id lifecycle** — when does a session end and a new run_id start? On Pipecat
   disconnect. Implement a session_end hook that triggers learnFromTurn() on the
   full session before flushing.

4. **Memory privacy** — user memories persist indefinitely by default. Phase 2 should
   add TTL or user-triggered deletion. Note in the data model now, build later.

5. **Mem0 self-hosted vs managed** — Phase 1 uses local vector store (free, no service).
   Phase 2 may benefit from Mem0's managed platform for analytics and decay mechanisms.
   The MemoryService interface abstracts this — switching is a config change only.
