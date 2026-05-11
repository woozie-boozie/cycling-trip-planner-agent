"""get_elevation_profile — terrain difficulty for a single segment.

Catalog segments live in the `elevation_segments` table in Postgres (seeded
from `_SEGMENTS` below via `src/db/seed.py`). Both directions are seeded with
gain/loss mirrored, so reverse lookups don't need runtime computation.

Out-of-catalog segments (generic-mode corridors like London → Edinburgh):
geocode both endpoints via Open-Meteo, call BRouter for real cycling
distance + ascent, derive max grade + difficulty. Mirrors the get_route
generic-mode pattern — the catalog is the fast path for curated corridors,
BRouter is the general-purpose fallback for everywhere else.

Real elevation data lives in DEMs (digital elevation models like SRTM); the
abstraction here is the same shape a real provider would use.
"""

from __future__ import annotations

import httpx
import structlog
from sqlmodel import select

from src.db import get_async_session
from src.db.models import ElevationSegment as ElevRow
from src.tools.base import register_tool
from src.tools.schemas import (
    Difficulty,
    GetElevationProfileInput,
    GetElevationProfileOutput,
)

log = structlog.get_logger(__name__)

# Per-segment terrain. Ordered as they appear on the Ams→Cph corridor;
# reverse direction (Cph→Ams) is symmetrical.
# (start, end, distance_km, gain_m, loss_m, max_grade_pct, difficulty, note)
_SegmentRow = tuple[str, str, float, int, int, float, Difficulty, str | None]

_SEGMENTS: list[_SegmentRow] = [
    # Amsterdam → Copenhagen corridor
    ("amsterdam", "hoorn", 45.0, 30, 25, 1.0, "easy", "Flat polders. Possible headwinds."),
    ("hoorn", "groningen", 185.0, 80, 70, 1.5, "easy", "Mostly flat, dyke-side cycling."),
    ("groningen", "bremen", 180.0, 120, 100, 2.0, "easy", "Crosses German lowlands — flat with gentle rolls."),
    ("bremen", "hamburg", 120.0, 90, 80, 2.0, "easy", "Following the Elbe valley — flat."),
    ("hamburg", "lübeck", 75.0, 110, 90, 3.0, "moderate", "Some gentle rolling moraine outside Hamburg."),
    ("lübeck", "puttgarden", 85.0, 100, 95, 2.5, "easy", "Coastal flatland through Schleswig-Holstein."),
    ("puttgarden", "rødby", 20.0, 5, 5, 0.5, "easy", "Ferry crossing — minimal cycling distance."),
    ("rødby", "vordingborg", 60.0, 60, 55, 2.0, "easy", "Flat Lolland and Falster islands. Wind exposure."),
    ("vordingborg", "copenhagen", 80.0, 90, 80, 2.5, "easy", "Crosses Storstrøm bridge then gentle Zealand terrain."),
    # Avenue Verte (London → Paris)
    ("london", "east grinstead", 60.0, 280, 180, 4.0, "moderate", "South London hills, then Greenwich Park climb. Forest of Ashdown approach."),
    ("east grinstead", "lewes", 50.0, 320, 380, 5.0, "moderate", "Crosses the South Downs ridge — proper climbs and a steep descent into Lewes."),
    ("lewes", "newhaven", 12.0, 40, 80, 2.0, "easy", "Short, flat ride along the Ouse valley to the ferry port."),
    ("newhaven", "dieppe", 0.0, 0, 0, 0.0, "easy", "Channel ferry crossing — no cycling. ~4 hour journey."),
    ("dieppe", "forges-les-eaux", 58.0, 250, 150, 4.0, "moderate", "Climb out of Dieppe, then rolling Pays de Bray farmland."),
    ("forges-les-eaux", "beauvais", 60.0, 180, 200, 3.0, "easy", "Gentle agricultural rolls through Picardy."),
    ("beauvais", "cergy-pontoise", 80.0, 150, 130, 3.0, "easy", "Approach to the Paris basin — mostly flat."),
    ("cergy-pontoise", "paris", 60.0, 100, 120, 2.0, "easy", "Riverside paths along the Seine into central Paris. Watch for traffic in the last 10km."),
    # London → Brighton (south coast classic)
    ("london", "crystal palace", 12.0, 80, 30, 5.0, "easy", "Urban climb out of central London to Crystal Palace ridge."),
    ("crystal palace", "brighton", 83.0, 400, 420, 6.0, "hard", "South Downs the whole way — Ditchling Beacon's the steepest climb in the south of England (16% near top)."),
]

