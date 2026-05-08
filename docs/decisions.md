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
