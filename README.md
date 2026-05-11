# Cycling Trip Planner Agent

An AI agent that helps a cyclist plan a multi-day bike trip through conversation. Built as a case study for Affinity Labs.

### 🚴 Try it live

| | |
|---|---|
| **Web app** | **https://cycling-trip-planner-nu.vercel.app** |
| **Backend API** | https://cycling-trip-planner-backend-5ko5j6u6mq-ew.a.run.app |
| **API docs (Swagger)** | https://cycling-trip-planner-backend-5ko5j6u6mq-ew.a.run.app/docs |

The fastest tour: open the web app → click any of the three route cards (London → Paris, Amsterdam → Copenhagen, London → Brighton) → pick a month + daily distance + accommodation mix → hit "Plan it" → watch the agent stream a day-by-day plan with real route distances (BRouter), real climate norms (Open-Meteo ECMWF ERA5), and real accommodation listings with ratings + photos (Google Places).

**Stack — split-stack production deploy:**
- **Frontend** — Next.js 16 + React 19 + Tailwind v4 + shadcn/ui + react-leaflet + Mapbox Static Images, hosted on **Vercel** (edge CDN)
- **Backend** — Python 3.10+ + FastAPI + Anthropic Claude (sonnet-4-5) + Pydantic + SQLModel + structlog, hosted on **Google Cloud Run** (`europe-west1`)
- **Database** — Neon Postgres (managed) for tool data + user profiles + conversation sessions
- **External APIs** — Anthropic · BRouter (real bike routes) · Open-Meteo Archive (real climate) · Google Places API New (real accommodation + POI)
- **Streaming** — Server-Sent Events for live `text_delta` + `tool_use_complete` + `iteration_end` events

---

## What it does

Talk to the agent in natural language and it produces a day-by-day cycling plan with route, terrain, weather, and accommodation — adapting as you change your preferences mid-conversation. **Live**, hitting the production backend:

```bash
curl -X POST https://cycling-trip-planner-backend-5ko5j6u6mq-ew.a.run.app/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Plan a 4-day cycle from London to Paris on the Avenue Verte, 100km/day, prefer camping but a hostel every 3rd night, traveling in June"}'
```

The agent will: shape the route via real BRouter cycling-network data (London → Lewes → Newhaven → Dieppe → Paris on the signposted Avenue Verte V16a, ~364 km), present **multiple route variants** with their distinguishing features and trade-offs, gather elevation + weather + accommodation per segment **in parallel** (~15-30 tool calls in one Claude turn), call its **self-critique** tool to check the draft against the user's constraints (often firing 2-3 times in a single response — draft → critique → revise → re-critique → ship), then return a structured day-by-day plan with a "Heads up" section that honestly surfaces any constraints it couldn't fully honor (e.g. *"Day 6 is 114 km — 42% over your stated comfort"*) plus real accommodation suggestions with ratings + review counts + photos pulled live from Google Places.

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
curl http://localhost:8000/health
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
make test       # 90 unit tests, ~1.6s, no network, no API key needed
make evals      # 6 real-Claude eval scenarios + 1 live Open-Meteo, ~3 min, ~$0.21
```

### Optional: real climate data (Phase 1.10 · Open-Meteo)

```bash
# In .env:
USE_REAL_WEATHER=true

# Restart the server. get_weather now hits Open-Meteo's ECMWF ERA5 archive
# (no API key, no signup). Falls back to seeded mocks on any failure.
```

### Optional: real route distances (Phase 1.10b · BRouter)

```bash
# In .env:
USE_REAL_ROUTES=true

