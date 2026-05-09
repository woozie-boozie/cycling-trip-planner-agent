# Cycling Trip Planner Agent

An AI agent that helps a cyclist plan a multi-day bike trip through conversation. Built as a case study for Affinity Labs.

**Stack:** Python 3.10+ · FastAPI · Anthropic Claude · Pydantic · SQLModel · Postgres (Neon) · Open-Meteo

---

## What it does

Talk to the agent in natural language and it produces a day-by-day cycling plan with route, terrain, weather, and accommodation — adapting as you change your preferences mid-conversation.

```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{
  "message": "Plan a 4-day cycle from London to Paris on the Avenue Verte, 100km/day, prefer camping but a hostel every 3rd night, traveling in June"
}'
```

The agent will: shape the route (London→Lewes→Newhaven→Dieppe→Paris via the Avenue Verte), gather elevation + weather + accommodation per segment **in parallel** (~15 tool calls in one Claude turn), call its **self-critique** tool to check the draft against the user's constraints, then return a structured day-by-day plan with a "Heads up" section that honestly surfaces any constraints it couldn't fully honor (e.g. *"no camping found in Lewes, hostel fallback"*).

See it in action via the [eval scoreboard](docs/eval-results.md) and [agent-loop walkthrough](docs/agent-loop.md).

---

## Run it locally

Requires **Python 3.10+** (developed on 3.13) and an **Anthropic API key**. No other accounts required — Postgres falls back to SQLite for tests, and weather data falls back to seeded mocks if you don't set `DATABASE_URL`.

```bash
git clone https://github.com/woozie-boozie/cycling-trip-planner-agent.git
cd cycling-trip-planner-agent

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY (required)
# DATABASE_URL is optional — if unset, SQLite in-memory is used

make install              # creates .venv and installs deps
make seed                 # populates DB with route/accommodation/weather/elevation data
make dev                  # runs FastAPI on http://localhost:8000

# in another terminal
curl http://localhost:8000/healthz
# → {"status":"ok",...}

# Interactive Swagger UI:
open http://localhost:8000/docs
```

### Try the agent end-to-end

```bash
# A real conversation, with auto-generated session id:
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Plan a London to Brighton ride, June, 100km/day, hostel both nights"}' | jq

# Continue the conversation by passing back the session_id:
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Actually 60km/day", "session_id": "<paste-session-id>"}' | jq

# Inspect the agent's full reasoning trace:
curl http://localhost:8000/trace/<session-id> | jq
```

### Run the test suite

```bash
make test       # 61 unit tests, ~1.4s, no network, no API key needed
make evals      # 5 real-Claude eval scenarios, ~3 min, ~$0.21
```

### Optional: real climate data

```bash
# In .env:
USE_REAL_WEATHER=true

# Restart the server. get_weather now hits Open-Meteo's ECMWF ERA5 archive
# (no API key, no signup). Falls back to seeded mocks on any failure.
```

### Optional: production database

```bash
# Provision a Neon (or any Postgres) database, then:
DATABASE_URL=postgresql://user:pass@host/db  # in .env

make seed       # populates the live DB
make dev        # tools now read from Postgres instead of SQLite
```

---

## Architecture decisions (1 page)

The brief grades agent architecture (25%), tool design (20%), multi-step reasoning (20%), conversation handling (15%), code quality (10%), and product thinking (10%). Every decision below is calibrated against those weights.

**1. No agent framework.** The agent loop is ~120 lines of plain async Python in [`src/agent/orchestrator.py`](src/agent/orchestrator.py). LangChain, CrewAI, etc. would hide the loop and undermine the architecture grade. For 5 tools and one agent, a framework is over-engineering.

**2. Pydantic models drive Claude's tool schemas.** Each tool's `Input` model is the single source of truth. Claude's `input_schema` is generated via `model_json_schema()` at registration time. Add a field, both the validator and Claude's view update together. See [`src/tools/base.py`](src/tools/base.py).

**3. `SessionStore` is a Protocol from minute one.** Today: `InMemorySessionStore` (a dict). Tomorrow: `PostgresSessionStore` swaps in via one line in `src/api/dependencies.py`. The route code never changes. See [`src/sessions/store.py`](src/sessions/store.py).

**4. Tool data lives in three storage backends — same Pydantic schema across all three.**
   - **Python dicts** (Phase 1.2) — case study mock seed
   - **Neon Postgres** (Phase 1.12a) — operational store, default backend, async via SQLModel
   - **Open-Meteo Archive** (Phase 1.10) — real ECMWF ERA5 climate norms, opt-in via `USE_REAL_WEATHER=true`, falls back to (2) on any failure

   The agent loop, the system prompt, the tests — none of these change as the storage backend changes. That's the abstraction earning its keep, demonstrated three times.

**5. Errors travel as data, not exceptions.** Tool failures return a `ToolResult(is_error=True, content=...)` matching Anthropic's `tool_result` protocol. The agent loop sees the error block and adapts (or asks the user) instead of crashing the whole turn.

**6. Self-critique is a tool, not a hard-coded validation step.** The agent calls `critique_trip_plan` with its drafted plan, gets back issues + an `overall_assessment`, and decides whether to ship, surface warnings, or revise. Visible in the trace; future-compatible if we want an LLM-based critique later. See [`src/tools/critique.py`](src/tools/critique.py).

**7. Eval harness uses real Claude.** The 5 eval scenarios in [`tests/test_evals.py`](tests/test_evals.py) hit the live API and assert behavioral properties — multi-step fan-out, parallel tool calls, infeasibility refusal, mid-conversation preference adaptation, constraint conflict surfacing. Skipped by default (`pytest -m evals` or `make evals`). Cost: ~$0.21 per full run.