_LOOKUP: dict[tuple[str, str], _SegmentRow] = {(s, e): row for row in _SEGMENTS for s, e in [(row[0], row[1])]}
# Add reverse direction with mirrored gain/loss
for row in _SEGMENTS:
    s, e, dist, gain, loss, grade, diff, note = row
    _LOOKUP[(e, s)] = (e, s, dist, loss, gain, grade, diff, note)


def _normalize(s: str) -> str:
    return s.strip().lower()


def _difficulty_from(distance_km: float, gain_m: float, max_grade_pct: float) -> Difficulty:
    """Map BRouter outputs to the same easy/moderate/hard/extreme buckets the
    catalog rows use. Combines km + climb the way critique.py scores days,
    plus a max-grade gate so a short-but-steep climb (e.g. Ditchling Beacon
    on a 25 km day) still reads as hard."""
    if max_grade_pct >= 8.0:
        return "extreme"
    score = distance_km + (gain_m * 0.05)
    if score < 50:
        return "easy"
    if score < 90 and max_grade_pct < 4.5:
        return "easy"
    if score < 115 and max_grade_pct < 6.0:
        return "moderate"
    if score < 140 and max_grade_pct < 7.0:
        return "hard"
    return "extreme"


def _difficulty_from_distance(distance_km: float) -> Difficulty:
    """Distance-only difficulty for the haversine fallback path where we
    don't have real elevation data. Conservative — long flat days still
    flag as 'hard' so the agent doesn't underestimate fatigue."""
    if distance_km < 50:
        return "easy"
    if distance_km < 90:
        return "easy"
    if distance_km < 115:
        return "moderate"
    if distance_km < 145:
        return "hard"
    return "extreme"


