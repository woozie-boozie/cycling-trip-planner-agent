# Tool design

The tool layer is **20% of the rubric grade**, second only to agent architecture. This doc explains exactly how it works and why each choice was made.

## The contract — Pydantic IS the schema

Every tool has three things:

```python
# 1. Pydantic input model — what Claude sends
class GetRouteInput(BaseModel):
    start: str = Field(description="Starting city, e.g. 'Amsterdam'")
    end: str
    daily_km_target: float = Field(default=80, gt=0, le=300)

# 2. Pydantic output model — what we send back to Claude
class GetRouteOutput(BaseModel):
    start: str
    end: str
    total_distance_km: float
    estimated_days: int
    waypoints: list[Waypoint]
    notes: str | None = None

# 3. The implementation
@register_tool(
    name="get_route",
    description="Get a cycling route between two cities. Use this FIRST...",
    input_model=GetRouteInput,
    output_model=GetRouteOutput,
)
async def get_route(input: GetRouteInput) -> GetRouteOutput:
    # query Postgres, build the response
    ...
```

That's it. The decorator does the rest:

1. Stores the tool in `TOOL_REGISTRY` (a global dict, populated at import time)
2. Pre-computes the Anthropic-shaped tool definition by calling `Input.model_json_schema()` — Claude needs this for its `tools=` parameter on `messages.create()`
3. Validates incoming arguments against `Input` before invoking the handler
4. Validates the handler's return against `Output` before serializing

**One source of truth.** Add a field to `GetRouteInput`, and (a) Claude's view of the tool updates automatically and (b) any malformed call from Claude is caught by Pydantic and returned as a `ToolResult(is_error=True)` instead of corrupting state.

This is the single most important design choice in the tool layer. See ADR-002.

## The dispatch contract

```python
async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
    """
    Returns ToolResult, NEVER raises. Errors travel as data.
    """
```

`dispatch` does five things, in order, each with its own error path:

1. **Resolve the tool by name.** Unknown tool → `ToolResult(content={"error": "unknown_tool", ...}, is_error=True)`
2. **Validate input.** Pydantic `ValidationError` → `ToolResult(error="invalid_arguments", details=[...], is_error=True)`. The agent sees the error and can retry or ask the user for clarification.
3. **Invoke handler** (sync or async — `inspect.isawaitable(...)` decides). Any exception → `ToolResult(error="tool_exception", message=..., is_error=True)`
4. **Validate output type** (defense against bugs in tool code) → `ToolResult(error="bad_output_type", ...)`
5. **Serialize via `model_dump(mode="json")`** → `ToolResult(content=dict, is_error=False)`

Why every error becomes data: the agent loop sees `is_error=True` in a `tool_result` block and Claude knows to adapt. If we raised exceptions, the orchestrator would have to catch and translate, and we'd lose the protocol-level coherence with Anthropic's tool-use spec.

## The five tools

| Tool | Purpose | Backend |
|---|---|---|
| **`get_route`** | Route between two cities, with ordered waypoints, distances, ferry flags | Postgres (`routes` + `waypoints` tables) |
| **`find_accommodation`** | Per-city catalog filtered by type (camping/hostel/hotel/guesthouse) | Postgres (`accommodations` table) |
| **`get_weather`** | Climate norms for a (location, month) pair | Postgres OR Open-Meteo Archive (env-flag toggle) |
| **`get_elevation_profile`** | Terrain difficulty per segment (gain, max grade, difficulty rating) | Postgres (`elevation_segments`, both directions seeded) |
| **`critique_trip_plan`** | Self-critique on the agent's drafted plan (deterministic Python) | Pure compute |

The first four are required by the brief. `critique_trip_plan` is added in Step 2 to lock in the multi-step reasoning rubric.

## Why three storage backends behind `get_weather`

This is the cleanest demonstration of the abstraction:

```
                    ┌── USE_REAL_WEATHER=true ──► Open-Meteo Archive (real ERA5)
get_weather(loc,m) ─┤                                  │
                    │                              fail (network/unknown city)
                    │                                  │
                    └────────────────────────────► Postgres weather_norms ──► seeded mock
                                                       │
                                                  fail (unseeded)
                                                       │
                                                  GenericFallback (notes="Mock data")
```

Same `GetWeatherOutput` Pydantic schema regardless of which backend served the request. The agent only knows about the `notes` field — that's where each backend leaves a fingerprint:

- Real ERA5: `"Real climate norm — Open-Meteo Archive (ECMWF ERA5), 2021–2025, 150 June days sampled."`
- DB seeded: `null` or location-specific guidance
- Generic fallback: `"Mock data — exact climate record unavailable for this location/month."`

The agent surfaces uncertainty honestly because the system prompt instructs it to pass the `notes` through. That's how *"South Downs YHA — no campsite found in Lewes; hostel fallback"* ended up in real /chat output during the build (see [eval-results.md](eval-results.md)).

## The async story

`dispatch` and all tool handlers are async. Why:

- FastAPI is async-native; matching the framework idiom keeps the call stack uniform
- Real APIs (Open-Meteo today, Komoot/Booking later) are I/O bound — `await client.get(...)` doesn't block the event loop
- `dispatch` uses `inspect.isawaitable(result)` so a future tool author can write a sync handler if they want; we await only when needed
- Postgres access via SQLModel + asyncpg is async, so a non-async tool dispatching to async DB code would need `asyncio.run()` per call — costly and weird

Result: 5 parallel tool calls in one Claude response dispatch in **40-300ms total** against Postgres-on-Neon. See the [trace](eval-results.md#example-trace) for proof.

## Adding a new tool

The whole flow:

```python
# 1. In src/tools/schemas.py — Pydantic Input/Output models
class GetPointsOfInterestInput(BaseModel):
    location: str
    radius_km: float = Field(default=5, gt=0, le=50)

class POI(BaseModel):
    name: str
    category: Literal["bike_shop", "cafe", "scenic", "rest_stop"]
    distance_km: float

class GetPointsOfInterestOutput(BaseModel):
    location: str
    results: list[POI]

# 2. In src/tools/poi.py — handler + decorator
from src.tools.base import register_tool

@register_tool(
    name="get_points_of_interest",
    description="Find bike shops, cafes, scenic spots near a location...",
    input_model=GetPointsOfInterestInput,
    output_model=GetPointsOfInterestOutput,
)
async def get_points_of_interest(input: GetPointsOfInterestInput) -> GetPointsOfInterestOutput:
    # query Postgres or whatever
    ...

# 3. In src/tools/__init__.py — import to trigger registration
from src.tools import poi  # noqa
```

Total: ~3 files touched, no changes to the agent loop, the orchestrator, the system prompt, or the `/chat` endpoint. The Pydantic schema flows through to Claude automatically.

## See also

- [`docs/agent-loop.md`](agent-loop.md) — how dispatch is called from the loop
- [`docs/decisions.md`](decisions.md) — ADR-002 (Pydantic-driven schemas), ADR-010 (critique-as-tool)