# Restart the server. get_route now computes real road-network distances
# via BRouter (https://brouter.de) — a free OpenStreetMap-backed bike
# routing engine. No API key, no signup. Falls back to seeded mocks on
# unknown corridor or any BRouter failure. Returns multi-variant data
# where multiple signposted routes exist (e.g. London→Paris has V16a
# Beauvais, Oise/Chantilly, and Gisors variants).
#
# Result: London→Paris (Avenue Verte V16a) reports ~364 km — within 6%
# of cycle.travel's signposted reference. ADR-014 documents the swap.
```

### Optional: real accommodation + POI data (Phase 1.10d · Google Places)

```bash
# In .env:
USE_REAL_PLACES=true
GOOGLE_PLACES_API_KEY=AIza...

# Restart the server. find_accommodation and get_points_of_interest now
# hit Google Places API (New) — Nearby Search for listings, Text Search
# for city geocoding, Places Photos for image URLs. Free $200/mo Google
# Maps Platform credit covers case-study volume by orders of magnitude.
# Falls back to the seed catalog for unknown locations or any failure.
#
# Categories without a clean Places type (water_fountain, toilet) stay
# on seed by design — partial real + partial seed in one response would
# confuse the agent's quality judgement. ADR-015 documents the swap.
#
# Get a key: console.cloud.google.com → Places API (New) → Credentials.
```

### Optional: production database

```bash
# Provision a Neon (or any Postgres) database, then:
DATABASE_URL=postgresql://user:pass@host/db  # in .env

make seed       # populates the live DB
make dev        # tools now read from Postgres instead of SQLite
                # sessions automatically use PostgresSessionStore (Phase 1.12b)
                # when DATABASE_URL is set — survives Cloud Run cold starts
