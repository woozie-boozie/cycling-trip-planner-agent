"""get_route — real-data path via BRouter (Phase 1.10b · multi-variant).

Opt-in via ``USE_REAL_ROUTES=true`` in the environment.

Multi-variant — what changed (2026-05-09 · Phase 1.10c):
--------------------------------------------------------
First cut returned one route per corridor — the agent silently picked the
"obvious" path. User pushed back: real cyclists choose between variants
based on trade-offs (distance vs scenery, cathedral towns vs rural villages,
inland vs coastal). So now each corridor maps to a *list* of variants,
each with its own:

  - anchor chain (different roads, different distances)
  - distinguishing features the rider should know about
  - honest trade-offs they're accepting
  - "best for" suitability hint

The agent presents 2-3 variants side-by-side; the user picks; the agent
goes deep on the chosen one.

Why this matters for the architecture
-------------------------------------
Per-segment tools (``get_elevation_profile``, ``get_weather``,
``find_accommodation``) consume city-name strings from
``GetRouteOutput.waypoints``. With multi-variant, the agent's flow is:
  1. ``get_route`` → all variants returned
  2. agent presents comparison; user picks
  3. agent calls per-segment tools using the chosen variant's waypoints

The legacy ``waypoints``/``total_distance_km``/``notes`` fields on
``GetRouteOutput`` are kept (mirrored from the default variant) so
existing test fixtures and downstream consumers don't break.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from dataclasses import dataclass

import httpx
import structlog

from src.tools.schemas import DayPlan, GetRouteOutput, RouteVariant, Waypoint

log = structlog.get_logger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Per-corridor anchor catalog — one entry per signposted variant
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    name: str
    country: str
    lat: float
    lon: float
    is_ferry_arrival: bool = False
    # Through-towns set is_overnight=False — they steer BRouter along the
    # signposted route but don't surface in the agent-facing waypoint list.
    is_overnight: bool = True


@dataclass(frozen=True)
class CorridorVariant:
    """A single variant within a corridor — name + anchors + presentation."""

    name: str  # short identifier, e.g. "v16a_beauvais"
    title: str  # human-readable, e.g. "V16a Beauvais — fastest signposted"
    description: str
    anchors: list[Anchor]
    distinguishing_features: list[str]
    trade_offs: list[str]
    best_for: str
    is_default: bool = False


# ---- Avenue Verte — 3 variants ─────────────────────────────────────────────

# Shared UK side: London → ... → Newhaven (signposted Avenue Verte UK).
_AVENUE_VERTE_UK: list[Anchor] = [
    Anchor("London", "United Kingdom", 51.5074, -0.1278),
    Anchor("Wandsworth", "United Kingdom", 51.4530, -0.1845, is_overnight=False),
    Anchor("Crystal Palace", "United Kingdom", 51.4216, -0.0746, is_overnight=False),
    Anchor("Coulsdon", "United Kingdom", 51.3208, -0.1395, is_overnight=False),
    Anchor("Redhill", "United Kingdom", 51.2400, -0.1714, is_overnight=False),
    Anchor("Crawley", "United Kingdom", 51.1092, -0.1872, is_overnight=False),
    Anchor("East Grinstead", "United Kingdom", 51.1283, -0.0094),
    Anchor("Forest Row", "United Kingdom", 51.1006, 0.0312, is_overnight=False),
    Anchor("Lewes", "United Kingdom", 50.8736, 0.0080),
    Anchor("Newhaven", "United Kingdom", 50.7935, 0.0570),
]

# Variant A · V16a Beauvais — fastest signposted French side.
_AV_V16A_FR: list[Anchor] = [
    Anchor("Dieppe", "France", 49.9229, 1.0784, is_ferry_arrival=True),
    Anchor("Forges-les-Eaux", "France", 49.6111, 1.5439),
    Anchor("Gournay-en-Bray", "France", 49.4869, 1.7269, is_overnight=False),
    Anchor("Saint-Germer-de-Fly", "France", 49.4317, 1.7747, is_overnight=False),
    Anchor("Beauvais", "France", 49.4314, 2.0807),
    Anchor("Beaumont-sur-Oise", "France", 49.1432, 2.2825, is_overnight=False),
    Anchor("Cergy-Pontoise", "France", 49.0356, 2.0707),
    Anchor("Paris", "France", 48.8566, 2.3522),
]

# Variant B · Oise/Chantilly — scenic detour via Senlis & Chantilly chateaux.
_AV_OISE_CHANTILLY_FR: list[Anchor] = [
    Anchor("Dieppe", "France", 49.9229, 1.0784, is_ferry_arrival=True),
    Anchor("Forges-les-Eaux", "France", 49.6111, 1.5439),
    Anchor("Gournay-en-Bray", "France", 49.4869, 1.7269, is_overnight=False),
    Anchor("Saint-Germer-de-Fly", "France", 49.4317, 1.7747, is_overnight=False),
    Anchor("Beauvais", "France", 49.4314, 2.0807),
    Anchor("Clermont", "France", 49.3779, 2.4140, is_overnight=False),
    Anchor("Senlis", "France", 49.2069, 2.5817),
    Anchor("Chantilly", "France", 49.1939, 2.4598),
    Anchor("Cergy-Pontoise", "France", 49.0356, 2.0707, is_overnight=False),
    Anchor("Paris", "France", 48.8566, 2.3522),
]

# Variant C · Gisors / Pays de Bray — western route, no Beauvais cathedral
# but the Epte valley + medieval Gisors keep + Vexin villages.
_AV_GISORS_FR: list[Anchor] = [
    Anchor("Dieppe", "France", 49.9229, 1.0784, is_ferry_arrival=True),
    Anchor("Forges-les-Eaux", "France", 49.6111, 1.5439),
    Anchor("Gournay-en-Bray", "France", 49.4869, 1.7269, is_overnight=False),
    Anchor("Gisors", "France", 49.2806, 1.7783),
    Anchor("Vétheuil", "France", 49.0833, 1.6378, is_overnight=False),
    Anchor("Conflans-Sainte-Honorine", "France", 48.9988, 2.0985, is_overnight=False),
    Anchor("Cergy-Pontoise", "France", 49.0356, 2.0707),
    Anchor("Paris", "France", 48.8566, 2.3522),
]


_AVENUE_VERTE_VARIANTS: list[CorridorVariant] = [
    CorridorVariant(
        name="v16a_beauvais",
        title="V16a Beauvais — fastest signposted",
        description=(
            "The most direct of the signposted Avenue Verte variants. Crosses "
            "the Pays de Bray to Beauvais (UNESCO Gothic cathedral, tallest "
            "choir vault in the world), then drops to Cergy via Beaumont-sur-Oise."
        ),
        anchors=_AVENUE_VERTE_UK + _AV_V16A_FR,
        distinguishing_features=[
            "Beauvais Cathedral (tallest Gothic choir vault, 48 m)",
            "Pays de Bray cheese country (Neufchâtel AOC)",
            "Mostly disused railway path on French side — gentle gradients",
            "Shortest of the three Avenue Verte variants",
        ],
        trade_offs=[
            "Misses the Senlis/Chantilly chateaux loop",
            "More A-road sections in the UK approach to East Grinstead",
        ],
        best_for=(
            "targeting the fastest signposted crossing with one cathedral stop"
        ),
        is_default=True,
    ),
    CorridorVariant(
        name="oise_chantilly",
        title="Oise/Chantilly — scenic chateaux loop",
        description=(
            "Adds the Senlis (medieval town) + Chantilly (chateau, racecourse, "
            "lace) detour after Beauvais. ~20–30 km longer than V16a but the "
            "most photogenic variant — three world-class historic stops."
        ),
        anchors=_AVENUE_VERTE_UK + _AV_OISE_CHANTILLY_FR,
        distinguishing_features=[
            "Chantilly Château + Grand Stables (one of France's finest)",
            "Senlis medieval old town with intact Gallo-Roman walls",
            "Beauvais Cathedral retained",
            "Forest of Chantilly cycle paths",
        ],
        trade_offs=[
            "20–30 km longer than V16a (one extra day for casual riders)",
            "Chantilly + Senlis can be expensive for food and accommodation",
        ],
        best_for=(
            "riders prioritising heritage + photography over distance, "
            "or honeymoon/special-occasion trips"
        ),
    ),
    CorridorVariant(
        name="gisors_western",
        title="Gisors — western Epte valley",
        description=(
            "Skips Beauvais entirely. From Gournay-en-Bray, drops south via "
            "Gisors (12th-century keep, William the Conqueror history) and "
            "the Epte valley to the Seine. Quieter, more rural, fewer tourists."
        ),
        anchors=_AVENUE_VERTE_UK + _AV_GISORS_FR,
        distinguishing_features=[
            "Gisors medieval keep (Knights Templar history)",
            "Epte valley — the historic Norman/French frontier",
            "Vexin Français Regional Natural Park",
            "Far fewer tourists than the Beauvais/Chantilly variants",
        ],
        trade_offs=[
            "No Beauvais Cathedral",
            "More rural — food + accommodation density lower",
            "Rougher signposting in places (V32 + local cycle network)",
        ],
        best_for=(
            "experienced tourers wanting solitude + rural Normandy/Vexin "
            "over headline tourist stops"
        ),
    ),
]


# ---- Amsterdam → Copenhagen — 2 variants ───────────────────────────────────

_AMS_INLAND: list[Anchor] = [
    Anchor("Amsterdam", "Netherlands", 52.3676, 4.9041),
    Anchor("Hoorn", "Netherlands", 52.6425, 5.0597),
    Anchor("Groningen", "Netherlands", 53.2194, 6.5665),
    Anchor("Bremen", "Germany", 53.0793, 8.8017),
    Anchor("Hamburg", "Germany", 53.5511, 9.9937),
    Anchor("Lübeck", "Germany", 53.8655, 10.6866),
    Anchor("Puttgarden", "Germany", 54.5021, 11.2378),
    Anchor("Rødby", "Denmark", 54.6907, 11.3469, is_ferry_arrival=True),
    Anchor("Vordingborg", "Denmark", 55.0085, 11.9105),
    Anchor("Copenhagen", "Denmark", 55.6761, 12.5683),
]

_AMS_COASTAL_EV12: list[Anchor] = [
    Anchor("Amsterdam", "Netherlands", 52.3676, 4.9041),
    Anchor("IJmuiden", "Netherlands", 52.4602, 4.6103, is_overnight=False),
    Anchor("Den Helder", "Netherlands", 52.9612, 4.7600),
    Anchor("Harlingen", "Netherlands", 53.1740, 5.4220, is_overnight=False),
    Anchor("Leeuwarden", "Netherlands", 53.2012, 5.7999),
    Anchor("Groningen", "Netherlands", 53.2194, 6.5665, is_overnight=False),
    Anchor("Bremerhaven", "Germany", 53.5396, 8.5810),
    Anchor("Cuxhaven", "Germany", 53.8665, 8.7010, is_overnight=False),
    Anchor("Hamburg", "Germany", 53.5511, 9.9937),
    Anchor("Lübeck", "Germany", 53.8655, 10.6866),
    Anchor("Travemünde", "Germany", 53.9620, 10.8730, is_overnight=False),
    Anchor("Puttgarden", "Germany", 54.5021, 11.2378),
    Anchor("Rødby", "Denmark", 54.6907, 11.3469, is_ferry_arrival=True),
    Anchor("Vordingborg", "Denmark", 55.0085, 11.9105),
    Anchor("Copenhagen", "Denmark", 55.6761, 12.5683),
]


_AMS_TO_CPH_VARIANTS: list[CorridorVariant] = [
    CorridorVariant(
        name="inland_ev7_hybrid",
        title="Inland EV7/12 hybrid — fastest",
        description=(
            "Cuts inland through Hoorn and Groningen rather than following "
            "the coast. The popular 'Amsterdam → Copenhagen tour' that most "
            "do — flat, well-signposted, ~9 days for an 80 km/day rider."
        ),
        anchors=_AMS_INLAND,
        distinguishing_features=[
            "Mostly LF / EuroVelo 7 (Sun Route) signage in NL/DE",
            "Fewer ferry/coastal complications",
            "Bremen + Hamburg for hostel density and food variety",
            "Rødby–Puttgarden ferry crossing (~45 min, bikes free)",
        ],
        trade_offs=[
            "Misses the North Sea coast and Wadden Sea UNESCO area",
            "Fewer dramatic seaside stretches",
        ],
        best_for=(
            "riders prioritising distance/day balance and flat, well-signposted "
            "infrastructure"
        ),
        is_default=True,
    ),
    CorridorVariant(
        name="coastal_ev12",
        title="Coastal EV12 North Sea — scenic but long",
        description=(
            "True EuroVelo 12 along the North Sea coast — Den Helder, Frisian "
            "islands gateway, Wadden Sea National Park (UNESCO), Bremerhaven "
            "maritime museum. Adds 250+ km vs the inland route."
        ),
        anchors=_AMS_COASTAL_EV12,
        distinguishing_features=[
            "Wadden Sea UNESCO World Heritage coast",
            "Frisian islands gateway at Harlingen",
            "Bremerhaven Auswandererhaus + maritime museum",
            "Cuxhaven sea-bathing town",
        ],
        trade_offs=[
            "~250 km longer than the inland route (12+ days at 80 km/day)",
            "Stronger headwind risk — North Sea westerlies",
            "Some coastal gravel sections; pace slower than tarmac inland",
        ],
        best_for=(
            "riders who want the EuroVelo 12 'proper' experience with time "
            "to enjoy the coast — not for tight schedules"
        ),
    ),
]


# ---- London → Brighton — 2 variants ────────────────────────────────────────

_LDN_TO_BRI_NCN20: list[Anchor] = [
    Anchor("London", "United Kingdom", 51.5074, -0.1278),
    Anchor("Wandsworth", "United Kingdom", 51.4530, -0.1845, is_overnight=False),
    Anchor("Mitcham", "United Kingdom", 51.4040, -0.1683, is_overnight=False),
    Anchor("Coulsdon", "United Kingdom", 51.3208, -0.1395, is_overnight=False),
    Anchor("Crawley", "United Kingdom", 51.1092, -0.1872, is_overnight=False),
    Anchor("Cuckfield", "United Kingdom", 51.0007, -0.1421),
    Anchor("Burgess Hill", "United Kingdom", 50.9551, -0.1316, is_overnight=False),
    Anchor("Brighton", "United Kingdom", 50.8225, -0.1372),
]

# Avenue Verte UK + Lewes detour to Brighton — adds the Sussex Weald + South
# Downs scenic stretch, popular with cyclists who want a proper South Downs
# overnight before the coastal arrival.
_LDN_TO_BRI_AV_LEWES: list[Anchor] = [
    Anchor("London", "United Kingdom", 51.5074, -0.1278),
    Anchor("Crystal Palace", "United Kingdom", 51.4216, -0.0746, is_overnight=False),
    Anchor("Coulsdon", "United Kingdom", 51.3208, -0.1395, is_overnight=False),
    Anchor("Redhill", "United Kingdom", 51.2400, -0.1714, is_overnight=False),
    Anchor("East Grinstead", "United Kingdom", 51.1283, -0.0094),
    Anchor("Forest Row", "United Kingdom", 51.1006, 0.0312, is_overnight=False),
    Anchor("Lewes", "United Kingdom", 50.8736, 0.0080),
    Anchor("Brighton", "United Kingdom", 50.8225, -0.1372),
]


_LDN_TO_BRI_VARIANTS: list[CorridorVariant] = [
    CorridorVariant(
        name="ncn20",
        title="NCN 20 signposted — fastest",
        description=(
            "The classic National Cycle Network 20 route, the standard "
            "London→Brighton signposted ride. Ridden by ~30,000 cyclists "
            "every June for the British Heart Foundation event."
        ),
        anchors=_LDN_TO_BRI_NCN20,
        distinguishing_features=[
            "Wandle Trail through south London",
            "Cuckoo Trail disused railway in East Sussex",
            "Ditchling Beacon climb (the famous final ascent)",
            "Best signposting of any UK cycle route",
        ],
        trade_offs=[
            "Urban south London first 25 km can feel stop-start",
            "Brighton seafront finish but no Lewes/South Downs detour",
        ],
        best_for=(
            "the canonical day-ride or a fast 2-day weekend; charity riders"
        ),
        is_default=True,
    ),
    CorridorVariant(
        name="avenue_verte_lewes",
        title="Avenue Verte UK + Lewes — South Downs detour",
        description=(
            "Follows the Avenue Verte UK signposted route via East Grinstead, "
            "Forest Row, Lewes — adding the South Downs scenic spur and the "
            "historic county town of Lewes (Anne of Cleves' house, castle). "
            "Brighton arrival via the South Downs Way."
        ),
        anchors=_LDN_TO_BRI_AV_LEWES,
        distinguishing_features=[
            "Forest of Ashdown (Winnie-the-Pooh country)",
            "Lewes — Tudor architecture, castle, real-ale pubs",
            "South Downs ridge approach to Brighton",
            "Quieter than NCN 20 — lower traffic on Sussex lanes",
        ],
        trade_offs=[
            "10–20 km longer than NCN 20",
            "More climbing (Ashdown Forest + South Downs ridge)",
            "Less signposting on the Lewes→Brighton spur",
        ],
        best_for=(
            "riders wanting a proper 2-day trip with a Lewes overnight, or "
            "those who care more about countryside than the canonical route"
        ),
    ),
]


# Master corridor catalog — start/end (case-insensitive) → variants.
_CORRIDORS: dict[tuple[str, str], list[CorridorVariant]] = {
    ("london", "paris"): _AVENUE_VERTE_VARIANTS,
    ("paris", "london"): [
        # Reverse direction: same variants but reversed anchor order.
        CorridorVariant(
            name=v.name,
            title=v.title,
            description=v.description,
            anchors=list(reversed(v.anchors)),
            distinguishing_features=v.distinguishing_features,
            trade_offs=v.trade_offs,
            best_for=v.best_for,
            is_default=v.is_default,
        )
        for v in _AVENUE_VERTE_VARIANTS
    ],
    ("amsterdam", "copenhagen"): _AMS_TO_CPH_VARIANTS,
    ("copenhagen", "amsterdam"): [
        CorridorVariant(
            name=v.name,
            title=v.title,
            description=v.description,
            anchors=list(reversed(v.anchors)),
            distinguishing_features=v.distinguishing_features,
            trade_offs=v.trade_offs,
            best_for=v.best_for,
            is_default=v.is_default,
        )
        for v in _AMS_TO_CPH_VARIANTS
    ],
    ("london", "brighton"): _LDN_TO_BRI_VARIANTS,
    ("brighton", "london"): [
        CorridorVariant(
            name=v.name,
            title=v.title,
            description=v.description,
            anchors=list(reversed(v.anchors)),
            distinguishing_features=v.distinguishing_features,
            trade_offs=v.trade_offs,
            best_for=v.best_for,
            is_default=v.is_default,
        )
        for v in _LDN_TO_BRI_VARIANTS
    ],
}


# ---------------------------------------------------------------------------
# BRouter HTTP client — unchanged from previous iteration
# ---------------------------------------------------------------------------

_BROUTER_URL = "https://brouter.de/brouter"
_BROUTER_PROFILE = "trekking"
_BROUTER_TIMEOUT = 15.0
_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h

_segment_cache: dict[tuple[float, float, float, float], tuple[float, float, float]] = {}
_cache_timestamps: dict[tuple[float, float, float, float], float] = {}

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = httpx.AsyncClient(timeout=_BROUTER_TIMEOUT)
    return _client


async def aclose_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _cache_key(a: Anchor, b: Anchor) -> tuple[float, float, float, float]:
    return (round(a.lat, 4), round(a.lon, 4), round(b.lat, 4), round(b.lon, 4))


def _cached_segment(a: Anchor, b: Anchor) -> tuple[float, float, float] | None:
    key = _cache_key(a, b)
    ts = _cache_timestamps.get(key)
    if ts is None or (time.time() - ts) > _CACHE_TTL_SECONDS:
        return None
    return _segment_cache.get(key)


def _cache_segment(
    a: Anchor, b: Anchor, distance_km: float, ascend_m: float, time_s: float
) -> None:
    key = _cache_key(a, b)
    _segment_cache[key] = (distance_km, ascend_m, time_s)
    _cache_timestamps[key] = time.time()


async def _brouter_segment(
    client: httpx.AsyncClient, a: Anchor, b: Anchor
) -> tuple[float, float, float]:
    """Real road distance for one cycling segment a→b. Returns
    (distance_km, ascend_m, time_seconds). Raises on any failure."""
    cached = _cached_segment(a, b)
    if cached is not None:
        return cached

    params = {
        "lonlats": f"{a.lon},{a.lat}|{b.lon},{b.lat}",
        "profile": _BROUTER_PROFILE,
        "alternativeidx": "0",
        "format": "geojson",
    }
    resp = await client.get(_BROUTER_URL, params=params)
    resp.raise_for_status()
    payload = resp.json()
    features = payload.get("features", [])
    if not features:
        raise ValueError(f"BRouter returned no features for {a.name}→{b.name}")
    props = features[0].get("properties", {})
    track_length_m = float(props["track-length"])
    ascend_m = float(props.get("filtered ascend", 0))
    time_s = float(props.get("total-time", 0))
    distance_km = track_length_m / 1000.0
    _cache_segment(a, b, distance_km, ascend_m, time_s)
    return distance_km, ascend_m, time_s


# ---------------------------------------------------------------------------
# Variant building
# ---------------------------------------------------------------------------


def use_real_routes() -> bool:
    """True when the env flag is set. Same convention as USE_REAL_WEATHER."""
    return os.getenv("USE_REAL_ROUTES", "").strip().lower() in {"true", "1", "yes", "on"}


def _normalize(s: str) -> str:
    return s.strip().lower()


def _variants_for(start: str, end: str) -> list[CorridorVariant] | None:
    return _CORRIDORS.get((_normalize(start), _normalize(end)))


def _ferry_notes(anchors: list[Anchor]) -> str | None:
    ferry = next((a for a in anchors if a.is_ferry_arrival), None)
    if ferry is None:
        return None
    if _normalize(ferry.name) in {"rødby", "puttgarden"}:
        return (
            "Includes the Rødby–Puttgarden ferry across the Fehmarn Belt — a fixed link "
            "tunnel is under construction but the ferry remains the standard option as of "
            "this dataset. Allow ~45 minutes for the crossing."
        )
    if _normalize(ferry.name) in {"dieppe", "newhaven"}:
        return (
            "Includes the Newhaven–Dieppe ferry across the English Channel (DFDS, "
            "~4 hours). Cyclists travel as foot passengers — bikes carry no surcharge "
            "above the foot-passenger fare (from £33 each way, ~£40–55 in summer)."
        )
    return "Route includes a ferry crossing — check schedules in advance."


def _suggest_day_plan(
    waypoints: list[Waypoint], daily_km_target: float
) -> list[DayPlan]:
    """Variance-minimising day-allocation via dynamic programming.

    Picks n_days overnight boundaries that minimise the sum of squared
    deviations from the user's daily km target. The previous greedy "snap
    each boundary to the closest waypoint" approach occasionally produced
    lopsided splits (e.g. Avenue Verte @ 80 km/day → 134/38 because Cergy
    was 1.1 km closer to the d=4 ideal boundary than Beauvais). The DP
    fixes this by considering all combinations.

    State:
        dp[d][i] = minimum sum-of-squared-deviations to end day d at
                   waypoint index i (1 <= d <= n_days, d <= i <= len-1).
    Transition:
        dp[d][i] = min over k in [d-1, i)  of
                   dp[d-1][k] + (cum[i] - cum[k] - target) ** 2
    Base:
        dp[0][0] = 0
    Answer:
        dp[n_days][len-1], with parent pointers for reconstruction.

    Complexity: O(n_days · len² · ...) ≈ O(n_days · len²). For our sizes
    (≤18 waypoints, ≤11 days) this is trivially fast.

    Notes per day still flag long/short/ferry deviations.
    """
    if len(waypoints) < 2:
        return []
    total_km = waypoints[-1].distance_from_start_km
    raw_n_days = max(1, round(total_km / daily_km_target))
    # Can't have more days than there are unique stops to end them at.
    n_days = min(raw_n_days, len(waypoints) - 1)

    if n_days == 1:
        overnight_indices: list[int] = [0, len(waypoints) - 1]
    else:
        n = len(waypoints)
        target = daily_km_target
        cum = [w.distance_from_start_km for w in waypoints]
        INF = float("inf")

        # dp[d][i] = min cost ending day d at waypoint i; parent[d][i] = k
        dp = [[INF] * n for _ in range(n_days + 1)]
        parent = [[-1] * n for _ in range(n_days + 1)]
        dp[0][0] = 0.0

        for d in range(1, n_days + 1):
            # Day d ends somewhere in [d, n-1]; on the last day we MUST
            # end at n-1, but we still compute all candidates and only
            # use n-1 at reconstruction.
            for i in range(d, n):
                best = INF
                best_k = -1
                # Day d started at the prior boundary k in [d-1, i).
                for k in range(d - 1, i):
                    if dp[d - 1][k] >= INF:
                        continue
                    day_km = cum[i] - cum[k]
                    cost = dp[d - 1][k] + (day_km - target) ** 2
                    if cost < best:
                        best = cost
                        best_k = k
                dp[d][i] = best
                parent[d][i] = best_k

        # Reconstruct: must end at n-1 after exactly n_days days.
        overnight_indices = [n - 1]
        d = n_days
        i = n - 1
        while d > 0:
            k = parent[d][i]
            overnight_indices.append(k)
            i = k
            d -= 1
        overnight_indices.reverse()

    days: list[DayPlan] = []
    for i in range(len(overnight_indices) - 1):
        start_idx = overnight_indices[i]
        end_idx = overnight_indices[i + 1]
        day_waypoints = waypoints[start_idx + 1 : end_idx + 1]
        cycling_km = round(sum(w.segment_km for w in day_waypoints), 1)
        has_ferry = any(w.is_ferry_required for w in day_waypoints)

        deviation_pct = ((cycling_km / daily_km_target) - 1) * 100 if daily_km_target else 0
        notes_parts: list[str] = []
        # If the day is dominated by a ferry crossing (cycling < 30% of target),
        # describe it as a ferry day instead of flagging it as "short" against
        # the target — the rider isn't expected to clock target km on a ferry day.
        if has_ferry and cycling_km < daily_km_target * 0.3:
            notes_parts.append(f"ferry crossing day ({cycling_km:.0f} km cycling)")
        else:
            if cycling_km > daily_km_target * 1.15:
                notes_parts.append(f"long day, {deviation_pct:+.0f}% vs target")
            elif cycling_km < daily_km_target * 0.5:
                notes_parts.append(f"short day, {deviation_pct:+.0f}% vs target")
            if has_ferry:
                notes_parts.append("includes ferry crossing")
        notes = "; ".join(notes_parts) if notes_parts else None

        days.append(
            DayPlan(
                day=i + 1,
                from_city=waypoints[start_idx].name,
                to_city=waypoints[end_idx].name,
                cycling_km=cycling_km,
                has_ferry=has_ferry,
                waypoints_visited=[w.name for w in waypoints[start_idx : end_idx + 1]],
                notes=notes,
            )
        )
    return days


async def _build_variant(
    client: httpx.AsyncClient,
    cv: CorridorVariant,
    daily_km_target: float,
) -> RouteVariant:
    """Compute a RouteVariant by calling BRouter for each adjacent anchor pair."""
    cumulative_km = 0.0
    pending_segment_km = 0.0
    waypoints: list[Waypoint] = []
    if cv.anchors[0].is_overnight:
        waypoints.append(
            Waypoint(
                name=cv.anchors[0].name,
                country=cv.anchors[0].country,
                distance_from_start_km=0.0,
                segment_km=0.0,
                is_ferry_required=False,
            )
        )

    for prev, curr in zip(cv.anchors[:-1], cv.anchors[1:], strict=True):
        if curr.is_ferry_arrival:
            hop_km = 0.0
        else:
            hop_km, _ascend, _seconds = await _brouter_segment(client, prev, curr)
        cumulative_km += hop_km
        pending_segment_km += hop_km
        if curr.is_overnight:
            waypoints.append(
                Waypoint(
                    name=curr.name,
                    country=curr.country,
                    distance_from_start_km=round(cumulative_km, 1),
                    segment_km=round(pending_segment_km, 1),
                    is_ferry_required=curr.is_ferry_arrival,
                )
            )
            pending_segment_km = 0.0

    total = round(cumulative_km, 1)
    estimated_days = max(1, math.ceil(total / daily_km_target))
    notes = _ferry_notes(cv.anchors)
    day_plan = _suggest_day_plan(waypoints, daily_km_target)

    return RouteVariant(
        name=cv.name,
        title=cv.title,
        description=cv.description,
        total_distance_km=total,
        estimated_days=estimated_days,
        waypoints=waypoints,
        suggested_day_plan=day_plan,
        distinguishing_features=list(cv.distinguishing_features),
        trade_offs=list(cv.trade_offs),
        best_for=cv.best_for,
        notes=notes,
        is_default=cv.is_default,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def fetch_real_route(
    start: str,
    end: str,
    daily_km_target: float,
    *,
    client: httpx.AsyncClient | None = None,
) -> GetRouteOutput | None:
    """Build a multi-variant ``GetRouteOutput`` with real BRouter distances.

    Returns ``None`` when:
      - the corridor isn't in our anchor catalog (caller should fall back)
      - BRouter fails for any segment of any variant (caller should fall back)
    """
    corridor_variants = _variants_for(start, end)
    if corridor_variants is None:
        return None

    if client is None:
        client = await _get_client()

    try:
        # Build all variants in sequence (cache makes later ones fast).
        variants: list[RouteVariant] = []
        for cv in corridor_variants:
            variants.append(await _build_variant(client, cv, daily_km_target))
    except (httpx.HTTPError, ValueError, KeyError) as e:
        log.warning(
            "route_real.fallback",
            reason=type(e).__name__,
            error=str(e)[:200],
            start=start,
            end=end,
        )
        return None

    # Pick the default variant for the legacy fields. Falls back to first
    # variant if no is_default flag is set.
    default = next((v for v in variants if v.is_default), variants[0])

    log.info(
        "route_real.success",
        start=start,
        end=end,
        variants_count=len(variants),
        default_variant=default.name,
        default_total_km=default.total_distance_km,
    )

    real_data_note = (
        f"Distances computed via BRouter on the signposted routes. "
        f"{len(variants)} variant{'s' if len(variants) > 1 else ''} available — "
        f"agent should present them side-by-side and let the user pick. "
        f"Cached for 24h."
    )
    legacy_notes = (
        f"{default.notes}\n\n{real_data_note}" if default.notes else real_data_note
    )

    return GetRouteOutput(
        start=start,
        end=end,
        variants=variants,
        # Legacy single-variant fields mirror the default for back-compat.
        total_distance_km=default.total_distance_km,
        estimated_days=default.estimated_days,
        waypoints=default.waypoints,
        notes=legacy_notes,
    )
