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

import httpx
import structlog

# Anchor + CorridorVariant moved to corridor_registry on 2026-05-12 as
# part of the YAML-catalog refactor. Re-exported here for backwards
# compatibility — every caller that did `from src.tools.route_real import
# Anchor, CorridorVariant` keeps working unchanged.
from src.tools.corridor_registry import (
    Anchor,
    CorridorVariant,
    get_corridor_variants,
)
from src.tools.schemas import DayPlan, GetRouteOutput, RouteVariant, Waypoint

log = structlog.get_logger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


__all__ = [
    "Anchor",
    "CorridorVariant",
    "fetch_real_route",
    "use_real_routes",
    "_brouter_segment",
    "aclose_client",
]


# ---------------------------------------------------------------------------
# Per-corridor anchor catalog — sourced from data/corridors/*.yaml via
# corridor_registry. The Anchor + CorridorVariant + bidirectional catalog
# dict that used to live inline here moved out on 2026-05-12. Adding the
# 21st corridor is now one YAML file in data/corridors/, not a Python edit.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# BRouter HTTP client — unchanged from previous iteration
# ---------------------------------------------------------------------------

_BROUTER_URL = "https://brouter.de/brouter"
_BROUTER_PROFILE = "trekking"
_BROUTER_TIMEOUT = 15.0
_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h

# Per-segment cache. Stores everything BRouter returns for an a→b call so
# the variant-build path and the GPX-export path share one round-trip.
# Coordinates are kept as raw [lon, lat, ele?] floats (lists from JSON).
_SegmentCache = tuple[float, float, float, list[list[float]]]
_segment_cache: dict[tuple[float, float, float, float], _SegmentCache] = {}
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


def _cached_segment(a: Anchor, b: Anchor) -> _SegmentCache | None:
    key = _cache_key(a, b)
    ts = _cache_timestamps.get(key)
    if ts is None or (time.time() - ts) > _CACHE_TTL_SECONDS:
        return None
    return _segment_cache.get(key)


def _cache_segment(
    a: Anchor,
    b: Anchor,
    distance_km: float,
    ascend_m: float,
    time_s: float,
    coordinates: list[list[float]],
) -> None:
    key = _cache_key(a, b)
    _segment_cache[key] = (distance_km, ascend_m, time_s, coordinates)
    _cache_timestamps[key] = time.time()


async def _brouter_fetch(
    client: httpx.AsyncClient, a: Anchor, b: Anchor
) -> _SegmentCache:
    """Fetch one BRouter segment a→b. Returns
    (distance_km, ascend_m, time_seconds, coordinates) where coordinates is
    the raw GeoJSON LineString — each entry is [lon, lat] or [lon, lat, ele].
    Cached for ``_CACHE_TTL_SECONDS`` so the variant-build path and the
    GPX-export path share a single round-trip."""
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
    geometry = features[0].get("geometry", {})
    raw_coords = geometry.get("coordinates", []) or []
    # Normalise to plain float lists — robust to numpy/tuple variants if any
    # transport upstream changes how the JSON gets parsed.
    coordinates: list[list[float]] = [[float(x) for x in pt] for pt in raw_coords]
    _cache_segment(a, b, distance_km, ascend_m, time_s, coordinates)
    return distance_km, ascend_m, time_s, coordinates


async def _brouter_segment(
    client: httpx.AsyncClient, a: Anchor, b: Anchor
) -> tuple[float, float, float]:
    """Back-compat shim: (distance_km, ascend_m, time_seconds) only.

    Variant building doesn't need geometry — keeping the 3-tuple return
    avoids touching the variant-build call sites. GPX export uses
    ``_brouter_fetch`` directly to also grab the polyline.
    """
    distance_km, ascend_m, time_s, _coords = await _brouter_fetch(client, a, b)
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
    """Look up the variant list for a corridor direction.

    Delegates to ``corridor_registry.get_corridor_variants``, which reads
    from ``data/corridors/*.yaml``. Returns ``None`` for out-of-catalog
    pairs — caller falls through to generic mode. The reverse direction
    (e.g. paris→london) is built at registry load time by reversing each
    variant's anchor list, so this function doesn't need to know about
    directionality.
    """
    return get_corridor_variants(start, end)


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
        headline_tag=cv.headline_tag,
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