```

---

## Architecture decisions (1 page)

The brief grades agent architecture (25%), tool design (20%), multi-step reasoning (20%), conversation handling (15%), code quality (10%), and product thinking (10%). Every decision below is calibrated against those weights.

**1. No agent framework.** The agent loop is ~120 lines of plain async Python in [`src/agent/orchestrator.py`](src/agent/orchestrator.py). LangChain, CrewAI, etc. would hide the loop and undermine the architecture grade. For 5 tools and one agent, a framework is over-engineering.

**2. Pydantic models drive Claude's tool schemas.** Each tool's `Input` model is the single source of truth. Claude's `input_schema` is generated via `model_json_schema()` at registration time. Add a field, both the validator and Claude's view update together. See [`src/tools/base.py`](src/tools/base.py).

**3. `SessionStore` is a Protocol from minute one.** Phase 1.4 shipped `InMemorySessionStore` (a dict). Phase 1.12b added `PostgresSessionStore` — auto-selected when `DATABASE_URL` is set, falls back to in-memory otherwise. Conversation state survives Cloud Run cold starts because state is JSON-serialised into one row per session (no relational decomposition of trace events — they're append-only and consumed in-order). See [`src/sessions/postgres_store.py`](src/sessions/postgres_store.py).

**4. Tool data lives in five storage backends — same Pydantic schema across all five.**
   - **Python dicts** (Phase 1.2) — case study mock seed
   - **Neon Postgres** (Phase 1.12a) — operational store, default backend, async via SQLModel
   - **Open-Meteo Archive** (Phase 1.10) — real ECMWF ERA5 climate norms, opt-in via `USE_REAL_WEATHER=true`, falls back to (2) on any failure
   - **BRouter** (Phase 1.10b) — real OpenStreetMap-backed bike routing, opt-in via `USE_REAL_ROUTES=true`, falls back to (2) on unknown corridor or BRouter failure. Caught real factual errors in the seed data when fact-checked against cycle.travel — see ADR-014.
   - **Google Places API New** (Phase 1.10d) — real accommodation + POI listings with ratings, review counts, photos, price tiers. Opt-in via `USE_REAL_PLACES=true` + `GOOGLE_PLACES_API_KEY`. Falls back to (2) on missing key, network failure, or seed-only POI categories (water_fountain, toilet). See ADR-015.

   The agent loop, the system prompt, the tests — none of these change as the storage backend changes. That's the abstraction earning its keep, demonstrated **five times** across three tools (`get_weather`, `get_route`, `find_accommodation` + `get_points_of_interest`).

**5. Errors travel as data, not exceptions.** Tool failures return a `ToolResult(is_error=True, content=...)` matching Anthropic's `tool_result` protocol. The agent loop sees the error block and adapts (or asks the user) instead of crashing the whole turn.

**6. Self-critique is a tool, not a hard-coded validation step.** The agent calls `critique_trip_plan` with its drafted plan, gets back issues + an `overall_assessment`, and decides whether to ship, surface warnings, or revise. Visible in the trace; future-compatible if we want an LLM-based critique later. See [`src/tools/critique.py`](src/tools/critique.py).

**7. Eval harness uses real Claude.** The 6 eval scenarios in [`tests/test_evals.py`](tests/test_evals.py) hit the live API and assert behavioral properties — multi-step fan-out, parallel tool calls, infeasibility refusal, mid-conversation preference adaptation, constraint conflict surfacing, and **silent constraint relaxation transparency** (S7 — added TDD-first after a Gemini fact-check caught the agent silently dropping a daily km target instead of naming the trade-off). Plus 1 live Open-Meteo eval that asserts climate norms without a Claude call. Skipped by default (`pytest -m evals` or `make evals`). Cost: ~$0.21 per full run.

**8. Split-stack production deploy** (Phase 1.13) — Vercel CDN serves the Next.js frontend with edge caching + automatic image optimisation; Cloud Run hosts the FastAPI backend with full container control for streaming SSE + persistent DB connection pools; Neon Postgres is independent of both compute platforms. Same Docker image runs in dev and prod. Three independent layers, each with a clean swap path, joined by HTTP + a published `NEXT_PUBLIC_API_URL`. Secret Manager (with `tr -d '\n'` discipline) for production secrets.

For deeper write-ups on each area:

| Topic | Doc |
|---|---|
| Module dependency map + request flow | [docs/architecture.md](docs/architecture.md) |
| Tool registry, schemas, dispatch contract | [docs/tool-design.md](docs/tool-design.md) |
| Annotated `run_turn()` walkthrough | [docs/agent-loop.md](docs/agent-loop.md) |
| Sessions + trace observability | [docs/conversation-state.md](docs/conversation-state.md) |
| Verified eval scoreboard | [docs/eval-results.md](docs/eval-results.md) |
| Running ADR log (15 entries) | [docs/decisions.md](docs/decisions.md) |

---

## Project structure

Matches the brief's specification verbatim, plus the frontend (`web/`) and the production deploy machinery:

```
src/
  agent/                  agent logic, prompts, orchestration
    config.py             pydantic-settings (anthropic key, model, env flags)
    state.py              ConversationState, TraceEvent, AgentResponse
    prompts.py            SYSTEM_PROMPT — 5-step plan + honesty rules incl. S7
    orchestrator.py       run_turn() + run_turn_stream() — the tool-use loop
    streaming.py          SSE event accumulator for /chat/stream
  tools/                  tool definitions (8 tools — 4 brief-required + critique + 3 bonus)
    schemas.py            Pydantic Input/Output models with rich-data fields
    base.py               registry + async dispatch
    route.py              get_route — DB-backed catalog
    route_real.py         BRouter real-data path (Phase 1.10b · multi-variant)
    accommodation.py      find_accommodation — DB or Google Places (env flag)
    weather.py            get_weather — DB or Open-Meteo (env flag)
    elevation.py          get_elevation_profile
    critique.py           critique_trip_plan — incl. S7 constraint-drift check
    poi.py                get_points_of_interest — bonus: 9 categories
    ferry.py              get_ferry_schedule — bonus
    budget.py             estimate_budget — bonus: cost + calories
    places_real.py        Google Places real-data path (Phase 1.10d)
  sessions/               session + profile storage abstraction
    store.py              SessionStore Protocol + InMemorySessionStore
    postgres_store.py     PostgresSessionStore (Phase 1.12b — Cloud-Run-safe)
    profile_store.py      UserProfile Protocol + InMemory + Postgres impls
  db/                     database layer
    engine.py             async SQLAlchemy engine + URL normalization
    models.py             SQLModel ORM tables (incl. SessionRow + UserProfileRow)
    seed.py               idempotent seed script
  api/                    FastAPI routes
    main.py               app factory + structlog + lifespan handler (init_db on startup)
    routes.py             /chat, /chat/stream, /profile, /sessions, /trace, /health
    dependencies.py       FastAPI Depends — env-driven store selection
    schemas.py            request/response models
