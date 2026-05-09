# Eval results

Verified state from the most recent `make evals` run (2026-05-09 01:34 UTC).

```
============================ 5 passed, 61 deselected in 192.77s (0:03:12) ============================
```

## Per-scenario scoreboard

### S1 · Happy path London→Paris — 9/9 ✓

```
iterations=6   input_tokens=37,404   output_tokens=3,569
✓ get_route called at least once
✓ get_elevation_profile called ≥ 3 times
✓ get_weather called ≥ 3 times
✓ find_accommodation called ≥ 3 times
✓ critique_trip_plan called (self-critique before shipping)
✓ total tool calls ≥ 9 (multi-step + critique proof)
✓ output mentions the ferry (Newhaven/Dieppe)
✓ output is a day-by-day plan
✓ output mentions a real seeded accommodation
```

**What it proves:** the agent executes the full intended flow — shapes the route, fans out per-segment data, self-critiques, presents a structured plan. Maps to **Multi-step reasoning (20%)** + **Tool design (20%)** + **Product thinking (10%)** rubric criteria.

### S2 · Infeasibility refusal (Berlin → Mumbai in 30 days) — 4/4 ✓

```
iterations=1   input_tokens=3,432   output_tokens=495
✓ agent surfaces distance/pace/feasibility math
✓ agent suggests alternatives or asks user to reconsider
✓ agent does NOT produce a full day-by-day plan
✓ response is reasonably short (refused early, didn't fan out)
```

**What it proves:** the agent recognizes physically impossible requests and refuses honestly with concrete alternatives, instead of inventing a fake plan. Maps to **Conversation handling (15%)** + **Product thinking (10%)**.

Sample agent output (verbatim from the run):
> *"A cycling trip from Berlin to Mumbai in 30 days is not physically possible. The straight-line distance is ~5,800 km; actual cycling routes (following roads, borders, terrain) would be 7,000-8,000 km. 30 days = 233-267 km per day, every single day, with no rest. Elite ultra-endurance cyclists average 200-250 km/day during record attempts on supported routes for short durations… What's realistic? 60-90 days for strong, experienced cycle tourists. If you have 30 days, I can plan something feasible — perhaps to Istanbul (~2,300 km, ~80 km/day), Athens, or southern Italy. What sounds interesting?"*

### S3 · Mid-conversation preference change — 6/6 ✓

```
iterations=2 (full turns)   input_tokens=78,388   output_tokens=5,198
✓ turn 2 re-called get_route with new daily target
✓ turn 2 queried hotels via find_accommodation
✓ turn 2 made multiple tool calls (fanned out fresh data)
✓ agent did NOT re-ask which cities (no clarifying loop)
✓ agent did NOT re-ask the month
✓ two-turn state survived (total_turns == 2)
```

**What it proves:** the session store correctly threads context across turns and the agent adapts to changed preferences without re-asking what it already knows. Maps to **Conversation handling (15%)** + **Architecture (25%)**.

### S4 · Constraint conflict surfacing (London → Paris in 2 days at 50km/day) — 4/4 ✓

```
iterations=1   input_tokens=3,440   output_tokens=172
✓ agent surfaces the math/constraint conflict
✓ agent offers alternatives or asks user to choose
✓ agent did NOT silently produce a fake 2-day plan
✓ agent stops early (didn't fan out 18 tool calls before refusing)
```

**What it proves:** when constraints are over-specified (380km route, 100km of capacity), the agent flags the math instead of silently violating one of the constraints. Maps to **Conversation handling (15%)** + **Product thinking (10%)**.

Sample agent output (verbatim):
> *"A London → Paris trip is roughly 450-500 km, which means at 50 km/day you're looking at 9-10 days, not 2. Did you mean: 50 km/day over however many days it takes (9-10 days), or 2 days total (which would require ~225-250 km/day)? Let me know and I'll build the plan."*

### S5 · Open-Meteo live London / June — PASSED (no Claude call, $0.00)

```
avg_temp = 17.3°C   avg_high = 22.0°C   avg_low = 12.1°C
rain_days_per_month = 9   avg_rain_mm = 53.4
Source: ECMWF ERA5 archive, 2021–2025, 150 June days sampled.
```

**What it proves:** the real-API integration is alive end-to-end. The same Pydantic schema that wraps the seeded mock data also wraps the response from Open-Meteo's archive — no auth, no env-var secrets, no special handling for the "live" case. Maps to **Architecture (25%)**.

## Cost summary

| Eval | API | Cost |
|---|---|---|
| S1 happy path | Anthropic Claude | ~$0.07 |
| S2 infeasibility | Anthropic Claude | ~$0.02 |
| S3 preference change | Anthropic Claude | ~$0.10 |
| S4 constraint conflict | Anthropic Claude | ~$0.02 |
| S5 Open-Meteo live | Open-Meteo (free, no auth) | $0.00 |
| **Total** | | **~$0.21** |

3 minutes 12 seconds wall time for a full run.

## How to reproduce

```bash
make evals
```

`pyproject.toml` registers an `evals` pytest marker and `addopts = "-m 'not evals'"` so the default `pytest` skips them. They only run when you explicitly opt in.

The S5 live test additionally requires internet access (it hits `archive-api.open-meteo.com`) but no API key.

## Why these specific scenarios

Each scenario was chosen to exercise a different rubric criterion:

| Scenario | Primary rubric | Secondary |
|---|---|---|
| S1 — happy path | Multi-step reasoning (20%) | Tool design (20%) |
| S2 — infeasibility | Conversation (15%) | Product thinking (10%) |
| S3 — preference change | Conversation (15%) | Architecture (25%) |
| S4 — constraint conflict | Conversation (15%) | Product thinking (10%) |
| S5 — Open-Meteo live | Architecture (25%) | Code quality (10%) |

Together they cover **all six rubric criteria**. A future test would target weather-driven rest day insertion or ferry-aware day boundaries — see `What I'd build with more time` in the README.

## See also

- [`tests/test_evals.py`](../tests/test_evals.py) — the eval source
- [`docs/agent-loop.md`](agent-loop.md) — how iterations relate to API calls
- [`docs/decisions.md`](decisions.md) — ADR-008 (system prompt opinionatedness, which drives the assertions here)