async def _fetch_real_elevation(
    start: str, end: str
) -> GetElevationProfileOutput | None:
    """Out-of-catalog fallback: geocode + BRouter for any (start, end) pair.

    Returns None on any failure (geocode miss, BRouter unavailable, etc.) so
    the caller can drop to the moderate-default stub. We import the helpers
    from route.py + route_real.py rather than duplicating; they're build-time
    shared utilities now that two tools rely on the same geocode + BRouter
    pattern.
    """
    # Local imports — these modules pull database + httpx clients at import
    # time, so deferring keeps `from src.tools.elevation import …` light.
    from src.tools.route import _geocode_pair, _haversine_km
    from src.tools.route_real import Anchor, _brouter_segment

    # Joint geocoding — resolves both endpoints simultaneously, picking the
    # candidate pair with the smallest haversine distance. Handles the
    # "Cambridge → Newmarket" class of error where each endpoint has a
    # more-populous US namesake and the asymmetric "geocode start, bias end"
    # pattern silently picks the wrong continent. See route._geocode_pair
    # docstring for the failure-mode trace.
    coords = await _geocode_pair(start, end)
    if coords is None:
        log.info("elevation.geocode_miss", start=start, end=end)
        return None
    start_coords, end_coords = coords

    start_anchor = Anchor(
        name=start, country="?", lat=start_coords[0], lon=start_coords[1],
    )
    end_anchor = Anchor(
        name=end, country="?", lat=end_coords[0], lon=end_coords[1],
    )

    # 10s ceiling — healthy BRouter responses are 2–5s; 10s gives comfortable
    # headroom while keeping the haversine fallback prompt when the public
    # instance is overloaded. Matches the spirit of route_real._BROUTER_TIMEOUT
    # (15s) but tighter so multi-segment fan-outs aren't dominated by dead
    # waits. A 30s value here cost ~150s of compounded latency on a real
    # 5-timeout LDN→Edinburgh request before this was tightened.
    brouter_failed = False
    brouter_exc: Exception | None = None
    distance_km = 0.0
    ascend_m = 0.0
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            distance_km, ascend_m, _time_s = await _brouter_segment(
                client, start_anchor, end_anchor,
            )
    except (httpx.HTTPError, ValueError, KeyError) as e:
        brouter_failed = True
        brouter_exc = e

    # Sanity check — even when BRouter "succeeds" it occasionally returns
    # nonsense distances (5–13× the real value) when its internal routing
    # hits a problem. Cycling routes typically run 1.1–1.5× the great-
    # circle distance; > 2.5× is almost certainly a routing error. We also
    # cap at an absolute 300 km per segment — even ultra-endurance riders
    # rarely cover that in a single day, so a >300 km segment-distance
    # signals a geocoding or routing collapse.
    #
    # Real example from production (London → Norfolk Broads chat,
    # 2026-05-11): BRouter returned 542 km for a Newmarket → Thetford
    # segment whose real distance is ~40 km, after geocoding resolved
    # one endpoint to the wrong continent. Without this check the agent
    # had to dance around the nonsense value mid-conversation.
    if not brouter_failed:
        gc_km_sanity = _haversine_km(start_coords, end_coords)
        # Guard against degenerate same-point pairs (gc_km == 0) where
        # any ratio test would explode; if both coords are identical,
        # zero distance is fine.
        ratio_blown = gc_km_sanity > 0.5 and distance_km > gc_km_sanity * 2.5
        if ratio_blown or distance_km > 300.0:
            log.warning(
                "elevation.brouter_sanity_check_failed",
                start=start,
                end=end,
                brouter_km=round(distance_km, 1),
                haversine_km=round(gc_km_sanity, 1),
                reason="ratio" if ratio_blown else "absolute_cap",
            )
            brouter_failed = True
            brouter_exc = ValueError(
                f"brouter returned {distance_km:.1f} km vs haversine "
                f"{gc_km_sanity:.1f} km — routing engine produced a "
                f"value outside the sanity envelope"
            )

    if brouter_failed:
        # BRouter unavailable BUT we already have valid geocodes. Compute a
        # great-circle × 1.25 distance estimate (same multiplier the get_route
        # generic-mode fallback uses) instead of returning None and dropping to
        # the universal 80 km stub. This is the difference between *all 7
        # timeouts becoming uniform 80 km* and *each timeout becoming roughly
        # right per its geography* (Durham → Newcastle ~23 km, Lincoln → York
        # ~111 km, etc.).
        #
        # Added 2026-05-11 after a web-Claude fact-check pinpointed the uniform
        # 80 km values as broken: Newcastle → Durham real is ~26 km, Lincoln →
        # York real is ~130 km, the 80 km mock was sometimes 3× off in either
        # direction. Worse, the under-stated 80 km for Lincoln → York hid a
        # day that would otherwise trip the joint blocker.
        log.warning(
            "elevation.brouter_failed_haversine_fallback",
            error=str(brouter_exc), start=start, end=end,
        )
        gc_km = _haversine_km(start_coords, end_coords)
        realistic_km = round(gc_km * 1.25, 1)
        return GetElevationProfileOutput(
            start=start,
            end=end,
            distance_km=realistic_km,
            # Elevation is genuinely unknown without BRouter or DEM data — set
            # to 0 with a clear caveat in `notes` rather than fabricating a
            # number that masquerades as data.
            elevation_gain_m=0,
            elevation_loss_m=0,
            max_grade_percent=0.0,
            difficulty=_difficulty_from_distance(realistic_km),
            notes=(
                f"Distance is geocode + great-circle × 1.25 (~{realistic_km} km, "
                f"within ~15% of real cycling distance — PLAN WITH IT). "
                f"Elevation is unknown for this specific segment (BRouter "
                f"unavailable) — surface 'verify gradient via Komoot' in your "
                f"Heads up section but DO NOT refuse to plan; the distance "
                f"is sufficient to compute pacing + accommodation."
            ),
        )

    # Touring routes are typically near-symmetric in gain/loss; ~0.95× ascent
    # is a reasonable estimate without a second BRouter call. For genuinely
    # net-climbing routes (sea-level → mountain town), this under-counts loss
    # in one direction and over-counts in the other — fine for the agent's
    # "roughly how hard is this segment" purpose.
    loss_m = int(round(ascend_m * 0.95))

    # BRouter doesn't return peak gradient. Approximate as ~1.8× the average
    # gradient, which empirically matches the peaks in catalog routes
    # (Ditchling Beacon: avg ~3.5%, peak ~6%; Avenue Verte: avg ~1%, peak ~4%).
    if distance_km > 0:
        avg_grade_pct = (ascend_m / 1000.0) / distance_km * 100
    else:
        avg_grade_pct = 0.0
    max_grade_pct = round(avg_grade_pct * 1.8, 1)

    difficulty = _difficulty_from(distance_km, ascend_m, max_grade_pct)

    return GetElevationProfileOutput(
        start=start,
        end=end,
        distance_km=round(distance_km, 1),
        elevation_gain_m=int(round(ascend_m)),
        elevation_loss_m=loss_m,
        max_grade_percent=max_grade_pct,
        difficulty=difficulty,
        notes=(
            f"Real BRouter cycling segment (out-of-catalog). Distance and "
            f"ascent are BRouter-verified; descent is approximated as 0.95× "
            f"ascent and max grade as 1.8× the average gradient (BRouter "
            f"doesn't return peak grade). For exact terrain confirm via "
            f"Komoot or RWGPS before riding."
        ),
    )


