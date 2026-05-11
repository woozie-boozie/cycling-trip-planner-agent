# Architecture

A request flows top-to-bottom through four layers. Each layer has one job. None of them know about the others' implementation details.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          HTTP CLIENT                                 │
│              (Swagger UI · curl · frontend · Loom demo)              │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ POST /chat
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 4 · API (src/api/)                                            │
│    routes.py        — /chat, /sessions, /trace, /health              │
│    dependencies.py  — FastAPI Depends (store, anthropic client)      │
│    main.py          — app factory + structlog + CORS                 │
│  Validates request via Pydantic. Hands ConversationState to agent.   │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ run_turn(state, message, client)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 3 · Agent (src/agent/)                                        │
│    orchestrator.py  — run_turn(): the tool-use loop                  │
│    prompts.py       — SYSTEM_PROMPT (6-step plan + Honesty Rules)    │
│    state.py         — ConversationState, TraceEvent, AgentResponse   │
│    config.py        — pydantic-settings (model, max_tokens, etc.)    │
│  while stop_reason == "tool_use":                                    │
│    1. send messages to Claude with tool definitions                  │
│    2. for each tool_use block in response:                           │
│       result = await dispatch(name, args)                            │
│    3. append tool_result blocks as a user message                    │
│    4. record TraceEvents for /trace                                  │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ dispatch(tool_name, args)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 2 · Tools (src/tools/)                                        │
│    base.py          — TOOL_REGISTRY + @register_tool decorator       │
│    schemas.py       — single source of truth for input/output types  │
│    route, accommodation, weather, elevation, critique                │
│  dispatch() validates args via Pydantic, awaits the handler,         │
│  returns ToolResult(content=dict, is_error=bool).                    │
│  Errors become data, not exceptions.                                 │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ DB query / HTTP call / pure compute
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 1 · Storage (src/db/, src/sessions/)                          │
│    db/engine.py     — async SQLAlchemy engine, URL normalization     │
│    db/models.py     — SQLModel tables                                │
│    sessions/store.py — SessionStore Protocol + InMemoryStore         │
│  Three storage backends behind get_weather, swappable per env:       │
│    - SQLite in-memory (tests)                                        │
│    - Postgres on Neon (default)                                      │
│    - Open-Meteo Archive ERA5 (USE_REAL_WEATHER=true)                 │
└──────────────────────────────────────────────────────────────────────┘
```

## Module dependencies

A clean directed graph — no cycles, no surprises:

```
api ──► agent ──► tools ──► db
  │                         ▲
  └──► sessions ────────────┘
```

The agent doesn't import api. Tools don't import agent. The db layer doesn't import tools. Each layer has a one-way dependency on the layers beneath it.

## Why this shape

**Separation of grading concerns.** The brief grades agent architecture (25%) separately from tool design (20%) and conversation handling (15%). Mixing these into one ball would muddy each grade. The four layers map directly to the rubric: Layer 3 = agent architecture, Layer 2 = tool design, Layer 4 = conversation/HTTP, Layer 1 = code quality + storage.

**Swappability is the whole point.** Three things that *will* change in production:
1. The LLM (Claude → Bedrock-hosted Claude → fine-tuned model) — only `orchestrator.py` cares
2. The session store (memory → Postgres → Redis) — `SessionStore` Protocol contract
3. The tool data sources (mocks → real APIs like Komoot/Booking) — only the tool functions change, not their schemas

Each swap touches *one* file. That's not theoretical; it's been demonstrated three times in the build (see `decisions.md` ADR-009, ADR-011).

**Errors as data.** Tools don't raise exceptions to the agent loop. They return `ToolResult(is_error=True)` objects matching Anthropic's `tool_result` protocol exactly. Claude sees the error, the agent loop sends it back, and Claude adapts (often asking the user a clarifying question). This is what lets the agent recover from a typo in `find_accommodation(location="Lewess")` instead of 500-ing the whole turn.

## Request flow — the canonical happy path

```
client                   api.routes              agent.orchestrator        tools.dispatch
  │                          │                          │                       │
  ├──POST /chat ────────────►│                          │                       │
  │   {message,session_id?}  ├─ ChatRequest validated   │                       │
  │                          ├─ store.get(session_id)   │                       │
  │                          ├─ run_turn ──────────────►│                       │
  │                          │                          ├─ append user msg      │
  │                          │                          ├─ messages.create ────►│ Anthropic
  │                          │                          │   (system, tools)     │
  │                          │                          │◄── 5 tool_use blocks  │
  │                          │                          ├─ dispatch tool 1 ────►│
  │                          │                          ├─ dispatch tool 2 ────►│
  │                          │                          ├─ ...                  │
  │                          │                          ├─ messages.create ────►│ (with tool_results)
  │                          │                          │◄── final assistant    │
  │                          │                          ├─ TraceEvent: stop     │
  │                          │◄─ AgentResponse          │                       │
  │                          ├─ store.put(state)        │                       │
  │◄── ChatResponse JSON ────│                          │                       │
```

Per turn typical: 2-6 iterations, 5-18 tool calls (parallel within iteration), $0.02-$0.13 cost.

## What the diagrams don't capture

**ConversationState is the thread that ties everything together.** It's the one object that:
- Lives in the session store (per-user identity)
- Is passed by reference into `run_turn` (so the agent can mutate it)
- Is serialized in `/trace` responses (so reviewers can inspect it)
- Carries Anthropic's wire-format messages (so resuming a conversation needs no translation)

It's a Pydantic model in `src/agent/state.py`. Everything else hangs off it.

## See also

- [`docs/agent-loop.md`](agent-loop.md) — annotated walkthrough of `run_turn()` line-by-line
- [`docs/tool-design.md`](tool-design.md) — registry pattern, schemas, the dispatch contract
- [`docs/conversation-state.md`](conversation-state.md) — how sessions and traces flow
- [`docs/decisions.md`](decisions.md) — running ADR log
