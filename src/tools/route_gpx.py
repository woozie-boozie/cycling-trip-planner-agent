"""GPX export for planned routes.

Cyclists ride following a track on a head-unit (Garmin Edge, Wahoo Bolt,
Karoo, Apple Watch via Workoutdoors). The route artifact those devices
read is GPX 1.1: ``<trk>`` for the polyline, ``<wpt>`` for named
overnight stops + ferry terminals, ``<metadata>`` for the trip name.

We use BRouter's geometry (the same polyline used to compute the route
in :mod:`src.tools.route_real`). The variant-build path keeps geometry
in the segment cache so an export call is sub-second on a re-fetch.

Two modes:

* ``mode="full"`` — one ``<trk>`` containing every waypoint of every day.
  Suits Garmin Edge devices that can split a long route on-device.
* ``mode="day"`` — one ``<trk>`` scoped to a single day boundary. Suits
  the canonical touring workflow where riders upload tomorrow's day to
  the watch the night before.

The polyline split per day uses the variant's ``suggested_day_plan``
overnight boundaries — the same map the agent surfaces in the UI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

import httpx

from src.tools.route_real import (
    Anchor,
    CorridorVariant,
    _brouter_fetch,
    _get_client,
    _normalize,
    _suggest_day_plan,
    _variants_for,
)
from src.tools.schemas import DayPlan, Waypoint

GPX_MIME = "application/gpx+xml"


@dataclass(frozen=True)
class GpxBuild:
    """One assembled GPX file plus enough metadata to name and label it."""

    filename: str
    xml: str
    distance_km: float
    waypoint_count: int


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


async def _collect_polylines(
    client: httpx.AsyncClient,
    cv: CorridorVariant,
) -> tuple[list[Waypoint], list[list[list[float]]]]:
    """Walk the variant's anchor chain, returning:

    * ``waypoints`` — every overnight stop (mirror of ``_build_variant``)
    * ``polylines`` — one polyline per overnight stretch, so
      ``len(polylines) == len(waypoints) - 1``. Each polyline is a flat
      list of ``[lon, lat]`` or ``[lon, lat, ele]`` points.

    Through-town hops between two overnight anchors are stitched into the
    same polyline entry — riders care about overnight-to-overnight legs,
    not BRouter's internal segment book-keeping.
    """
    waypoints: list[Waypoint] = []
    polylines: list[list[list[float]]] = []

    cumulative_km = 0.0
    pending_segment_km = 0.0
    pending_polyline: list[list[float]] = []

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
            # Ferry crossings have no road geometry — record a synthetic
            # straight line between the two terminals so GPS-following
            # devices see a continuous track instead of a jump.
            hop_km = 0.0
            coords: list[list[float]] = [
                [prev.lon, prev.lat],
                [curr.lon, curr.lat],
            ]
        else:
            distance_km, _ascend, _seconds, coords = await _brouter_fetch(
                client, prev, curr
            )
            hop_km = distance_km

        cumulative_km += hop_km
        pending_segment_km += hop_km
        # Avoid duplicating the join point — first point of this hop is
        # the last point of the prior one when both come from BRouter.
        if pending_polyline and coords and pending_polyline[-1] == coords[0]:
            pending_polyline.extend(coords[1:])
        else:
            pending_polyline.extend(coords)

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
            polylines.append(pending_polyline)
            pending_polyline = []
            pending_segment_km = 0.0

    return waypoints, polylines


def _resolve_variant(
    start: str, end: str, variant_name: str | None
) -> CorridorVariant | None:
    """Look up the curated variant for a corridor. ``variant_name`` is
    matched case-insensitively; ``None`` returns the default."""
    variants = _variants_for(start, end)
    if not variants:
        return None
    if variant_name is None:
        return next((v for v in variants if v.is_default), variants[0])
    target = _normalize(variant_name)
    for v in variants:
        if _normalize(v.name) == target:
            return v
    return None


def _filename(corridor_label: str, variant_name: str, suffix: str | None) -> str:
    base = f"{corridor_label}-{variant_name}".lower()
    # Collapse whitespace and slugify common separators.
    cleaned: list[str] = []
    for ch in base:
        if ch.isalnum():
            cleaned.append(ch)
        elif ch in {" ", "_", "/", "→"}:
            cleaned.append("-")
        elif ch == "-":
            cleaned.append("-")
    slug = "".join(cleaned)
    # Squash repeated dashes.
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    if suffix:
        slug = f"{slug}-{suffix}"
    return f"{slug}.gpx"


# ---------------------------------------------------------------------------
# GPX XML assembly
# ---------------------------------------------------------------------------


_GPX_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.1" creator="Cycling Trip Planner" '
    'xmlns="http://www.topografix.com/GPX/1/1" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="http://www.topografix.com/GPX/1/1 '
    'http://www.topografix.com/GPX/1/1/gpx.xsd">'
)


def _format_pt(point: list[float]) -> str:
    if len(point) >= 3:
        lon, lat, ele = point[0], point[1], point[2]
        return (
            f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}">'
            f"<ele>{ele:.1f}</ele></trkpt>"
        )
    lon, lat = point[0], point[1]
    return f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}"/>'


def _format_wpt(name: str, lat: float, lon: float, comment: str | None = None) -> str:
    extras = ""
    if comment:
        extras = f"<cmt>{xml_escape(comment)}</cmt>"
    return (
        f'<wpt lat="{lat:.6f}" lon="{lon:.6f}">'
        f"<name>{xml_escape(name)}</name>{extras}</wpt>"
    )


def _assemble_gpx(
    track_name: str,
    polylines: list[list[list[float]]],
    waypoint_pins: list[tuple[str, float, float, str | None]],
) -> str:
    """Emit a GPX 1.1 document with one ``<trk>`` per group of
    polylines and one ``<wpt>`` per pin. Multiple polylines render as
    multiple ``<trkseg>`` inside a single ``<trk>``."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts: list[str] = [_GPX_HEADER]
    parts.append(
        f"<metadata><name>{xml_escape(track_name)}</name>"
        f"<time>{timestamp}</time></metadata>"
    )
    for name, lat, lon, comment in waypoint_pins:
        parts.append(_format_wpt(name, lat, lon, comment))
    parts.append(f"<trk><name>{xml_escape(track_name)}</name>")
    for polyline in polylines:
        if not polyline:
            continue
        parts.append("<trkseg>")
        parts.extend(_format_pt(pt) for pt in polyline)
        parts.append("</trkseg>")
    parts.append("</trk></gpx>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def build_gpx_for_variant(
    *,
    start: str,
    end: str,
    variant_name: str | None,
    daily_km: float = 80.0,
    mode: str = "full",
    day: int | None = None,
    from_city: str | None = None,
    to_city: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> GpxBuild | None:
    """Build a GPX file.

    Modes:

    * ``mode="full"`` — whole-trip GPX, one ``<trk>``.
    * ``mode="day"`` — single-day GPX. Two ways to scope the day:
      - **Preferred**: pass ``from_city`` and ``to_city`` directly so the
        GPX day boundaries match what the rider sees in the UI exactly.
      - **Fallback**: pass ``daily_km`` and ``day`` (1-indexed) and the
        builder will compute the same day plan ``_build_variant`` does.
        Use only when the frontend can't surface from/to.

    Returns ``None`` when:

    * the corridor isn't in the curated catalogue, or
    * the variant name doesn't match any known variant for the corridor, or
    * the day scope can't be resolved (``from_city``/``to_city`` not in
      the waypoint chain, or ``day`` out of range).

    Raises whatever ``_brouter_fetch`` raises (e.g. ``httpx.HTTPError``).
    """
    cv = _resolve_variant(start, end, variant_name)
    if cv is None:
        return None

    actual_client = client if client is not None else await _get_client()
    waypoints, polylines = await _collect_polylines(actual_client, cv)

    if not waypoints or not polylines:
        return None

    corridor_label = f"{cv.anchors[0].name}-{cv.anchors[-1].name}"
    track_name_full = f"{cv.title} · {cv.anchors[0].name} → {cv.anchors[-1].name}"

    overnight_anchors_by_name = {
        a.name: a for a in cv.anchors if a.is_overnight or a.is_ferry_arrival
    }

    if mode == "full":
        pins: list[tuple[str, float, float, str | None]] = []
        for w in waypoints:
            anchor = overnight_anchors_by_name.get(w.name)
            if anchor is None:
                continue
            comment = (
                f"Day boundary · {w.distance_from_start_km:.0f} km from start"
            )
            if w.is_ferry_required:
                comment = "Ferry arrival · " + comment
            pins.append((w.name, anchor.lat, anchor.lon, comment))
        xml = _assemble_gpx(track_name_full, polylines, pins)
        total_km = waypoints[-1].distance_from_start_km
        return GpxBuild(
            filename=_filename(corridor_label, cv.name, "full"),
            xml=xml,
            distance_km=total_km,
            waypoint_count=len(pins),
        )

    if mode != "day":
        return None

    # Day mode — resolve the day's start/end waypoints.
    from_idx: int | None
    to_idx: int | None
    day_label_n: int | None = day
    if from_city and to_city:
        from_idx = _waypoint_index(waypoints, from_city)
        to_idx = _waypoint_index(waypoints, to_city)
    else:
        if day is None or day < 1:
            return None
        # Recompute the same day plan used at variant-build time.
        day_plan = _suggest_day_plan(waypoints, daily_km)
        if day > len(day_plan):
            return None
        plan_entry = day_plan[day - 1]
        from_city = plan_entry.from_city
        to_city = plan_entry.to_city
        from_idx = _waypoint_index(waypoints, from_city)
        to_idx = _waypoint_index(waypoints, to_city)

    if from_idx is None or to_idx is None or to_idx <= from_idx:
        return None

    day_polylines = polylines[from_idx:to_idx]
    day_pins: list[tuple[str, float, float, str | None]] = []
    for w in waypoints[from_idx : to_idx + 1]:
        anchor = overnight_anchors_by_name.get(w.name)
        if anchor is None:
            continue
        comment = None
        if from_city and _normalize(w.name) == _normalize(from_city):
            comment = "Day start"
        elif to_city and _normalize(w.name) == _normalize(to_city):
            comment = "Day end"
        day_pins.append((w.name, anchor.lat, anchor.lon, comment))
    day_suffix = f"day-{day_label_n}" if day_label_n else "day"
    label_prefix = f"Day {day_label_n}: " if day_label_n else ""
    day_label = f"{cv.title} · {label_prefix}{from_city} → {to_city}"
    day_km = _polyline_total_km(day_polylines)
    xml = _assemble_gpx(day_label, day_polylines, day_pins)
    return GpxBuild(
        filename=_filename(corridor_label, cv.name, day_suffix),
        xml=xml,
        distance_km=day_km,
        waypoint_count=len(day_pins),
    )


def _polyline_total_km(polylines: list[list[list[float]]]) -> float:
    """Sum of haversine distances across a list of polylines."""
    return round(sum(total_polyline_distance_km(p) for p in polylines), 1)


def _waypoint_index(waypoints: list[Waypoint], city: str) -> int | None:
    target = _normalize(city)
    for i, w in enumerate(waypoints):
        if _normalize(w.name) == target:
            return i
    return None


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def total_polyline_distance_km(polyline: list[list[float]]) -> float:
    """Great-circle sum for sanity-checking emitted polylines."""
    if len(polyline) < 2:
        return 0.0
    earth = 6371.0
    acc = 0.0
    for a, b in zip(polyline[:-1], polyline[1:], strict=True):
        lon1, lat1 = math.radians(a[0]), math.radians(a[1])
        lon2, lat2 = math.radians(b[0]), math.radians(b[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        acc += 2 * earth * math.asin(math.sqrt(h))
    return acc