@register_tool(
    name="get_elevation_profile",
    description=(
        "Get terrain difficulty for a single segment between two adjacent "
        "waypoints — total elevation gain in meters, elevation loss, max "
        "gradient, and a difficulty rating (easy/moderate/hard/extreme). "
        "Use once per daily segment after building the route, to advise on "
        "pacing and rest-day placement."
    ),
    input_model=GetElevationProfileInput,
    output_model=GetElevationProfileOutput,
)
async def get_elevation_profile(input: GetElevationProfileInput) -> GetElevationProfileOutput:
    start_lower = _normalize(input.start)
    end_lower = _normalize(input.end)

    async with get_async_session() as session:
        result = await session.execute(
            select(ElevRow).where(
                ElevRow.start_lower == start_lower,
                ElevRow.end_lower == end_lower,
            )
        )
        row = result.scalar_one_or_none()

    if row is None:
        # Out-of-catalog segment — try real BRouter data before falling back.
        # Added 2026-05-11 (closes the same Phase 1.10b TODO as get_route's
        # generic-mode fix): the prior implementation returned a uniform
        # 80 km / 150 m / "moderate" stub which made every generic-mode
        # corridor's day plan look identical regardless of actual terrain.
        # Now the catalog is the fast path; BRouter handles everywhere else.
        real = await _fetch_real_elevation(input.start, input.end)
        if real is not None:
            return real

        # BRouter unavailable AND geocoding worked elsewhere — last-ditch
        # fallback. Surfaces clearly that the values are estimates so the
        # agent doesn't quote them with false confidence.
        return GetElevationProfileOutput(
            start=input.start,
            end=input.end,
            distance_km=80.0,
            elevation_gain_m=150,
            elevation_loss_m=150,
            max_grade_percent=3.0,
            difficulty="moderate",
            notes=(
                "Estimated values — segment not in the catalog and BRouter "
                "unavailable for this pair. Treat as 'moderate rolling terrain' "
                "default and verify via Komoot/RWGPS before riding."
            ),
        )

    return GetElevationProfileOutput(
        start=input.start,
        end=input.end,
        distance_km=row.distance_km,
        elevation_gain_m=row.elevation_gain_m,
        elevation_loss_m=row.elevation_loss_m,
        max_grade_percent=row.max_grade_percent,
        difficulty=row.difficulty,  # type: ignore[arg-type]
        notes=row.notes,
    )
