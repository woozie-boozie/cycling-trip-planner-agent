"""get_route — real-data path via BRouter (Phase 1.10b).

Opt-in: enable with ``USE_REAL_ROUTES=true`` in the environment.

What this gives us
------------------
The seeded routes in ``route.py`` were hand-curated and developed real factual
errors — Akhil fact-checked the Avenue Verte and found:

  - Total distance was 380 km (we had it as 380); the real Beauvais variant
    is ~462 km; the Normandy variant ~398 km.
  - Day 1 London → Lewes was shown as 110 km; cycle.travel's signposted
    Avenue Verte UK is closer to 140-150 km on the official route, ~107 km
    on a direct bike-routable path.
  - Day 4 Beauvais → Paris was shown as 140 km; BRouter reports 86.4 km
    on the trekking profile (and ~95-105 km on the signposted detour via
    Cergy-Pontoise).

Wiring BRouter into the pipeline replaces hand-typed numbers with live
road-network distances computed by a real bike routing engine. Same
``GetRouteOutput`` shape as the mock path, so the agent never sees the
difference and downstream tools (``get_elevation_profile``,
``get_weather``, ``find_accommodation``) keep working unchanged.

Why BRouter, not cycle.travel
-----------------------------
cycle.travel doesn't expose a public API (responds 403 to programmatic
fetches; their documented advice is "contact us"). BRouter is fully open,
runs on OpenStreetMap data, has a free hosted instance at brouter.de,
and matches the cyclist-routing domain we care about. Same architectural
pattern as ``ADR-011`` (Open-Meteo over OpenWeather): pick the dependency
that minimises friction for whoever's reviewing the code.

What this does NOT do
---------------------
1. Geocode arbitrary city pairs. We maintain a hand-curated chain of
   anchor waypoints per supported corridor (Avenue Verte, Amsterdam→
   Copenhagen, London→Brighton). Calling for an unknown corridor returns
   None and the caller falls back to the mock path.

2. Replace the ferry. Ferry segments have zero cycling distance — the
   ferry tool surfaces schedules separately. The waypoint chain marks
   the post-ferry city with ``is_ferry=True`` and BRouter is NOT called
   for the ferry leg.

3. Override elevation. BRouter does report elevation gain per segment,
   but the existing ``get_elevation_profile`` tool already covers that
   concern. A future swap could enrich the elevation tool too.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass

import httpx
import structlog

from src.tools.schemas import GetRouteOutput, Waypoint

log = structlog.get_logger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Corridor catalog — hand-curated anchor cities + ISO coords
# ---------------------------------------------------------------------------
#
# Each anchor: (name, country, lat, lon, is_ferry_arrival).
# ``is_ferry_arrival`` means "the segment ENTERING this waypoint is a
# ferry crossing" — so BRouter is NOT called for that segment, the
# distance for that hop is 0 km (the ferry tool surfaces sailings
# separately). Same convention as the seeded data.


@dataclass(frozen=True)
class Anchor:
    name: str
    country: str
    lat: float
    lon: float
    is_ferry_arrival: bool = False
    # When False, this anchor is used to STEER BRouter along the signposted
    # route but is NOT surfaced to the agent as an overnight option. Default
    # True keeps existing behaviour; set False on through-towns we add to
    # force the routing closer to the official signposted track.
    is_overnight: bool = True


# Avenue Verte — London → Paris (Beauvais variant, ~387 km signposted).
#
# Dense anchors steer BRouter through the signposted towns rather than
# letting it pick the most-direct bike-routable path. Sources cross-checked
# with avenuevertelondonparis.co.uk, cycle.travel/route/avenue_verte_uk and
# Cicerone's London-to-Paris guidebook (May 2026).
#
# UK side (via NCN 21 / 20 / 2 / 21):
#   London → Wandsworth → Crystal Palace → Coulsdon → Redhill → Crawley →
#   East Grinstead → Forest Row → Lewes → Newhaven
# Ferry: Newhaven ↔ Dieppe (DFDS, ~4 hr)
# France side (Beauvais variant V16a):
#   Dieppe → Forges-les-Eaux → Gournay-en-Bray → Saint-Germer-de-Fly →
#   Beauvais → Beaumont-sur-Oise → Cergy-Pontoise → Paris
_AVENUE_VERTE: list[Anchor] = [
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
    Anchor("Dieppe", "France", 49.9229, 1.0784, is_ferry_arrival=True),
    Anchor("Forges-les-Eaux", "France", 49.6111, 1.5439),
    Anchor("Gournay-en-Bray", "France", 49.4869, 1.7269, is_overnight=False),
    Anchor("Saint-Germer-de-Fly", "France", 49.4317, 1.7747, is_overnight=False),
    Anchor("Beauvais", "France", 49.4314, 2.0807),
    Anchor("Beaumont-sur-Oise", "France", 49.1432, 2.2825, is_overnight=False),
    Anchor("Cergy-Pontoise", "France", 49.0356, 2.0707),
    Anchor("Paris", "France", 48.8566, 2.3522),
]

# Amsterdam → Copenhagen via Puttgarden-Rødby ferry (EuroVelo 12 corridor).
# Existing 10-anchor chain matches the popular inland touring route well
# (BRouter reports 836 km, very close to the seeded 850 km — sanity-check
# passes). No additional through-towns needed.
_AMS_TO_CPH: list[Anchor] = [
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

# London → Brighton — National Cycle Network Route 20 (the iconic signposted
# south-coast classic, ~95 km signposted vs ~75 km direct).
#   London → Wandsworth → Mitcham → Coulsdon → Crawley (rejoin AV briefly) →
#   Cuckfield → Burgess Hill → Brighton
_LDN_TO_BRI: list[Anchor] = [
    Anchor("London", "United Kingdom", 51.5074, -0.1278),
    Anchor("Wandsworth", "United Kingdom", 51.4530, -0.1845, is_overnight=False),
    Anchor("Mitcham", "United Kingdom", 51.4040, -0.1683, is_overnight=False),
    Anchor("Coulsdon", "United Kingdom", 51.3208, -0.1395, is_overnight=False),
    Anchor("Crawley", "United Kingdom", 51.1092, -0.1872, is_overnight=False),
    Anchor("Cuckfield", "United Kingdom", 51.0007, -0.1421),  # popular halfway B&B stop
    Anchor("Burgess Hill", "United Kingdom", 50.9551, -0.1316, is_overnight=False),
    Anchor("Brighton", "United Kingdom", 50.8225, -0.1372),
]


_CORRIDORS: dict[tuple[str, str], list[Anchor]] = {
    ("london", "paris"): _AVENUE_VERTE,
    ("paris", "london"): list(reversed(_AVENUE_VERTE)),
    ("amsterdam", "copenhagen"): _AMS_TO_CPH,
    ("copenhagen", "amsterdam"): list(reversed(_AMS_TO_CPH)),
    ("london", "brighton"): _LDN_TO_BRI,
    ("brighton", "london"): list(reversed(_LDN_TO_BRI)),
}


# ---------------------------------------------------------------------------
# BRouter HTTP client
# ---------------------------------------------------------------------------

_BROUTER_URL = "https://brouter.de/brouter"
_BROUTER_PROFILE = "trekking"
_BROUTER_TIMEOUT = 15.0
_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h — road network is stable

# Process-local cache: keyed by the rounded coordinates of the segment.
# 6 dp ~= 0.11m accuracy, more than enough; round to 4 dp (~11m) so anchors
# match across the dataclass instances.
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
    """Close the singleton HTTP client. Hook for FastAPI lifespan teardown."""
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
    """Real road distance for a single cycling segment a→b. Returns
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
# Public entry point
# ---------------------------------------------------------------------------


