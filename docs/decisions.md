# Architecture Decision Log

A running log of design decisions, ordered chronologically. The "why" matters more than the "what" — code can be re-read; reasoning can't.

---

## ADR-001 · Anthropic SDK direct, no agent framework

**Decision:** Use `anthropic` Python SDK directly. No LangChain, CrewAI, Genkit, or similar.

**Why:** The rubric weights *Agent architecture* at 25% and explicitly values code that is "easy to understand and extend." A framework wrapper hides the agent loop — evaluators would open `orchestrator.py` and see `agent.run()` instead of the actual tool-use cycle. For 4 tools and a single agent, a framework is also genuine over-engineering.

**Consequence:** We hand-write the `while stop_reason == "tool_use"` loop. More code, more transparency.

---

## ADR-002 · Pydantic drives tool schemas (one source of truth)

**Decision:** Each tool's input is a Pydantic model. Claude's `input_schema` is generated from `Model.model_json_schema()` at registration time.

**Why:** Avoids the bug-magnet of writing the JSON schema by hand and the Pydantic model by hand. One change, both update. Type-checked end-to-end.

**Consequence:** Tools must declare a Pydantic input model. Trivially small cost; large correctness win.

---

## ADR-003 · Monorepo, brief's `/src` structure preserved verbatim at root

**Decision:** Single repository. `src/` (backend) and `tests/` sit at the root exactly as the brief specifies. Frontend (`web/`) and mobile (`mobile/`) are added as siblings, not nested inside `src/`.

**Why:** Brief asks for *one* "Public GitHub repo link." Two repos = two clicks for Edo. Keeping `/src` and `/tests` at root means the project structure matches the PDF on first scroll.

**Consequence:** Mixed-language tooling at the root (Python, eventually Node, eventually Dart). Manageable — each subdirectory has its own toolchain.

---

## ADR-004 · In-memory sessions for v1, `SessionStore` interface from minute one

**Decision:** Phase 1 uses an `InMemorySessionStore` (a dict keyed by `session_id`). The store is accessed through an abstract `SessionStore` Protocol so a `PostgresSessionStore` can swap in later (Phase 1.12).

**Why:** Brief says "conversation state" — never says persistent across restarts. In-memory is correct for the spec. But designing the abstraction now means the production-deploy phase is a one-line swap, not a refactor.

**Consequence:** No DB dependency until late in the build. Sessions reset on server restart in v1 (acceptable).

---

## ADR-005 · Cloud Run for production deploy (matches existing Mali pattern)

**Decision:** Deploy via `gcloud run deploy` to Google Cloud Run. Postgres via Neon (serverless) when persistence lands. Auth via Firebase Auth (matches existing Keeda Studios pattern).

**Why:** Same deployment pattern as Mali (`trellis-backend-538033318202.us-central1.run.app`). GCP project already exists; no new platform to learn. Velocity multiplier — "deployed in 30 min because I'd done it before" is a real shipping signal.

**Consequence:** Dockerfile must be Cloud-Run-shaped (listens on `$PORT`, no privileged operations). Already done — see `Dockerfile`.

---

## ADR-006 · Python 3.13 (brief requires 3.10+)

**Decision:** Develop on Python 3.13 locally. `pyproject.toml` declares `requires-python = ">=3.10"` to honor the brief's floor.

**Why:** 3.13 is what's installed. The brief's `>=3.10` requirement is satisfied. No 3.13-only syntax used so the artifact remains 3.10-portable.

**Consequence:** If a reviewer runs on 3.10, it works. If on 3.13, it works. No lock-in.

---

## ADR-007 · Agent loop is a free function, not an `Agent` class

**Decision:** `run_turn(state, user_message, *, client=None)` is a plain async function. State is passed in (a `ConversationState` Pydantic model). The Anthropic client is injectable for testing.

**Why:** The rubric values code that's "easy to understand and extend." A 100-line function with one clear loop is more legible than an `Agent` class spread across `__init__`, `_step`, `_dispatch_tools`, etc. There's no hidden state to chase.

**Consequence:** State accumulation lives in the caller (we mutate the passed-in `state`). Tests inject a fake client. /chat owns the session store.

---

## ADR-008 · System prompt is opinionated about *how* to think

**Decision:** The system prompt explicitly enumerates a 5-step plan (Understand → Shape → Plan-each-day → Present → Adapt) and three "Honesty rules" (infeasible constraints, mock-data uncertainty, impossible requests).

