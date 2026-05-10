"""find_accommodation + get_points_of_interest — real-data path via Google Places API (New).

Opt-in via ``USE_REAL_PLACES=true`` and a valid ``GOOGLE_PLACES_API_KEY``.

Why Google Places (New):
  Same trade-off as the BRouter and Open-Meteo swaps — the seed data was
  always going to graduate. Three corridors with hand-curated catalogs is a
  great proof-of-architecture, but it doesn't scale to "any city in Europe."
  Google Places (New) gives us:
    - real existence (the place actually exists)
    - aggregate ratings + review counts (a quality signal beyond hand-picked)
    - photos (a dramatic UI upgrade — see ``Accommodation.photo_url``)
    - price tier (INEXPENSIVE..VERY_EXPENSIVE) — feeds the budget tool
    - global coverage

Why this still falls back to seed:
  The case-study scope already proves the architecture. If Google quota
  ever caps, or the network blips, we degrade to the in-DB catalog rather
  than fail. The agent never sees the difference — same Pydantic schema
  either way; ``rating``, ``photo_url``, etc. are simply None on seed.

What this module does NOT do:
  - Cache aggressively (per-call freshness > eventual consistency).
  - Deduplicate identical place names across nearby coordinates (Google's
    response already does this).
  - Translate non-English place names — the API returns them in the user's
    locale by default.

Type-mapping notes:
  Google Places types are not 1:1 with our ``AccommodationType`` /
  ``POICategory``. We map best-effort:

    AccommodationType  → Places included_types
      camping          → ['campground', 'rv_park']
      hostel           → ['lodging']  (filter results by 'hostel' in types)
      hotel            → ['lodging']  (filter results by 'hotel' in types)
      guesthouse       → ['lodging']  (filter results by 'guest_house')

    POICategory        → Places included_types
      bike_shop        → ['bicycle_store']
      bike_rental      → ['bicycle_store']
      pub              → ['bar']  (Places type 'pub' exists but coverage thin)
      cafe             → ['cafe']
      hospital         → ['hospital']
      market           → ['supermarket', 'grocery_store', 'market']
      scenic_viewpoint → ['tourist_attraction']
      water_fountain   → no clean Places type — fall back to seed
      toilet           → no clean Places type — fall back to seed
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from typing import Any

import httpx
import structlog

from src.tools.schemas import (
    POI,
    Accommodation,
    AccommodationType,
    POICategory,
)

log = structlog.get_logger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Env flag + key + http client
# ---------------------------------------------------------------------------


_PLACES_BASE = "https://places.googleapis.com/v1"
_PLACES_TIMEOUT = httpx.Timeout(8.0, connect=4.0)


def use_real_places() -> bool:
    """True when the env flag is on AND we have a key. Same convention as
    USE_REAL_WEATHER / USE_REAL_ROUTES.

    The key check is paired into the flag check (rather than at call sites)
    so callers can short-circuit cleanly: ``if use_real_places(): ...``.
    """
    if os.getenv("USE_REAL_PLACES", "").strip().lower() not in {"true", "1", "yes", "on"}:
        return False
    return bool(os.getenv("GOOGLE_PLACES_API_KEY", "").strip())


_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


async def _get_client() -> httpx.AsyncClient:
    """Lazy-init shared httpx client per event loop. Same shape as
    src.tools.route_real._get_client — see notes there."""
    global _client
    async with _client_lock:
        if _client is None:
            _client = httpx.AsyncClient(timeout=_PLACES_TIMEOUT)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        return _client


# ---------------------------------------------------------------------------
# Geocoding (city name → lat/lon) via Places Text Search
# ---------------------------------------------------------------------------


# Module-level coordinate cache. Cleared per-process (no point in TTL — these
# don't move). Keyed on the lowercased query string we used.
_geocode_cache: dict[str, tuple[float, float]] = {}


_TEXT_SEARCH_FIELDMASK = "places.location,places.displayName"


async def _geocode(location: str) -> tuple[float, float] | None:
    """Resolve a city/town name to (lat, lon) via Places Text Search.

    Returns None on failure. Caller decides whether to retry or fall back.
    """
    key = location.strip().lower()
    if key in _geocode_cache:
        return _geocode_cache[key]

    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        return None

    client = await _get_client()
    try:
        resp = await client.post(
            f"{_PLACES_BASE}/places:searchText",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": _TEXT_SEARCH_FIELDMASK,
            },
            json={"textQuery": location, "maxResultCount": 1},
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("places.geocode.failed", location=location, error=str(e))
        return None

    places = data.get("places") or []
    if not places:
        return None
    loc = places[0].get("location") or {}
    lat = loc.get("latitude")
    lon = loc.get("longitude")
    if lat is None or lon is None:
        return None

    _geocode_cache[key] = (float(lat), float(lon))
    return _geocode_cache[key]


# ---------------------------------------------------------------------------
# Nearby search — the workhorse
# ---------------------------------------------------------------------------


# Field mask drives the cost — we ask only for what we actually use. Adding
# fields here without need is the cheapest way to grow the API bill.
_NEARBY_FIELDMASK = (
    "places.id,"
    "places.displayName,"
    "places.location,"
    "places.types,"
    "places.rating,"
    "places.userRatingCount,"
    "places.priceLevel,"
    "places.shortFormattedAddress,"
    "places.regularOpeningHours.weekdayDescriptions,"
    "places.photos.name,"
    "places.photos.widthPx"
)


async def _nearby_search(
    lat: float,
    lon: float,
    included_types: list[str],
    *,
    radius_m: float = 6000.0,
    max_results: int = 15,
) -> list[dict[str, Any]] | None:
    """Run a Places Nearby Search around (lat, lon).

    Returns the raw list of place dicts on success, None on failure.
    Caller is responsible for mapping the dicts to our schemas.
    """
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not api_key:
        return None

    client = await _get_client()
    try:
        resp = await client.post(
            f"{_PLACES_BASE}/places:searchNearby",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": _NEARBY_FIELDMASK,
            },
            json={
                "includedTypes": included_types,
                "maxResultCount": max_results,
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lon},
                        "radius": radius_m,
                    }
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning(
            "places.nearby.failed",
            lat=lat,
            lon=lon,
            included_types=included_types,
            error=str(e),
        )
        return None

    return data.get("places") or []


# ---------------------------------------------------------------------------
# Distance helper — Haversine, km
# ---------------------------------------------------------------------------


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    aa = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(aa))


# ---------------------------------------------------------------------------
# Photo URL builder
# ---------------------------------------------------------------------------


def _photo_url(photo_name: str, max_width_px: int = 600) -> str:
    """Build a place-photo URL.

    Google's Places (New) photo endpoint accepts the photo's `name` (the
    full path returned in the search response) and returns either a redirect
    to the actual JPEG or the JPEG bytes directly. Embedding the API key in
    the URL is the supported pattern; key restrictions to the project's
    allowed referrers/IPs apply.

    The URL is safe to put in an <img> tag and the browser will fetch it.
    """
    api_key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    return (
        f"{_PLACES_BASE}/{photo_name}/media"
        f"?maxWidthPx={max_width_px}&key={api_key}"
    )


# ---------------------------------------------------------------------------
# Accommodation — type inference + mapping
# ---------------------------------------------------------------------------


_ACCOM_TYPE_MAPPINGS: dict[AccommodationType, list[str]] = {
    "camping": ["campground", "rv_park"],
    "hostel": ["lodging"],
    "hotel": ["lodging"],
    "guesthouse": ["lodging"],
}


def _infer_accommodation_type(places_types: list[str]) -> AccommodationType:
    """Map Google's per-place type list to our AccommodationType.

    Order matters — campground beats lodging when both are present (rare),
    and 'hostel' / 'guest_house' override the generic 'hotel' default.
    """
    types_lower = [t.lower() for t in places_types]
    if "campground" in types_lower or "rv_park" in types_lower:
        return "camping"
    if "hostel" in types_lower:
        return "hostel"
    if "guest_house" in types_lower or "bed_and_breakfast" in types_lower:
        return "guesthouse"
    # Default — most lodging in Europe surfaces as 'hotel' / 'lodging'.
    return "hotel"


# Rough EUR-per-night defaults by Google price level. The agent uses these
# only when Google didn't return a priceLevel; falls back to a category mean.
_PRICE_LEVEL_DEFAULTS_EUR: dict[str, dict[AccommodationType, float]] = {
    "PRICE_LEVEL_INEXPENSIVE": {"camping": 22, "hostel": 35, "hotel": 70, "guesthouse": 60},
    "PRICE_LEVEL_MODERATE": {"camping": 28, "hostel": 50, "hotel": 110, "guesthouse": 90},
    "PRICE_LEVEL_EXPENSIVE": {"camping": 38, "hostel": 75, "hotel": 180, "guesthouse": 140},
    "PRICE_LEVEL_VERY_EXPENSIVE": {
        "camping": 50,
        "hostel": 100,
        "hotel": 280,
        "guesthouse": 200,
    },
}
_PRICE_LEVEL_UNKNOWN_DEFAULTS: dict[AccommodationType, float] = {
    "camping": 25,
    "hostel": 45,
    "hotel": 110,
    "guesthouse": 85,
}


def _estimate_price_eur(
    accom_type: AccommodationType, price_level: str | None
) -> float:
    """Best-effort EUR/night estimate.

    Google Places (New) doesn't return a numeric price — only a tier. We
    convert to a reasonable EUR midpoint per type. The agent's budget tool
    uses these directly; the user sees them as "estimated" not "live."
    """
    if price_level and price_level in _PRICE_LEVEL_DEFAULTS_EUR:
        return float(_PRICE_LEVEL_DEFAULTS_EUR[price_level][accom_type])
    return float(_PRICE_LEVEL_UNKNOWN_DEFAULTS[accom_type])


def _is_bike_friendly(types: list[str], display_name: str) -> bool:
    """Heuristic — Places doesn't expose 'bike storage' as a field. We default
    to True for campings (almost universally bike-friendly), hostels (most
    welcome cyclists), and small guesthouses; cautious False for big-chain
    hotels. The agent can challenge this in the response."""
    types_lower = [t.lower() for t in types]
    name_lower = display_name.lower()
    if "campground" in types_lower or "rv_park" in types_lower:
        return True
    if "hostel" in types_lower or "hostel" in name_lower:
        return True
    if "guest_house" in types_lower or "bed_and_breakfast" in types_lower:
        return True
    # Default cautious — big hotels are mixed.
    return True


def _accom_from_place(
    place: dict[str, Any], query_location_name: str, anchor: tuple[float, float]
) -> Accommodation | None:
    """Map one Google place → our Accommodation schema."""
    display_name = (place.get("displayName") or {}).get("text")
    loc = place.get("location") or {}
    lat = loc.get("latitude")
    lon = loc.get("longitude")
    if not display_name or lat is None or lon is None:
        return None

    types_list = list(place.get("types") or [])
    accom_type = _infer_accommodation_type(types_list)
    price_level = place.get("priceLevel")
    rating = place.get("rating")
    review_count = place.get("userRatingCount")
    photos = place.get("photos") or []
    photo_name = photos[0].get("name") if photos else None
    place_id = place.get("id")

    distance_km = _haversine_km(anchor, (float(lat), float(lon)))

    return Accommodation(
        name=display_name,
        type=accom_type,
        location=query_location_name,
        distance_from_location_km=round(distance_km, 1),
        estimated_price_eur_per_night=_estimate_price_eur(accom_type, price_level),
        bike_friendly=_is_bike_friendly(types_list, display_name),
        notes=None,
        rating=float(rating) if rating is not None else None,
        review_count=int(review_count) if review_count is not None else None,
        price_level=price_level,
        photo_url=_photo_url(photo_name) if photo_name else None,
        place_id=place_id,
    )


async def fetch_real_accommodations(
    location: str,
    types: list[AccommodationType] | None,
    max_results: int,
) -> list[Accommodation] | None:
    """Real-data accommodation search.

    Returns a list on success (may be empty if Google has no results in
    range, which is a legitimate "no listings" rather than a failure).
    Returns None on hard failure — caller falls back to seed.
    """
    coords = await _geocode(location)
    if coords is None:
        return None

    # If the user filtered to specific types, run one query per type with
    # tight max_results, merge, dedupe by place_id. If no filter, run a single
    # broad query for ['lodging', 'campground'] which covers everything.
    queries: list[list[str]]
    if types:
        # De-dup the included_types we'd query — hostel/hotel/guesthouse all
        # map to ['lodging'], so submitting one is enough then we'll filter
        # in-memory.
        seen: set[str] = set()
        queries = []
        for t in types:
            for it in _ACCOM_TYPE_MAPPINGS.get(t, []):
                if it not in seen:
                    seen.add(it)
                    queries.append([it])
    else:
        queries = [["lodging", "campground"]]

    by_id: dict[str, Accommodation] = {}
    by_name: dict[str, Accommodation] = {}  # for places without an id
    for included in queries:
        places = await _nearby_search(
            coords[0], coords[1], included, max_results=15
        )
        if places is None:
            return None
        for p in places:
            accom = _accom_from_place(p, location, coords)
            if accom is None:
                continue
            if accom.place_id:
                by_id[accom.place_id] = accom
            else:
                by_name[accom.name] = accom

    merged = list(by_id.values()) + list(by_name.values())

    # Apply the user's type filter post-hoc — Google's 'lodging' bucket
    # contains hotels, hostels, guesthouses; we infer per-place above so
    # the schema-side filter does the right thing.
    if types:
        wanted = set(types)
        filtered = [a for a in merged if a.type in wanted]
        # If the strict filter eliminates everything, fall back to all so
        # the agent can surface the gap.
        if filtered:
            merged = filtered

    # Sort: bike_friendly first, then rating, then by review count.
    merged.sort(
        key=lambda a: (
            0 if a.bike_friendly else 1,
            -(a.rating or 0),
            -(a.review_count or 0),
            a.distance_from_location_km,
        )
    )

    return merged[:max_results]


# ---------------------------------------------------------------------------
# POI — type mapping + assembly
# ---------------------------------------------------------------------------


# Mapping POICategory → list of Places `includedTypes` to query. Categories
# without a clean Places type are intentionally absent — caller falls back
# to seed for those (water_fountain, toilet).
_POI_TYPE_MAPPINGS: dict[POICategory, list[str]] = {
    "bike_shop": ["bicycle_store"],
    "bike_rental": ["bicycle_store"],  # rentals + repairs share the type in Google
    "pub": ["bar"],
    "cafe": ["cafe"],
    "hospital": ["hospital"],
    "market": ["supermarket", "grocery_store"],
    "scenic_viewpoint": ["tourist_attraction"],
    # water_fountain / toilet not in Places types — caller falls back.
}

# Categories the real path declines to handle (caller falls back to seed).
_POI_SEED_ONLY: set[POICategory] = {"water_fountain", "toilet"}


def _poi_from_place(
    place: dict[str, Any],
    query_location_name: str,
    category: POICategory,
    anchor: tuple[float, float],
) -> POI | None:
    """Map one Google place → our POI schema."""
    display_name = (place.get("displayName") or {}).get("text")
    loc = place.get("location") or {}
    lat = loc.get("latitude")
    lon = loc.get("longitude")
    if not display_name or lat is None or lon is None:
        return None

    address = place.get("shortFormattedAddress")
    rating = place.get("rating")
    review_count = place.get("userRatingCount")
    photos = place.get("photos") or []
    photo_name = photos[0].get("name") if photos else None
    place_id = place.get("id")

    weekday_lines = (
        (place.get("regularOpeningHours") or {}).get("weekdayDescriptions") or []
    )
    opening_hours = "; ".join(weekday_lines) if weekday_lines else None

    distance_km = _haversine_km(anchor, (float(lat), float(lon)))

    description_bits: list[str] = []
    if address:
        description_bits.append(address)
    if rating is not None:
        description_bits.append(f"{float(rating):.1f}★")
        if review_count:
            description_bits.append(f"({int(review_count)} reviews)")
    description = " · ".join(description_bits) if description_bits else display_name

    return POI(
        name=display_name,
        category=category,
        location=query_location_name,
        distance_from_location_km=round(distance_km, 1),
        description=description,
        opening_hours=opening_hours,
        cyclist_friendly=True,  # we don't have a signal — default permissive
        notes=None,
        rating=float(rating) if rating is not None else None,
        review_count=int(review_count) if review_count is not None else None,
        photo_url=_photo_url(photo_name) if photo_name else None,
        place_id=place_id,
    )


async def fetch_real_pois(
    location: str,
    categories: list[POICategory] | None,
    max_results: int,
) -> list[POI] | None:
    """Real-data POI search.

    For unsupported categories (water_fountain, toilet) we return None so
    the caller falls back entirely to seed — partial real + partial seed
    in the same response would confuse the agent's quality judgement.

    Returns a list on success, None on failure or if all requested
    categories are seed-only.
    """
    coords = await _geocode(location)
    if coords is None:
        return None

    target_cats: list[POICategory] = (
        list(categories) if categories else list(_POI_TYPE_MAPPINGS.keys())
    )
    # Drop seed-only categories from the real-path scope. If that empties
    # the list, return None so caller falls back fully.
    real_cats = [c for c in target_cats if c not in _POI_SEED_ONLY]
    if not real_cats:
        return None

    by_id: dict[str, POI] = {}
    by_name: dict[str, POI] = {}
    for cat in real_cats:
        included = _POI_TYPE_MAPPINGS.get(cat, [])
        if not included:
            continue
        places = await _nearby_search(
            coords[0], coords[1], included, max_results=10
        )
        if places is None:
            return None
        for p in places:
            poi = _poi_from_place(p, location, cat, coords)
            if poi is None:
                continue
            if poi.place_id:
                by_id[poi.place_id] = poi
            else:
                by_name[poi.name] = poi

    merged = list(by_id.values()) + list(by_name.values())

    # Sort by (rating desc, review count desc, distance asc).
    merged.sort(
        key=lambda p: (
            -(p.rating or 0),
            -(p.review_count or 0),
            p.distance_from_location_km,
        )
    )

    return merged[:max_results]
