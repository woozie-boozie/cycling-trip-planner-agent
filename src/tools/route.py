"""get_route — cycling route between two points.

Catalogued corridors live in the `routes` + `waypoints` tables in Postgres
(seeded from `_KNOWN_ROUTES` below via `src/db/seed.py`).

Three real corridors are seeded:

  - Amsterdam → Copenhagen (EuroVelo 7 / 12 via Rødby–Puttgarden ferry, ~850km)
  - London → Paris (Avenue Verte via Newhaven–Dieppe ferry, ~380km)
  - London → Brighton (short south-coast classic, ~95km)

A real route engine would call something like Komoot, BRouter, or OSRM with
a cycling profile. The contract here is the same shape — the abstraction
holds when we wire a real provider in Phase 1.10.

The `_KNOWN_ROUTES` dict below remains as the canonical source for `seed.py`
to populate Postgres. After seeding, the tool reads from the DB.
"""

from __future__ import annotations

import math

import httpx
import structlog
from sqlmodel import select

from src.db import get_async_session
from src.db.models import Route as RouteRow
from src.db.models import Waypoint as WaypointRow
from src.tools.base import register_tool
from src.tools.route_real import _suggest_day_plan, fetch_real_route, use_real_routes
from src.tools.schemas import GetRouteInput, GetRouteOutput, RouteVariant, Waypoint

log = structlog.get_logger(__name__)