**Why:** Rubric weights *Multi-step reasoning* (20%) and *Conversation handling* (15%) — both are downstream of how the agent *plans*, not just what it knows. Telling Claude "plan in steps, surface conflicts, refuse impossible requests honestly" gets us those points directly. Verified in smoke test 2026-05-08: agent caught a real constraint conflict (Puttgarden has no hostels) and offered three trade-offs instead of silently violating the user's preference.

**Consequence:** System prompt is ~1500 tokens. Cost per turn is acceptable (~5¢). Future bug fixes will go in the prompt, which makes prompt-versioning a future concern (Phase 2+).

---

## ADR-009 · Tool data on Neon Postgres mid-build (Phase 1.12a)

**Decision:** After the initial mock-data version was working, migrate tool data from in-code Python dicts to Postgres-on-Neon via SQLModel. Tools become async, dispatch becomes async, the SessionStore Protocol stays in-memory for now.

**Why:** The brief allows mock data, but doing the migration *during* the build is the strongest possible proof of the abstraction. "Swap-able" goes from a claim to a demonstration. After the swap landed, the agent loop, system prompt, eval harness, and 43 tests all stayed unchanged — only the four tool functions and a new `src/db/` module changed. That's not a future-state architecture diagram; that's a verifiable diff.

**Consequence:** Tests need a `seeded_db` fixture (SQLite in-memory with the same SQLModel schema as Neon). Async tools mean async dispatch, which the orchestrator already supported via `inspect.isawaitable()`. One new env var (`DATABASE_URL`); falls back to SQLite in-memory if unset.

---

## ADR-010 · Self-critique is a tool, not a hard-coded validation step

**Decision:** Add `critique_trip_plan` as a registered tool. The agent calls it after drafting (per the system prompt), reads the result, decides whether to ship, surface warnings, or revise. Implementation is deterministic Python (rule-based pacing + accommodation pattern + consistency checks) — not another LLM call.

**Why:** Three reasons.
  1. **Visible in the trace.** Reviewers see the agent self-checking; that's worth more than a behind-the-scenes validation pass.
  2. **Forward compatibility.** If we want to swap the deterministic check for an LLM-based critique later, the registry entry doesn't change.
  3. **Multi-step reasoning rubric (20%) values the *step* explicitly.** A draft → critique → revise pattern is more multi-step than a draft → ship pattern.

**Consequence:** One extra tool in the registry. One extra iteration per agent turn. ~$0.02 of extra Claude tokens per turn. New unit tests for each rule path. S1 eval upgraded with a check that asserts critique was called.

---

## ADR-011 · Open-Meteo over OpenWeather for real climate norms

**Decision:** When integrating real weather data behind `USE_REAL_WEATHER=true`, use Open-Meteo's free Archive API instead of OpenWeather. The integration computes 5-year monthly norms from the ECMWF ERA5 reanalysis archive.

**Why:**
  1. **No API key.** The case study should be runnable by anyone reviewing it without a signup loop or secret reveal. Open-Meteo's Archive endpoint is free with no auth.
  2. **Reviewer experience.** A senior-engineering signal: pick the dependency that minimizes friction for whoever's going to read your code.
  3. **Velocity moat in action.** When the OpenWeather account locked over a weekend, switching to Open-Meteo took 45 minutes — same Pydantic schema, same env-flag toggle, same fallback chain. Demonstrating the abstraction works under unplanned dependency changes.

**Consequence:** One new dependency on `httpx` (already in the deps). Hardcoded city-to-coords table for the 21 seeded cities (faster than per-call geocoding). Falls back to DB mock for unknown cities or any failure — agent never breaks. Zero env-var secrets.

---

## ADR-012 · Eval harness with real Claude calls, opt-in via marker

**Decision:** Eval scenarios in `tests/test_evals.py` hit the real Anthropic API. Marked with `@pytest.mark.evals`; `pyproject.toml` registers the marker and `addopts = "-m 'not evals'"` excludes them by default. Run via `make evals`.

**Why:** Mocking Claude in eval tests would just be testing my mocks. The eval scenarios are about *emergent* agent behaviour — clarifying questions, honest refusals, draft-critique-revise — and the only way to know the system prompt is driving Claude correctly is to ask it. Cost is bounded (~$0.21 per full run) and acceptable for a once-a-week regression check.

**Consequence:** CI doesn't need an API key (default `pytest` skips evals). Developers run `make evals` periodically. The skip-if guard checks for a real key, not the placeholder value, so accidental commits of fake keys don't cause silent test passes.

