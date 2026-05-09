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
