"""Fetch real POI data from OpenStreetMap for each known corridor.

Why this exists
---------------
The visual map (`web/lib/pois.ts`) used to be ~20 hand-typed POIs per corridor.
On a 836 km Amsterdam → Copenhagen map that reads as "barely any POIs" — one
dot every 40 km of route. This script replaces the hand-curated set with a
real-world snapshot from OpenStreetMap.

OSM is the right source for this:
  * Free, no auth required.
  * Tag schema covers our 9 amenity-based layers cleanly (the `warning`
    layer stays hand-curated — OSM doesn't tag cyclist hazards well).
  * Cycling-native: `shop=bicycle`, `amenity=bicycle_repair_station`,
    `amenity=drinking_water`, `tourism=camp_site` are first-class tags.
  * Built by people who ride bikes.

Build-time, not runtime
-----------------------
The output is committed to `web/lib/data/pois-{corridor_id}.json` and
imported by `pois.ts`. Frontend reads it like it read the hardcoded data
before — no live API calls in prod, deterministic for the case-study
demo, reviewer can read the data alongside the code. Re-run via
`make pois` (or `python scripts/fetch_corridor_pois.py`) when you want
fresher data.

Curation rules
--------------
For each (corridor, layer):
  1. Issue one Overpass QL query for the union bounding box of all
     variant anchors + a buffer (degrees, generous enough to catch
     POIs alongside the route).
  2. Filter results: require a `name` tag (drops thousands of unnamed
     amenities), and require min-distance-to-any-variant-polyline below
     `MAX_DISTANCE_KM`.
  3. Sort by distance-to-route ascending, take the top `LAYER_CAPS[layer]`.

The distance filter is the most important: without it, the map would
fill with café spam from every city the corridor passes near.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

# Primary + fallbacks. The OSM Foundation instance is the default; the Kumi
# mirror runs faster but enforces stricter rate limits. We rotate to a
# fallback if the primary returns 406/429/5xx — common on busy days.
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]

# Overpass etiquette asks for a descriptive User-Agent so abusive scripts can
# be banned by signature rather than IP. Default httpx UA ("python-httpx/x.y")
# gets 406 from the main endpoint.
USER_AGENT = "cycling-trip-planner-agent/0.1 (build-time POI fetch; github.com/woozie-boozie/cycling-trip-planner-agent)"

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "web" / "lib" / "data"

# ---------------------------------------------------------------------------
# Corridor anchor data (sourced from data/corridors/*.yaml via the registry)
# ---------------------------------------------------------------------------
# Pre-2026-05-12: this script kept a hand-copied duplicate of the route_real
# anchors. Now sourced from the YAML registry — adding a 4th, 5th, … 23rd
# corridor only requires creating data/corridors/<slug>.yaml; this script
# picks it up on the next `make pois` run.
#
# The registry has zero FastAPI deps (just pydantic + pyyaml), so the
# original "intentional copy to avoid pulling the FastAPI tree" concern
# doesn't apply anymore.


@dataclass(frozen=True)
class Anchor:
    """Lightweight Anchor used by the OSM filter math. The corridor
    registry returns its own Anchor dataclass; we wrap into this minimal
    one to keep the polyline/bbox helpers below dialect-agnostic."""

    name: str
    lat: float
    lon: float


def _load_corridors_from_registry() -> dict[str, list[list[Anchor]]]:
    """Read every corridor from data/corridors/*.yaml and produce the
    {corridor_id: [variant_anchors]} shape this script needs.

    Filters to is_overnight=True anchors only — through-towns (Wandsworth,
    Crystal Palace, etc.) steer BRouter for cycling routing but are noise
    for POI bbox + polyline filtering."""
    # Lazy import so the script still runs when only PyYAML is installed
    # (no FastAPI / structlog needed for this build-time tool).
    from src.tools.corridor_registry import all_corridor_defs

    out: dict[str, list[list[Anchor]]] = {}
    for corridor in all_corridor_defs():
        variant_anchor_lists: list[list[Anchor]] = []
        for variant in corridor.variants:
            anchors = [
                Anchor(name=a.name, lat=a.lat, lon=a.lon)
                for a in variant.anchors
                if a.is_overnight
            ]
            if anchors:
                variant_anchor_lists.append(anchors)
        if variant_anchor_lists:
            out[corridor.id] = variant_anchor_lists
    return out


CORRIDORS: dict[str, list[list[Anchor]]] = _load_corridors_from_registry()


# ---------------------------------------------------------------------------
# Layer → OSM tag mapping
# ---------------------------------------------------------------------------
# Each entry is a list of (key, value) pairs, OR'd together in Overpass QL.
# Both nodes and ways are queried; for ways we use `out center` to get a
# single lat/lon per result instead of the full geometry.

LAYER_TAGS: dict[str, list[tuple[str, str]]] = {
    "photo": [
        ("tourism", "viewpoint"),
        ("tourism", "attraction"),
    ],
    "wildlife": [
        ("leisure", "nature_reserve"),
        ("tourism", "wildlife_hide"),
    ],
    "camp": [
        ("tourism", "camp_site"),
        ("tourism", "caravan_site"),
    ],
    # food + heritage are the heaviest tag families (10k+ results for the
    # ams-cph bbox). They tend to time out / 429 on the public Overpass
    # instances, and the curated POI set already has good food/heritage
    # narrative anchors (Beauvais Cathedral, Brunswick fish markets, etc.).
    # Keep them out of the OSM scatter to avoid blowing the build budget.
    "repair": [
        ("shop", "bicycle"),
        ("amenity", "bicycle_repair_station"),
    ],
    "water": [
        ("amenity", "drinking_water"),
    ],
    "hospital": [
        ("amenity", "hospital"),
        ("amenity", "clinic"),
    ],
    "ferry": [
        ("amenity", "ferry_terminal"),
    ],
}

# Maximum POIs per layer per corridor. Tuned so the visual map looks dense
# without crowding the basemap. Food gets the biggest cap because cafés are
# what cyclists actually need; hospital/ferry stay small because they're
# operational/rare reference points.
LAYER_CAPS: dict[str, int] = {
    "photo": 18,
    "wildlife": 12,
    "camp": 25,
    "food": 30,
    "heritage": 18,
    "repair": 20,
    "water": 22,
    "hospital": 10,
    "ferry": 6,
}

# A POI must be within this many km of at least one variant's polyline to
# count as on-route. 8 km is generous enough to catch town POIs that aren't
# exactly on the bike path, tight enough to exclude unrelated city centres.
MAX_DISTANCE_KM = 8.0

# Bounding box buffer (degrees) around the union of all anchors.
BBOX_BUFFER_DEG = 0.20

# Overpass query timeout — short so the script moves on to fallbacks
# quickly when a heavy query gets stuck behind a busy queue.
OVERPASS_TIMEOUT_S = 35

# Wait between Overpass queries — fair-use policy.
INTER_QUERY_SLEEP_S = 1.5


# ---------------------------------------------------------------------------
# Geo math
# ---------------------------------------------------------------------------


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """Great-circle distance in km."""
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _distance_to_segment_km(
    lat: float,
    lon: float,
    a_lat: float,
    a_lon: float,
    b_lat: float,
    b_lon: float,
) -> float:
    """Approximate distance from point to line segment, in km.

    Linear projection in equirectangular coords; accurate enough at the
    scale we care about (8 km buffer over <2000 km segments).
    """
    # Project to a local equirectangular plane with the midpoint as origin.
    mid_lat = (a_lat + b_lat) / 2
    cos_lat = math.cos(math.radians(mid_lat))
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * cos_lat

    px = (lon - a_lon) * km_per_deg_lon
    py = (lat - a_lat) * km_per_deg_lat
    bx = (b_lon - a_lon) * km_per_deg_lon
    by = (b_lat - a_lat) * km_per_deg_lat

    seg_len_sq = bx * bx + by * by
    if seg_len_sq < 1e-9:
        # Degenerate segment — fall back to haversine to endpoint.
        return _haversine_km(lat, lon, a_lat, a_lon)

    # Param t along [0,1] for the foot of perpendicular.
    t = max(0.0, min(1.0, (px * bx + py * by) / seg_len_sq))
    foot_x = t * bx
    foot_y = t * by
    return math.hypot(px - foot_x, py - foot_y)


def _min_distance_to_polylines_km(
    lat: float, lon: float, polylines: list[list[Anchor]]
) -> float:
    """Min distance from a point to any segment of any polyline."""
    best = float("inf")
    for line in polylines:
        for i in range(len(line) - 1):
            a, b = line[i], line[i + 1]
            d = _distance_to_segment_km(lat, lon, a.lat, a.lon, b.lat, b.lon)
            if d < best:
                best = d
                if best == 0:
                    return 0
    return best


# ---------------------------------------------------------------------------
# Overpass
# ---------------------------------------------------------------------------


def _bbox_for(corridor_polylines: list[list[Anchor]]) -> tuple[float, float, float, float]:
    """Compute (south, west, north, east) bbox covering all variant anchors."""
    lats = [a.lat for line in corridor_polylines for a in line]
    lons = [a.lon for line in corridor_polylines for a in line]
    return (
        min(lats) - BBOX_BUFFER_DEG,
        min(lons) - BBOX_BUFFER_DEG,
        max(lats) + BBOX_BUFFER_DEG,
        max(lons) + BBOX_BUFFER_DEG,
    )


def _overpass_query(
    bbox: tuple[float, float, float, float],
    tags: list[tuple[str, str]],
) -> str:
    """Build an Overpass QL query for nodes+ways matching any of the tags."""
    south, west, north, east = bbox
    bbox_clause = f"({south},{west},{north},{east})"
    parts: list[str] = []
    for key, value in tags:
        parts.append(f'node["{key}"="{value}"]["name"]{bbox_clause};')
        parts.append(f'way["{key}"="{value}"]["name"]{bbox_clause};')
    inner = "\n".join(parts)
    return f"[out:json][timeout:{OVERPASS_TIMEOUT_S}];\n({inner});\nout center;"


def _fetch_layer(
    client: httpx.Client,
    bbox: tuple[float, float, float, float],
    tags: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Try each Overpass endpoint in order; first success wins."""
    query = _overpass_query(bbox, tags)
    last_err: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            r = client.post(
                endpoint,
                data={"data": query},
                timeout=OVERPASS_TIMEOUT_S + 10,
            )
            if r.status_code in (406, 429, 502, 503, 504):
                last_err = httpx.HTTPStatusError(
                    f"{r.status_code} on {endpoint}", request=r.request, response=r
                )
                time.sleep(INTER_QUERY_SLEEP_S)
                continue
            r.raise_for_status()
            payload = r.json()
            return payload.get("elements", [])
        except httpx.HTTPError as e:
            last_err = e
            time.sleep(INTER_QUERY_SLEEP_S)
    if last_err is not None:
        raise last_err
    return []


def _element_to_poi_candidate(
    element: dict[str, Any], layer: str
) -> dict[str, Any] | None:
    """Normalise an Overpass element to a POI candidate (no distance yet)."""
    tags = element.get("tags", {})
    name = tags.get("name")
    if not name:
        return None

    # Coords: nodes have lat/lon directly; ways have a `center` block.
    if element.get("type") == "node":
        lat = element.get("lat")
        lon = element.get("lon")
    else:
        center = element.get("center") or {}
        lat = center.get("lat")
        lon = center.get("lon")
    if lat is None or lon is None:
        return None

    description = _description_for(layer, tags)

    return {
        "lat": float(lat),
        "lon": float(lon),
        "layer": layer,
        "label": name,
        "description": description,
    }


def _description_for(layer: str, tags: dict[str, Any]) -> str:
    """Build a short human-readable description from the OSM tags."""
    if "description" in tags:
        return str(tags["description"])[:160]

    if layer == "food":
        cuisine = tags.get("cuisine", "").replace("_", " ")
        kind = tags.get("amenity", "food spot")
        return f"{cuisine.capitalize()} {kind}" if cuisine else f"{kind.capitalize()}"
    if layer == "heritage":
        return (
            tags.get("historic", tags.get("tourism", "Heritage site"))
            .replace("_", " ")
            .capitalize()
        )
    if layer == "camp":
        return tags.get("tourism", "Campsite").replace("_", " ").capitalize()
    if layer == "wildlife":
        return tags.get("leisure", tags.get("tourism", "Nature site")).replace("_", " ").capitalize()
    if layer == "water":
        return "Public drinking water" if tags.get("amenity") == "drinking_water" else "Natural spring"
    if layer == "repair":
        return "Bike shop" if tags.get("shop") == "bicycle" else "Self-service repair station"
    if layer == "hospital":
        return tags.get("amenity", "Medical").capitalize()
    if layer == "ferry":
        return "Ferry terminal"
    if layer == "photo":
        return tags.get("tourism", "Viewpoint").replace("_", " ").capitalize()
    return ""


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _fetch_corridor(corridor_id: str, polylines: list[list[Anchor]]) -> list[dict[str, Any]]:
    bbox = _bbox_for(polylines)
    print(
        f"\n[{corridor_id}] bbox = "
        f"S={bbox[0]:.3f} W={bbox[1]:.3f} N={bbox[2]:.3f} E={bbox[3]:.3f}"
    )

    all_pois: list[dict[str, Any]] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for layer, tags in LAYER_TAGS.items():
            print(f"[{corridor_id}] fetching layer={layer} ({len(tags)} tag(s))...")
            try:
                elements = _fetch_layer(client, bbox, tags)
            except httpx.HTTPError as e:
                print(f"  ! HTTP error on {layer}: {e}", file=sys.stderr)
                time.sleep(INTER_QUERY_SLEEP_S)
                continue

            # Normalise + dedupe by (label, rounded lat/lon)
            seen: set[tuple[str, float, float]] = set()
            candidates: list[dict[str, Any]] = []
            for el in elements:
                poi = _element_to_poi_candidate(el, layer)
                if poi is None:
                    continue
                key = (poi["label"], round(poi["lat"], 3), round(poi["lon"], 3))
                if key in seen:
                    continue
                seen.add(key)
                # Distance filter
                d = _min_distance_to_polylines_km(poi["lat"], poi["lon"], polylines)
                if d > MAX_DISTANCE_KM:
                    continue
                poi["_dist_km"] = round(d, 2)
                candidates.append(poi)

            # Sort by distance ascending, take top N
            candidates.sort(key=lambda p: p["_dist_km"])
            cap = LAYER_CAPS.get(layer, 15)
            kept = candidates[:cap]
            print(
                f"  → {len(elements)} elements → {len(candidates)} on-route "
                f"→ keeping top {len(kept)} (cap={cap})"
            )

            # Strip the internal distance marker before output
            for p in kept:
                p.pop("_dist_km", None)
                all_pois.append(p)

            time.sleep(INTER_QUERY_SLEEP_S)

    return all_pois


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    target_ids = sys.argv[1:] or list(CORRIDORS.keys())

    summary: list[tuple[str, int]] = []
    for corridor_id in target_ids:
        if corridor_id not in CORRIDORS:
            print(f"! unknown corridor: {corridor_id}", file=sys.stderr)
            return 1
        pois = _fetch_corridor(corridor_id, CORRIDORS[corridor_id])
        output_path = OUTPUT_DIR / f"pois-{corridor_id}.json"
        with output_path.open("w") as f:
            json.dump(pois, f, indent=2, ensure_ascii=False)
        print(f"[{corridor_id}] wrote {len(pois)} POIs → {output_path}")
        summary.append((corridor_id, len(pois)))

    print("\n=== Summary ===")
    for cid, n in summary:
        print(f"  {cid}: {n} POIs")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