---

## ADR-013 · User-research-driven personalisation as the Phase 2D keystone

**Decision (2026-05-09):** After the v1 was rubric-complete, I ran user interviews with cyclists and surfaced ~30 distinct feature ideas. Rather than chase the firehose, I picked one keystone and three supporting tools and **documented the rest as a roadmap** (see README, "Cyclist user research findings"):

  - **Keystone:** an onboarding wizard + `UserProfile` table + per-turn personalisation fragment in the system prompt (Phase 2D·1 + 2D·3).
  - **Three bonus tools:** `get_points_of_interest`, `estimate_budget`, `get_ferry_schedule` — each answering an interview question that came up across multiple riders (Phase 2D·2).
  - **Everything else:** roadmap, with each item tagged by what infrastructure it needs that the case-study scope doesn't cover.

**Why:** The brightest signal across the interviews was a beginner saying *"don't set them up for failure — build their profile first."* That's the brief's **S2 infeasibility-refusal scenario** but with a *human* dimension the v1 agent didn't see. A beginner asking for 130 km/day looks like a normal request to the agent unless the profile says otherwise. Fixing that *one* gap is worth more than ten cosmetic features.

**Why Postgres for profiles, not localStorage-only:** Profiles are durable, cross-device-aspirational, and exactly the data shape Postgres handles well. localStorage works for the session_id (opaque, cheap to regenerate, single-device by design) but not for a profile a user might build up over months. Same `Protocol + InMemory + Postgres` pattern as `SessionStore` (ADR-004) — third time the discipline appears, deliberate not coincidental.

**Why 3 bonus tools, not 9:** Each new tool earns its keep when the agent actually calls it. POI is multi-category (bike_shop / pub / water_fountain / toilet / hospital / market / scenic_viewpoint / cafe / bike_rental — *one tool with focused queries*, not nine noisy ones). Budget is deterministic Python so the cost math is auditable in the trace, not an LLM hallucination. Ferry data is real (DFDS, P&O, Scandlines, Stena), sampled from operator sites in May 2026. The other six interview themes (real-time hazards, animal watching, Spotify integration, fundraising widgets, ecommerce, social Wrapped) need infrastructure outside the scope of a take-home — documented as roadmap, not built.

**Why the profile fragment is fresh-per-turn, not stored in `state.messages`:** If a user's onboarding lives in the message history, prompt edits I make next week only affect *new* sessions. By appending `user_profile_context(profile)` to the system prompt at the moment of the call, every existing session benefits the moment a prompt change ships. Documented in `src/agent/orchestrator.py` and verified by the test that intercepts `kwargs` sent to the mocked Anthropic client.

**Consequence:** Backend gains `UserProfile` + `UserProfileCreate` Pydantic models, `ProfileStore` Protocol, `PostgresProfileStore`, three new tools (POI / budget / ferry), and a personalisation fragment in `prompts.py`. Frontend gains a 5-step skippable wizard, profile_id in localStorage, threaded into every `/chat` call. Live-verified end-to-end: same prompt, profile changes the agent's behaviour ("plan 100 km/day London → Paris in 4 days" + casual rider with charity in `additional_notes` → agent flags 80 km/day comfort gap, recommends 5-day option *"because your donors want you to finish strong, not limp into Paris wrecked"* — referencing the charity context unprompted on turn 2 with zero new tool calls).

---

## ADR-014 · Real route distances via BRouter, opt-in like the Open-Meteo swap

