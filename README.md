# Cycling Trip Planner Agent

An AI agent that helps a cyclist plan a multi-day bike trip through conversation.

> **Built for:** Affinity Labs case study assessment
> **Stack:** Python 3.10+ · FastAPI · Anthropic Claude · Pydantic
> **Status:** 🚧 Phase 1.1 — scaffolding

---

## What it does

Talk to the agent in natural language ("I want to cycle from Amsterdam to Copenhagen, ~100km a day, prefer camping but a hostel every 4th night, June") and it produces a day-by-day plan with route, accommodation, weather, and elevation, adapting as you change your preferences mid-conversation.

## Quick start

Requires Python 3.10+ (we use 3.13) and an Anthropic API key.

```bash
git clone https://github.com/woozie-boozie/cycling-trip-planner-agent.git
cd cycling-trip-planner-agent

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY

make install      # creates .venv and installs deps
make dev          # runs FastAPI on http://localhost:8000

# in another terminal
curl http://localhost:8000/healthz
```

## Project structure

Matches the brief's specification verbatim:

```
src/
  agent/    — agent logic, prompts, orchestration
  tools/    — tool definitions
  api/      — FastAPI routes
tests/      — tests for tools and agent
docs/       — architecture write-ups
```

## Architecture

See [`docs/architecture.md`](docs/architecture.md) (added in Phase 1.13).

## Build phases

This project is being built in phases. See [`docs/decisions.md`](docs/decisions.md) for the running decision log.

| Phase | Status | What |
|---|---|---|
| 1.1 — Scaffold | ✅ in progress | Project structure, FastAPI runs, healthz |
| 1.2 — Tool layer | ⏳ | 4 required tools, Pydantic schemas, registry |
| 1.3 — Agent orchestrator | ⏳ | Tool loop, system prompt |
| 1.4 — `/chat` endpoint | ⏳ | Conversation state, sessions |
| 1.5+ — Polish | ⏳ | Self-critique, evals, streaming, deploy |
| 2 — Frontend | ⏳ | Next.js chat, multimodal, voice |
| 3 — Mobile | ⏳ | Flutter companion |

## What I'd build with more time

Filled in at end of Phase 1.13.

## License

MIT