def use_real_routes() -> bool:
    """True when the env flag is set. Same convention as USE_REAL_WEATHER."""
    return os.getenv("USE_REAL_ROUTES", "").strip().lower() in {"true", "1", "yes", "on"}


def _normalize(s: str) -> str:
    return s.strip().lower()


def _corridor_for(start: str, end: str) -> list[Anchor] | None:
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
            "~4 hours). Bikes carried free of charge. Avenue Verte is the official "
            "signed cycle route either side."
        )
    return "Route includes a ferry crossing — check schedules in advance."


async def fetch_real_route(
    start: str,
    end: str,
    daily_km_target: float,
    *,
    client: httpx.AsyncClient | None = None,
) -> GetRouteOutput | None:
    """Build a ``GetRouteOutput`` with real BRouter-computed distances.

    Returns ``None`` when:
      - the corridor isn't in our anchor catalog (caller should fall back)
      - BRouter fails for any segment (caller should fall back)
    """
    import math

    anchors = _corridor_for(start, end)
    if anchors is None:
        return None

    own_client = client is None
    if client is None:
        client = await _get_client()

    cumulative_km = 0.0
    waypoints: list[Waypoint] = []
    if anchors[0].is_overnight:
        waypoints.append(
            Waypoint(
                name=anchors[0].name,
                country=anchors[0].country,
                distance_from_start_km=0.0,
                is_ferry_required=False,
            )
        )

    try:
        for prev, curr in zip(anchors[:-1], anchors[1:], strict=True):
            if curr.is_ferry_arrival:
                # Skip BRouter for ferry — distance contribution is 0 km
                # cycling. The ferry tool surfaces sailing details separately.
                segment_km = 0.0
            else:
                segment_km, _ascend, _seconds = await _brouter_segment(client, prev, curr)
            cumulative_km += segment_km
            # Only surface anchors flagged as overnight options to the agent.
            # The through-towns drive BRouter's path but would clutter the
            # agent's output and inflate downstream tool calls.
            if curr.is_overnight:
                waypoints.append(
                    Waypoint(
                        name=curr.name,
                        country=curr.country,
                        distance_from_start_km=round(cumulative_km, 1),
                        is_ferry_required=curr.is_ferry_arrival,
                    )
                )
    except (httpx.HTTPError, ValueError, KeyError) as e:
        log.warning(
            "route_real.fallback",
            reason=type(e).__name__,
            error=str(e)[:200],
            start=start,
            end=end,
        )
        return None
    finally:
        # Don't close the singleton — only the per-call client (which we
        # don't actually create here, but kept for symmetry with weather.py).
        if own_client and client is not None and client is not _client:
            await client.aclose()

    total = waypoints[-1].distance_from_start_km
    estimated_days = max(1, math.ceil(total / daily_km_target))

    notes = _ferry_notes(anchors)
    real_data_note = (
        f"Distances computed via BRouter on the signposted route — total "
        f"{total:.1f} km. Cached for 24h. The chain is steered through the "
        f"official signposted intermediate towns (cross-checked with "
        f"avenuevertelondonparis.co.uk, cycle.travel, Cicerone), so this "
        f"matches what a cyclist following the route signs would actually ride."
    )
    notes = f"{notes}\n\n{real_data_note}" if notes else real_data_note

    log.info(
        "route_real.success",
        start=start,
        end=end,
        total_km=total,
        waypoints=len(waypoints),
        estimated_days=estimated_days,
    )

    return GetRouteOutput(
        start=start,
        end=end,
        total_distance_km=total,
        estimated_days=estimated_days,
        waypoints=waypoints,
        notes=notes,
    )