**Decision (2026-05-09):** When `USE_REAL_ROUTES=true`, `get_route` calls **BRouter** (https://brouter.de) — a free OpenStreetMap-backed bike routing engine — for real road-network distances between hand-curated anchor cities per corridor. Falls back to the existing Postgres mock on any failure. Same architectural pattern as ADR-011 (Open-Meteo over OpenWeather) — second tool to prove the abstraction works against real public data.

**Why this decision became necessary:** During Phase 2D testing I asked the agent to plan a London → Paris cycling trip and **fact-checked the response against cycle.travel and Cicerone**. Three real factual errors in the seeded data:
  - Total distance was 380 km in the seed; reality is ~398 km (Normandy variant) or ~462 km (Beauvais variant) on the signposted Avenue Verte
  - Day 1 London → Lewes was 110 km in the seed; the signposted route is closer to 140-150 km
  - Day 4 Beauvais → Paris was 140 km in the seed; BRouter direct-bike-route says 86 km, signposted route ~95-105 km

These weren't hallucinations — they were **my** mistakes baked into the mock data. The agent dutifully reasoned over them, surfaced an "honest" Day 4 problem (140 km > 80 km comfort zone) that didn't actually exist on a real route. Cyclists fact-check; the abstraction needed to support real data, not just a plausible mock.

**Why BRouter, not cycle.travel:** cycle.travel doesn't have a public API and returns 403 to programmatic fetches. Their forum says "contact us." That's a multi-day delay. BRouter:
  1. Free, no API key, public HTTP endpoint at `brouter.de/brouter`
  2. Backed by OpenStreetMap — same data foundation as the planned POI swap (consistency)
  3. Cyclist-specific routing profiles (we use `trekking`)
  4. Returns track length + ascent + GeoJSON geometry per request

**Why hand-curated anchor cities, not free-form geocoding:** A general-purpose A→B router would route arbitrary city pairs but can't tell you "Newhaven → Dieppe is a ferry hop." The corridor-based approach respects domain knowledge (the Avenue Verte's signed waypoints, the Rødby–Puttgarden ferry crossing) while still letting BRouter compute real road-network distances *between* the curated anchors. Three corridors, ~10-18 anchors each, ~30s cold cache for the whole route, instant when cached.

**Why DENSE anchors with an `is_overnight` flag (added 2026-05-09):** First cut had only the major overnight cities (London → East Grinstead → Lewes → Newhaven). BRouter's trekking profile then took the most-direct cycle-routable path between those few points — shorter than the *signposted* Avenue Verte / NCN 20 cyclists actually ride. User caught this on fact-check: 319 km via direct routing didn't match cycle.travel's 387 km signposted total. Fix: each corridor now lists every signposted intermediate town as an anchor (Wandsworth, Crystal Palace, Coulsdon, Redhill, Crawley, Forest Row in the UK; Gournay-en-Bray, Saint-Germer-de-Fly, Beaumont-sur-Oise in France). A boolean `is_overnight` flag distinguishes "overnight options shown to the agent" from "through-towns that just steer BRouter." BRouter routes through every anchor; the agent only sees overnight ones. Result: 363.7 km on Avenue Verte, within 6% of cycle.travel's 387 km. The architecture handled the upgrade without changing the agent loop, the schema, or any downstream tool.

**Caching:** Process-local dict keyed by `(lat₁, lon₁, lat₂, lon₂)` rounded to 4 dp (~11m precision). 24h TTL — road networks don't change minute-to-minute.

**Failure model:** Any BRouter error or unknown corridor → return None → caller falls back to Postgres mock. Identical to the `_use_real_weather()` fallback chain. Logs the fallback event so it's visible in observability without breaking the agent.