# Open-Meteo geocoding API. Free, no auth, worldwide coverage. Used only
# in the generic-mode fallback below when the requested corridor isn't in
# the curated catalog.
_OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Cyclists' road-distance multiplier vs great-circle. Empirical: touring
# routes on real cycling infrastructure are typically ~25% longer than
# the straight-line distance due to road windings, bridge approaches,
# climbs being switchbacked, etc. Calibrated against the catalog
# corridors (e.g. LDN→PAR great-circle is ~340 km, BRouter-verified
# Avenue Verte is ~380 km → 1.12×; AMS→CPH great-circle 630 km vs 850 km
# inland → 1.35×). 1.25 is the median.
_ROAD_DISTANCE_MULTIPLIER = 1.25


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points, in km."""
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


async def _geocode_location(name: str) -> tuple[float, float] | None:
    """Resolve a place name to (lat, lon) via Open-Meteo's free geocoding API.

    Returns None on network error, no matches, or any other failure — the
    caller falls back to the "truly unknown" stub. We intentionally don't
    raise so a single bad input doesn't break the agent loop.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _OPEN_METEO_GEOCODE_URL,
                params={"name": name, "count": 1, "language": "en", "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("geocode.http_error", error=str(e), name=name)
        return None

    results = data.get("results") or []
    if not results:
        log.info("geocode.no_match", name=name)
        return None

    top = results[0]
    lat = top.get("latitude")
    lon = top.get("longitude")
    if lat is None or lon is None:
        return None
    return (float(lat), float(lon))

# (name, country, cumulative_km_from_start, ferry_required)
_WAYPOINTS_AMS_TO_CPH: list[tuple[str, str, float, bool]] = [
    ("Amsterdam", "Netherlands", 0.0, False),
    ("Hoorn", "Netherlands", 45.0, False),
    ("Groningen", "Netherlands", 230.0, False),
    ("Bremen", "Germany", 410.0, False),
    ("Hamburg", "Germany", 530.0, False),
    ("Lübeck", "Germany", 605.0, False),
    ("Puttgarden", "Germany", 690.0, False),
    ("Rødby", "Denmark", 710.0, True),  # ferry from Puttgarden across Fehmarn Belt
    ("Vordingborg", "Denmark", 770.0, False),
    ("Copenhagen", "Denmark", 850.0, False),
]

# Avenue Verte — the official signed cycle route from London to Paris.
# Newhaven → Dieppe ferry crosses the English Channel (~4 hr crossing).
_WAYPOINTS_LDN_TO_PAR: list[tuple[str, str, float, bool]] = [
    ("London", "United Kingdom", 0.0, False),
    ("East Grinstead", "United Kingdom", 60.0, False),
    ("Lewes", "United Kingdom", 110.0, False),
    ("Newhaven", "United Kingdom", 122.0, False),
    ("Dieppe", "France", 122.0, True),  # ferry crossing — 0 cycling km added
    ("Forges-les-Eaux", "France", 180.0, False),
    ("Beauvais", "France", 240.0, False),
    ("Cergy-Pontoise", "France", 320.0, False),
    ("Paris", "France", 380.0, False),
]

# London → Brighton — the canonical southern UK day-ride.
_WAYPOINTS_LDN_TO_BRI: list[tuple[str, str, float, bool]] = [
    ("London", "United Kingdom", 0.0, False),
    ("Crystal Palace", "United Kingdom", 12.0, False),
    ("Brighton", "United Kingdom", 95.0, False),
]


_KNOWN_ROUTES: dict[tuple[str, str], list[tuple[str, str, float, bool]]] = {
    ("amsterdam", "copenhagen"): _WAYPOINTS_AMS_TO_CPH,
    ("copenhagen", "amsterdam"): list(reversed(_WAYPOINTS_AMS_TO_CPH)),
    ("london", "paris"): _WAYPOINTS_LDN_TO_PAR,
    ("paris", "london"): list(reversed(_WAYPOINTS_LDN_TO_PAR)),
    ("london", "brighton"): _WAYPOINTS_LDN_TO_BRI,
    ("brighton", "london"): list(reversed(_WAYPOINTS_LDN_TO_BRI)),
}


def _normalize(city: str) -> str:
    return city.strip().lower()


@register_tool(
    name="get_route",
    description=(
        "Get a cycling route between two cities. Returns total distance, an ordered "
        "list of waypoints (cities/towns along the way), the cumulative distance to "
        "each waypoint from the start, whether each leg requires a ferry, and an "
        "estimated number of days based on the cyclist's daily target. Use this FIRST "
        "to understand the overall trip shape before calling per-segment tools."
    ),
    input_model=GetRouteInput,
    output_model=GetRouteOutput,
)
async def get_route(input: GetRouteInput) -> GetRouteOutput:
    start_lower = _normalize(input.start)
    end_lower = _normalize(input.end)

    # Phase 1.10b: opt into real BRouter-computed distances via env flag.
    # Falls back to the DB mock on unknown corridor or any BRouter failure —
    # same Pydantic schema either way, so the agent never sees the difference.
    if use_real_routes():
        live = await fetch_real_route(input.start, input.end, input.daily_km_target)
        if live is not None:
            return live

    async with get_async_session() as session:
        result = await session.execute(
            select(RouteRow).where(
                RouteRow.start_lower == start_lower,
                RouteRow.end_lower == end_lower,
            )
        )
        route_row = result.scalar_one_or_none()
        if route_row is None:
            # Unknown corridor — geocode the endpoints and return GENERIC MODE
            # with a real great-circle-based distance estimate. The agent then
            # proposes 5–10 cycling-friendly overnight waypoints itself (Claude
            # knows the geography), and per-segment elevation/weather/accommodation
            # tools fan out exactly the same way they do for catalog corridors.
            #
            # Replaces the previous hardcoded 600-km stub (Phase 1.10b TODO closed
            # 2026-05-11): "Suggest the user break the trip into shorter,
            # well-known legs" was a punt. The agent has everything it needs
            # to plan ANY corridor — see src/agent/prompts.py "Generic-mode
            # corridors" section.
            start_coords = await _geocode_location(input.start)
            end_coords = await _geocode_location(input.end)

            if start_coords is None or end_coords is None:
                # Couldn't geocode at all — fall back to the truly-unknown stub
                # so the agent can ask the user to rephrase the place name.
                missing = []
                if start_coords is None:
                    missing.append(input.start)
                if end_coords is None:
                    missing.append(input.end)
                stub_waypoints = [
                    Waypoint(
                        name=input.start, country="Unknown",
                        distance_from_start_km=0.0, segment_km=0.0,
                    ),
                    Waypoint(
                        name=input.end, country="Unknown",
                        distance_from_start_km=0.0, segment_km=0.0,
                    ),
                ]
                stub_variant = RouteVariant(
                    name="ungeocoded",
                    title="Place name not recognised",
                    description="Couldn't resolve the start or end to real coordinates.",
                    total_distance_km=0.0,
                    estimated_days=1,
                    waypoints=stub_waypoints,
                    distinguishing_features=[],
                    trade_offs=[],
                    best_for="ask the user to rephrase or use a more specific place name",
                    notes=(
                        f"Geocoding failed for: {', '.join(missing)}. Ask the user "
                        "for a more specific or commonly-known name (e.g. 'Edinburgh' "
                        "rather than 'Auld Reekie')."
                    ),
                    is_default=True,
                )
                return GetRouteOutput(
                    start=input.start,
                    end=input.end,
                    variants=[stub_variant],
                    total_distance_km=0.0,
                    estimated_days=1,
                    waypoints=stub_waypoints,
                    notes=stub_variant.notes,
                )

            # GENERIC MODE — real geocoded endpoints + great-circle estimate.
            # The agent reads the GENERIC MODE prefix on `notes` and switches
            # into "propose waypoints yourself + fan out per-segment tools" flow.
            great_circle_km = _haversine_km(start_coords, end_coords)
            realistic_km = round(great_circle_km * _ROAD_DISTANCE_MULTIPLIER, 1)
            estimated_days = max(1, math.ceil(realistic_km / input.daily_km_target))

            generic_waypoints = [
                Waypoint(
                    name=input.start, country="Unknown",
                    distance_from_start_km=0.0, segment_km=0.0,
                ),
                Waypoint(
                    name=input.end, country="Unknown",
                    distance_from_start_km=realistic_km, segment_km=realistic_km,
                ),
            ]
            generic_notes = (
                f"GENERIC MODE — this corridor is not in the curated catalog. "
                f"The distance estimate ({realistic_km} km) is great-circle × "
                f"{_ROAD_DISTANCE_MULTIPLIER} (typical road-distance multiplier "
                f"for touring routes). You MUST propose 5–10 cycling-friendly "
                f"overnight waypoints yourself based on your knowledge of the "
                f"geography + long-distance cycling networks (LEJOG, NCN, "
                f"EuroVelo, etc.), then call get_elevation_profile per consecutive "
                f"pair to get real BRouter distance + climb. Sum the segments for "
                f"the true total (discard this estimate). Then call get_weather "
                f"and find_accommodation per overnight stop, same as catalog "
                f"corridors. Flag in your response that overnight stops are "
                f"LLM-proposed (not signposted) and the user should verify each "
                f"leg via Komoot/RWGPS before riding. Still call critique_trip_plan."
            )
            generic_variant = RouteVariant(
                name="generic",
                title=f"{input.start} → {input.end} — generic (not catalog-curated)",
                description=(
                    f"Geocoded endpoints + great-circle distance × "
                    f"{_ROAD_DISTANCE_MULTIPLIER}. Propose intermediate "
                    f"waypoints and verify per-segment via BRouter."
                ),
                total_distance_km=realistic_km,
                estimated_days=estimated_days,
                waypoints=generic_waypoints,
                distinguishing_features=[
                    "Endpoints geocoded via Open-Meteo (real coordinates)",
                    "Distance estimate calibrated against catalog corridors",
                ],
                trade_offs=[
                    "No signposted cycle route — overnight stops are LLM-proposed",
                    "Per-segment elevation + accommodation must be fetched and verified",
                ],
                best_for=(
                    "any corridor outside the curated catalog — agent stitches a "
                    "plan from BRouter-verified segments"
                ),
                notes=generic_notes,
                is_default=True,
            )
            return GetRouteOutput(
                start=input.start,
                end=input.end,
                variants=[generic_variant],
                total_distance_km=realistic_km,
                estimated_days=estimated_days,
                waypoints=generic_waypoints,
                notes=generic_notes,
            )

        waypoint_result = await session.execute(
            select(WaypointRow)
            .where(WaypointRow.route_id == route_row.id)
            .order_by(WaypointRow.sequence)
        )
        waypoint_rows = waypoint_result.scalars().all()

    # segment_km is the cycling distance from the previous waypoint. Compute
    # via consecutive subtraction here so the Pydantic boundary always
    # carries the field — same contract as the BRouter path.
    waypoints: list[Waypoint] = []
    for i, w in enumerate(waypoint_rows):
        seg = (
            0.0
            if i == 0
            else round(w.distance_from_start_km - waypoint_rows[i - 1].distance_from_start_km, 1)
        )
        waypoints.append(
            Waypoint(
                name=w.name,
                country=w.country,
                distance_from_start_km=w.distance_from_start_km,
                segment_km=seg,
                is_ferry_required=w.is_ferry_required,
            )
        )
    total = waypoints[-1].distance_from_start_km if waypoints else route_row.total_distance_km
    estimated_days = max(1, math.ceil(total / input.daily_km_target))

    has_ferry = any(w.is_ferry_required for w in waypoints)
    ferry_waypoint = next((w for w in waypoints if w.is_ferry_required), None)
    if not has_ferry:
        notes = None
    elif ferry_waypoint and _normalize(ferry_waypoint.name) in {"rødby", "puttgarden"}:
        notes = (
            "Includes the Rødby–Puttgarden ferry across the Fehmarn Belt — a fixed link "
            "tunnel is under construction but the ferry remains the standard option as of "
            "this dataset. Allow ~45 minutes for the crossing."
        )
    elif ferry_waypoint and _normalize(ferry_waypoint.name) in {"dieppe", "newhaven"}:
        notes = (
            "Includes the Newhaven–Dieppe ferry across the English Channel (DFDS, "
            "~4 hours). Cyclists travel as foot passengers — bikes carry no surcharge "
            "above the foot-passenger fare (from £33 each way, ~£40–55 in summer). "
            "Avenue Verte is the official signed cycle route either side."
        )
    else:
        notes = "Route includes a ferry crossing — check schedules in advance."

    # Wrap the DB-loaded route as a single variant for schema consistency
    # with the multi-variant real-data path. Frontend + downstream tools
    # consume `waypoints` directly so they don't need to know about variants.
    db_variant = RouteVariant(
        name="seed_default",
        title=f"{input.start} → {input.end} (seeded route)",
        description=(
            "Route loaded from the seed dataset. Set USE_REAL_ROUTES=true to "
            "compute real road distances via BRouter and access multiple "
            "signposted variants where available."
        ),
        total_distance_km=total,
        estimated_days=estimated_days,
        waypoints=waypoints,
        suggested_day_plan=_suggest_day_plan(waypoints, input.daily_km_target),
        distinguishing_features=[],
        trade_offs=[],
        best_for="quick demo / offline mode",
        notes=notes,
        is_default=True,
    )

    return GetRouteOutput(
        start=input.start,
        end=input.end,
        variants=[db_variant],
        total_distance_km=total,
        estimated_days=estimated_days,
        waypoints=waypoints,
        notes=notes,
    )