For deeper write-ups on each area:

| Topic | Doc |
|---|---|
| Module dependency map + request flow | [docs/architecture.md](docs/architecture.md) |
| Tool registry, schemas, dispatch contract | [docs/tool-design.md](docs/tool-design.md) |
| Annotated `run_turn()` walkthrough | [docs/agent-loop.md](docs/agent-loop.md) |
| Sessions + trace observability | [docs/conversation-state.md](docs/conversation-state.md) |
| Verified eval scoreboard | [docs/eval-results.md](docs/eval-results.md) |
| Running ADR log (12 entries) | [docs/decisions.md](docs/decisions.md) |

---

## Project structure

Matches the brief's specification verbatim:

```
src/
  agent/                  agent logic, prompts, orchestration
    config.py             pydantic-settings (anthropic key, model, env flags)
    state.py              ConversationState, TraceEvent, AgentResponse
    prompts.py            SYSTEM_PROMPT — 5-step plan + 3 honesty rules
    orchestrator.py       run_turn() — the tool-use loop
  tools/                  tool definitions
    schemas.py            Pydantic Input/Output models
    base.py               registry + async dispatch
    route.py              get_route — 3 corridors (Ams→Cph, London→Paris, London→Brighton)
    accommodation.py      find_accommodation — per-city catalog
    weather.py            get_weather — DB or Open-Meteo (env flag)
    elevation.py          get_elevation_profile
    critique.py           critique_trip_plan — deterministic self-critique
  sessions/               session storage abstraction
    store.py              SessionStore Protocol + InMemorySessionStore
  db/                     database layer (Phase 1.12a)
    engine.py             async SQLAlchemy engine + URL normalization
    models.py             SQLModel ORM tables
    seed.py               idempotent seed script
  api/                    FastAPI routes
    main.py               app factory + structlog
    routes.py             /chat, /sessions, /trace, /healthz
    dependencies.py       FastAPI Depends for store + Anthropic client
tests/                    61 unit tests + 5 evals
  conftest.py             seeded_db fixture (SQLite in-memory)
  test_tools.py           tool layer (21 tests)
  test_critique.py        critique tool (12 tests)
  test_open_meteo.py      Open-Meteo integration (6 mocked + 1 live eval)
  test_agent.py           agent loop control flow (7 tests)
  test_api.py             HTTP endpoints (13 tests)
  test_evals.py           4 real-Claude scenarios + 1 live Open-Meteo
scripts/
  smoke_test.py           real-API end-to-end agent demo
docs/                     architecture write-ups (read these for depth)
Dockerfile                Cloud Run-ready
Makefile                  install / dev / seed / test / evals / docker
```

---

## What I'd build with more time

Listed roughly in priority order — each is a clean extension of the existing architecture.

**1. Phase 1.12b — sessions on Postgres.** `SessionStore` is already a Protocol with `InMemorySessionStore` as today's implementation. A `PostgresSessionStore` using SQLModel would survive server restarts and scale across multiple Cloud Run instances. The swap is one line in `src/api/dependencies.py`.

**2. Streaming `/chat/stream` (Server-Sent Events).** Yield `text_delta` and `tool_use_start/complete` events as Claude emits them. Browser-friendly demo where the agent thinks live. The orchestrator's loop already mutates `state.trace` per event; converting to a streaming generator is mechanical.

**3. Cloud Run deploy + Firebase Auth.** Dockerfile is already Cloud-Run-shaped (listens on `$PORT`). Production URL with `gcloud run deploy --set-env-vars ANTHROPIC_API_KEY=... DATABASE_URL=...`. Firebase Auth would gate `/chat` behind a bearer token.

**4. Bonus tools.** The brief lists three optional tools that the registry pattern makes trivial to add:
   - `get_points_of_interest` — bike shops, scenic detours, rest stops per waypoint
   - `estimate_budget` — €/day breakdown across accommodation + food + ferries
   - `get_ferry_schedule` — ScandLines / DFDS departures for a date range

**5. Real route engine.** `get_route` currently reads from Postgres (3 hand-curated corridors). Wiring Komoot, BRouter, or OSRM behind the same `GetRouteOutput` schema would make any city pair work — this is the same architectural pattern as the Open-Meteo integration but for routing.

**6. Self-critique → revise loop.** Today the agent calls `critique_trip_plan` once and either ships, surfaces warnings, or stops. With more time, the system prompt would explicitly allow up to 2 critique-revise cycles, with the trace recording the iteration so reviewers can see the agent improving on its own draft.

**7. Eval harness expansion.** Add scenarios for: weather-driven rest day insertion, ferry-aware day boundaries, multi-leg trips with intermediate stops the user specifies, and adversarial inputs (typos, contradictions). Each is one new `@pytest.mark.evals` test using the same scoreboard format.

**8. Frontend (Phase 2) — Next.js chat UI** with streaming display, multimodal upload (drop a route screenshot, agent extracts intent), and an [ElevenLabs](https://elevenlabs.io) voice-conversation embed using their Conversational AI agent product. The same `/chat` endpoint serves all three surfaces.

**9. Mobile (Phase 3) — Flutter companion app**. Single screen that hits the deployed Cloud Run `/chat`. Shares zero code with the backend (correctly) — proves the agent is platform-agnostic.

**10. Observability hardening.** Currently structlog-based JSON logs and an in-process trace. Production would add OpenTelemetry spans per tool call, Sentry for error capture, and a Grafana dashboard for token usage / cost / p50-p99 latency per endpoint.

---

## License

MIT