**Verified across three iterations of the same fact-checked prompt** ("plan a 4-day cycle from London to Paris on the Avenue Verte, 100km/day, prefer camping but a hostel every 3rd night, traveling in June"):

  - Mock seed:               380 km total, Day 4 = 140 km (fabricated; agent apologises, offers trade-offs)
  - BRouter sparse anchors:  319 km total, Day 4 = 97 km (real road network but the most-direct path, NOT the signposted route)
  - BRouter dense anchors:   363.7 km total, Day 4 = 109 km (real signposted Avenue Verte; cycle.travel reference: 387 km, we're within 6%)

**Fixing the data fixed the agent's product behaviour without changing one line of orchestrator code.**

**Consequence:** A second tool (`get_route` after `get_weather`) now ships behind an env flag with real public-data backing. The README's coverage table can promote `get_route` from "mock" to "real, opt-in." 90/90 unit tests stay green because the env flag is unset by default in tests.

---

## ADR-015 · Real accommodation + POI via Google Places API New (Phase 1.10d)

**Decision (2026-05-10):** When `USE_REAL_PLACES=true` and `GOOGLE_PLACES_API_KEY` is set, both `find_accommodation` and `get_points_of_interest` route through **Google Places API (New)** — Nearby Search for the listings, Text Search for city geocoding, and the Places Photos endpoint for image URLs. Falls back to the seed catalog (now in Postgres) on any failure or for categories without a Places type. Same architectural pattern as ADR-011 (Open-Meteo) and ADR-014 (BRouter).

**Why now, not before:** ADR-014 made the routing layer real-data-backed; the agent now reasons over real road distances on real signposted variants. The next-biggest "case-study smell" in the response was hand-curated accommodation lists ("Camping Municipal de Beauvais · €18 · bike-friendly") with no ratings, no reviews, no photos. A reviewer skimming the response could tell the data was static. Replacing it lifts every downstream surface — chat response, route map cards, the eventual UI redesign — into the same production-shaped tier as routing and weather.

**Why Google Places (New) and not OSM Overpass:** Both were on the table. Overpass is free, no key, generous coverage of campsites and historic POI tagging, and matches the "OpenStreetMap data foundation" thread already established by BRouter. Google Places (New) added four things Overpass cannot:
  1. **Aggregate user ratings** (1.0-5.0) and **review counts** — a quality signal beyond hand-curation. "Generator Hostel — 4.5★ (2,847 reviews)" beats "Generator Hostel" full stop.
  2. **First-party photos** via the Places Photos endpoint, single-URL fetch in a `<img>` tag — directly enables the day-card / accommodation-card UI redesign.
  3. **Price-tier signals** (`PRICE_LEVEL_INEXPENSIVE` / `MODERATE` / `EXPENSIVE` / `VERY_EXPENSIVE`) — a coarse but real budget input the agent can convert to EUR midpoints.
  4. **Strong urban coverage globally** — Overpass varies by region; Google's index is consistently dense in the cities the corridor visits.

The case-study reviewer is reading on a screen, not a terminal. Photos and ratings are the unfair advantage. Worth the API key and the modest per-call cost (case-study volume is ~50 requests; well inside Google's $200/mo free credit).

**Why a separate flag (`USE_REAL_PLACES`) and not a single `USE_REAL_DATA` master switch:** Each integration has its own failure mode, its own cost profile, and its own deploy gate (Open-Meteo: free; BRouter: free; Google Places: paid w/ free credit). Independent flags let me deploy one at a time, monitor each on Cloud Run, and roll back per-source if anything misbehaves. Compounds the lesson from ADR-011/014.

**Heuristic mapping the schemas don't carry:**
  - **AccommodationType inference** — Google's `lodging` is a bucket; we read the per-place `types` array to distinguish `hostel` / `guest_house` / `bed_and_breakfast` from generic `hotel`, and treat `campground` / `rv_park` as `camping`.
  - **EUR-per-night estimate** — Google returns a tier, not a number. The module ships a 4×4 lookup (`_PRICE_LEVEL_DEFAULTS_EUR`) that maps `(price_level, accom_type)` to a reasonable midpoint. Agent surfaces these as "estimated" rather than live prices.
  - **Bike-friendliness** — no Places field. Default True for camping/hostels/guesthouses; cautious True for hotels with a note that the agent can challenge in the response.

**Why `water_fountain` and `toilet` stay seed-only:** No clean Places type exists. Fudging via text search ("water fountain near London") is unreliable enough to mislead. The real path returns `None` for those categories so the caller falls back to the seed catalog cleanly — partial real + partial seed in the same response would confuse the agent's quality reasoning.

**Schema change:** `Accommodation` and `POI` gain optional `rating`, `review_count`, `photo_url`, `place_id`, plus `price_level` on `Accommodation`. All `None` on the seed path so existing eval fixtures and downstream consumers stay valid; the UI redesign reads them as "show photo if present, else fall back to text card." Pydantic validates either path identically.

**Smoke verification (live API):**
  - Beauvais accommodation: 5 results, all with photos + ratings (e.g. *Hôtel Mercure Beauvais Centre Cathédrale · 4.4★ · 627 reviews · 0.4 km*)
  - London bike shops: 5 results (Condor Cycles 4.8★ · 681, Decathlon 4.6★ · 4,515, Fully Charged 4.8★ · 475)
  - Seed-only category (water fountain) correctly returns None → caller falls back to the curated seed list

**Failure model:** Mirrors ADR-011/014. Any HTTP error, missing API key, or unrecognised location → return None → caller transparently falls back to Postgres seed. Logged via structlog so observability sees the fallback rate without crashing the agent.

**Consequence:** Three of the eight tools now ship with real public-data backends; two more (`get_elevation_profile`, partially redundant with BRouter; `get_ferry_schedule`, no clean free API) remain seed by deliberate decision rather than oversight. The README's data-coverage table promotes `find_accommodation` and `get_points_of_interest` from "mock" to "real, opt-in." 90/90 unit tests stay green (conftest forces `USE_REAL_PLACES=""` in test runs alongside `USE_REAL_ROUTES` and `USE_REAL_WEATHER`).