web/                      Next.js 16 frontend (Phase 2 + 2D + 2E)
  app/                    App Router pages
  components/             route-gallery, route-config-form, route-card,
                          chat-input, message-bubble, trace-panel, route-map,
                          onboarding/wizard, ui/ (shadcn/ui primitives)
  lib/                    api.ts, mapbox.ts, corridors.ts, session.ts, profile.ts
tests/                    90 unit tests + 6 evals + 1 live Open-Meteo
  conftest.py             seeded_db fixture (SQLite in-memory)
  test_tools.py           tool layer (44 tests — incl. POI, ferry, budget bonuses)
  test_critique.py        critique tool (13 tests — incl. S7 constraint drift)
  test_open_meteo.py      Open-Meteo integration (6 mocked + 1 live eval)
  test_agent.py           agent loop control flow (7 tests)
  test_api.py             HTTP endpoints (20 tests — incl. /chat/stream + /profile)
  test_evals.py           6 real-Claude scenarios (S1-S4 + S7) + 1 live Open-Meteo
scripts/
  smoke_test.py           real-API end-to-end agent demo
  smoke_places.py         Google Places live-API smoke test
docs/                     architecture write-ups (read these for depth)
                          15 ADRs in decisions.md
Dockerfile                Cloud Run-ready (listens on $PORT)
Makefile                  install / dev / seed / test / evals / docker
```

---

## Shipped after the original brief

Items I called out in the original "what I'd build with more time" that ended up landing inside the case-study window:

**✅ Phase 1.12b — sessions on Postgres.** `PostgresSessionStore` mirrors `PostgresProfileStore`. Auto-selected when `DATABASE_URL` is set; in-memory otherwise. JSON-blob storage of the full `ConversationState` (no relational decomposition of trace events). Survives Cloud Run cold starts.

**✅ Streaming `/chat/stream` (Server-Sent Events).** Backend yields `session`, `text_delta`, `tool_use_complete`, `iteration_end`, and `done` events as Claude emits them. Frontend consumes via `fetch` + `ReadableStream`, accumulates assistant text into a live-updating bubble, populates the trace panel on `done`. Multi-turn continuity verified with a 404-retry recovery on stale-session fallback.

**✅ Cloud Run deploy + split-stack production.** Backend on Cloud Run (`europe-west1`) with Secret Manager for credentials. Frontend on Vercel (Next.js 16). Neon Postgres independent of both. Same Docker container in dev and prod. End-to-end verified with a 45/45 tool-call user session at $1.46 cost.

**✅ Self-critique → revise loop.** Confirmed in production: critique fires 2-3 times within a single user turn — draft → critique → revise → re-critique → ship. Visible in the trace panel as `iter 4` + `iter 6` critique calls.

**✅ Real accommodation + POI data.** Phase 1.10d added Google Places API New behind `USE_REAL_PLACES=true` + `GOOGLE_PLACES_API_KEY`. Returns ratings, review counts, photos, price tiers. Falls back to seed for unsupported categories (water_fountain, toilet) by design. ADR-015.

**✅ Frontend with route gallery + Mapbox terrain thumbnails.** Phase 2E replaced the text empty state with three Mapbox `outdoors-v12` thumbnails + interactive config form (chip-style pickers for month, daily km, accommodation, hostel-every-N pattern). Click → guided plan submission with live prompt preview.

---

## What I'd build with more time (still on the roadmap)

Listed roughly in priority order — each is a clean extension of the existing architecture.

**1. Firebase Anonymous Auth.** Backend `verify_optional_bearer()` dependency. Frontend `signInAnonymously()` on app load, attaches Firebase ID token to every API call. Stops the public Cloud Run URL from being a free Anthropic billing piñata if the URL ever spreads. Skipped during the initial deploy for deadline reasons; trivial to layer on after submission.

**2. Free-form route engine.** `get_route` ships with three hand-curated anchor corridors (Avenue Verte, Amsterdam→Copenhagen, London→Brighton) — BRouter computes real distances between the anchors. Adding Nominatim geocoding for arbitrary city pairs + a runtime corridor-detection step would make any A→B request work without expanding the anchor catalog. Same `GetRouteOutput` schema, same BRouter call pattern.

**3. City-name disambiguation in Google Places geocoding.** Caught live in production: text search for "Harlingen camping" can hit Harlingen, Texas instead of Harlingen, Netherlands. The agent currently surfaces this transparently ("the tool returned Texas results — real Harlingen has X, Y, Z") which is itself good behaviour, but a 5-line fix in `places_real.py` to include country in the geocoding query would prevent the gotcha entirely.

**4. Inline plan-card rendering.** Today the agent's response renders as markdown text. The next iteration parses the multi-day plan and renders each day as a card with the new Google Places photos inline (so accommodation suggestions show up as photo cards, not text bullets). Biggest "less text-heavy" win remaining.

**5. Eval harness expansion.** Add scenarios for: weather-driven rest day insertion, ferry-aware day boundaries, multi-leg trips with intermediate stops the user specifies, and adversarial inputs (typos, contradictions). Each is one new `@pytest.mark.evals` test using the same scoreboard format.

**6. Mobile (Phase 3) — Flutter companion app.** Single screen that hits the deployed Cloud Run `/chat`. Shares zero code with the backend (correctly) — proves the agent is platform-agnostic.

**7. Observability hardening.** Currently structlog-based JSON logs and an in-process trace. Production would add OpenTelemetry spans per tool call, Sentry for error capture, and a Grafana dashboard for token usage / cost / p50-p99 latency per endpoint.

---

## Cyclist user research findings (May 2026)

Mid-build I ran interviews with ~10 cyclists — weekend tourers, commuters, charity riders, randonneurs. They surfaced ~30 feature ideas, far more than fit a 5-day case study. Rather than chase the firehose, I grouped the findings into five themes, **shipped the keystone + three supporting tools** that one of the themes pointed to, and document the rest here as a roadmap. (Full reasoning in `docs/decisions.md`, ADR-013.)

The keystone: *"don't set them up for failure — build their profile first"* (a beginner asking for 130 km/day is the brief's S2 infeasibility scenario with a human dimension the v1 agent didn't see). That insight became the onboarding wizard + `UserProfile` table + per-turn personalisation fragment in the system prompt — all live and verified end-to-end.

### Theme A · Real-time route hazards · 🟡 Roadmap

Live road conditions, weather windows, and safety telemetry were the most frequent ask.

- Live pothole density per segment (Strava heat-map style)
- Tractor / lorry frequency on rural roads
- Per-segment safety rating (cyclist-friendly index)
- Live weather updates during the ride (not just monthly norms)
- Sunrise / sunset times for daily start/finish planning
- Live wind direction + strength along the corridor

**Needs:** real-time data feeds, location streaming, partnerships with Strava/Komoot/Met Office. Not 5-day scope.

### Theme B · Local content & discovery · 🟡 Roadmap

Cycling is also tourism. Riders wanted the agent to surface what makes each segment *worth* riding, not just survivable.

- "What animals can I see along this route in June" (rewilding sites, raptor sanctuaries)
- Fun facts about the area (Domesday-Book-era abbeys, WWII trivia, local legends)
- Names of the regions you ride through (the *Pays de Bray* between Forges and Beauvais)
- Scenic-route prompts (extra 8 km but the cliff path is iconic)
- Local-produce stops (cider farms, cheesemakers, farmers' markets)
- Souvenir-shopping recommendations
- Photography stops worth a 5-minute pause

**Partial coverage today:** `get_points_of_interest` covers `scenic_viewpoint` + `market` categories. The deeper "stories of the land" content needs a separate content layer (curated text, ideally from a travel-writing partner).

### Theme C · Logistics & fueling · ✅ Mostly shipped

The bread-and-butter "I need this NOW" questions. This was the highest-actionability theme — and the new bonus tools cover most of it.

- Toilets and water fountains along the route — ✅ `get_points_of_interest(categories=['toilet','water_fountain'])`
- Bike repair when something breaks — ✅ `get_points_of_interest(categories=['bike_shop'])`
- Hospitals nearby for safety reference — ✅ `get_points_of_interest(categories=['hospital'])`
- Supermarkets for snack resupply — ✅ `get_points_of_interest(categories=['market'])`
- Pubs (with games / live music) — ✅ `get_points_of_interest(categories=['pub'])` (games + music as `notes`)
- Bike rental at the destination — ✅ `get_points_of_interest(categories=['bike_rental'])`
- Cafes / coffee stops — ✅ `get_points_of_interest(categories=['cafe'])`
- Calorie planning per day ("how much fuel do I need the night before") — ✅ `estimate_budget` returns `daily_calorie_estimate` (1800 base + 30 per km cycled)

Roadmap items in this theme:
- 🟡 Live opening hours (today's hours, not catalogued hours)
- 🟡 E-bike charging stations (needs a real-data feed)

### Theme D · Social & community · 🟡 Roadmap

Cyclists wanted the experience to extend beyond the ride itself.

- "How many people are also doing this route right now"
- Built-in fundraising integration (JustGiving / GoFundMe deep links + km-per-£ math)
- Monthly Wrapped-style summary of the rider's stats
- Public profile pages with completed-routes badges
- Trip sharing (export to Strava, Komoot, social media)
- Social-reach metrics ("your fundraising shared by 23 people")

**Needs:** persistent multi-month longitudinal data, presence/WebSocket infrastructure, OAuth integrations with at least three third parties (Strava, JustGiving, social platforms). Each is a multi-day build on its own.

### Theme E · Lifestyle & commerce · 🟡 Roadmap

The further-out asks — interesting product directions but they pull the brief well past a planning agent.

- Spotify integration ("queue me a 4-hour ride playlist matching the elevation profile")
- Live GPS tracker for friends/family while riding
- "Box of stuff" delivery to the next overnight stop (charger forgot, spare tube needed)
- E-bike charging-station marketplace
- Bike rental + sale marketplace at start/end cities
- Souvenir shopping along the route

**Needs:** payments, live tracking, third-party OAuth, fulfilment partners. Adjacent product, not 5-day scope.

### How this maps to the build

| Theme | Coverage in this build |
|---|---|
| A · Real-time hazards | Roadmap |
| B · Local content & discovery | `scenic_viewpoint`, `market` shipped; deeper content layer roadmap |
| C · Logistics & fueling | **Shipped** (`get_points_of_interest` covers 7 categories; `estimate_budget` covers calories) |
| D · Social & community | Roadmap |
| E · Lifestyle & commerce | Roadmap |
| Cross-cutting · personalisation | **Shipped** (onboarding wizard + `UserProfile` + per-turn personalisation fragment) |

The discipline of *deciding what NOT to build* and writing it up here matters more than any single shipped item. ADR-013 in `docs/decisions.md` records why the keystone was chosen over the alternatives.

---

## License

MIT
