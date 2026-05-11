"""get_weather — typical weather for a location and month.

THREE storage backends, one Pydantic schema:

  1. Postgres `weather_norms` table (default) — seeded from `_CLIMATE` below
     via `src/db/seed.py`. Hand-curated mock based on real climate averages.
  2. Open-Meteo Archive API (Phase 1.10) — opt-in via `USE_REAL_WEATHER=true`.
     No API key required. Computes 5-year monthly climate norms from the
     ECMWF ERA5 reanalysis archive. Falls back to (1) on any failure.
  3. SQLite in-memory (tests) — same SQLModel schema as (1), populated by
     the `seeded_db` fixture. Tests never hit Open-Meteo.

Switch backends without touching schemas, the registry, the agent loop,
or the system prompt. That's the abstraction — same `GetWeatherOutput`
return shape regardless of where the data came from.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from statistics import mean

import httpx
import structlog
from sqlmodel import select

from src.db import get_async_session
from src.db.models import WeatherNorm as WeatherRow
from src.tools.base import register_tool
from src.tools.schemas import GetWeatherInput, GetWeatherOutput, Month

log = structlog.get_logger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)  # silence chatty INFO logs

# ---------------------------------------------------------------------------
# Open-Meteo integration (Phase 1.10)
# ---------------------------------------------------------------------------

_OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Lat/lon for every city we've seeded. Pre-populating beats geocoding on
# every call: lookups are O(1), no extra HTTP round-trip, no second API
# dependency. Unknown cities fall through to the DB mock — which itself has
# a "mock data" note that the agent surfaces honestly to the user.
#
# As of 2026-05-12, `_get_city_coords()` ALSO checks the corridor YAML
# registry first, so new corridors added via `data/corridors/*.yaml`
# automatically populate the weather lookup — no manual dict edit needed.
# This dict is the explicit fallback for cities not in any corridor (e.g.
# Crystal Palace as a through-town historically; future non-corridor seeds).
_CITY_COORDS: dict[str, tuple[float, float]] = {
    # Amsterdam → Copenhagen corridor
    "amsterdam": (52.3676, 4.9041),
    "hoorn": (52.6422, 5.0594),
    "groningen": (53.2194, 6.5665),
    "bremen": (53.0793, 8.8017),
    "hamburg": (53.5511, 9.9937),
    "lübeck": (53.8654, 10.6866),
    "puttgarden": (54.5092, 11.2226),
    "rødby": (54.6906, 11.3539),
    "vordingborg": (55.0084, 11.9098),
    "copenhagen": (55.6761, 12.5683),
    # Avenue Verte (London → Paris)
    "london": (51.5074, -0.1278),
    "east grinstead": (51.1267, -0.0067),
    "lewes": (50.8736, 0.0097),
    "newhaven": (50.7906, 0.0533),
    "dieppe": (49.9239, 1.0775),
    "forges-les-eaux": (49.6173, 1.5460),
    "beauvais": (49.4295, 2.0808),
    "cergy-pontoise": (49.0398, 2.0712),
    "paris": (48.8566, 2.3522),
    # London → Brighton
    "crystal palace": (51.4189, -0.0735),
    "brighton": (50.8225, -0.1372),
}

def _get_city_coords(location_lower: str) -> tuple[float, float] | None:
    """Resolve a lowercased city name to (lat, lon) for Open-Meteo lookups.

    Lookup order:
      1. The corridor YAML registry — any waypoint defined in
         ``data/corridors/*.yaml`` is automatically available. Adding a
         new corridor auto-populates its cities for weather without
         touching this file.
      2. The manual ``_CITY_COORDS`` fallback for cities that don't
         appear in any corridor.

    Returns ``None`` if neither source knows the city — caller falls back
    to the DB mock or the live geocoder as before.
    """
    # Registry lookup is cheap (in-memory dict from lru_cached load).
    # Walk every variant's anchors looking for a name match. ~30 corridors
    # × ~10 anchors × 1-3 variants ≈ 1,000 string comparisons worst case,
    # well below noise on a single weather call.
    from src.tools.corridor_registry import load_all_corridors

    catalog = load_all_corridors()
    seen: set[tuple[str, str]] = set()
    for key, variants in catalog.items():
        if key in seen:
            continue
        seen.add(key)
        for variant in variants:
            for anchor in variant.anchors:
                if anchor.name.lower() == location_lower:
                    return (anchor.lat, anchor.lon)

    return _CITY_COORDS.get(location_lower)


_MONTH_TO_NUMBER: dict[Month, int] = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


def _use_real_weather() -> bool:
    return os.getenv("USE_REAL_WEATHER", "").strip().lower() in {"true", "1", "yes", "on"}


async def _fetch_open_meteo_norm(
    location: str,
    location_lower: str,
    month: Month,
    *,
    client: httpx.AsyncClient | None = None,
) -> GetWeatherOutput | None:
    """Compute a multi-year monthly climate norm from Open-Meteo's archive.

    Returns None on any failure (unknown city, network error, malformed
    response, etc.) so the caller falls back to the DB mock and the agent
    surfaces no error to the user.

    Strategy: pull 5 years of daily data from the ECMWF ERA5 archive,
    filter client-side to the target month, aggregate to a monthly norm.
    """
    coords = _get_city_coords(location_lower)
    if coords is None:
        log.info("open_meteo.skip_unknown_city", location=location)
        return None

    month_num = _MONTH_TO_NUMBER.get(month)
    if month_num is None:
        return None

    # Use a 5-year window ending in last full year. Archive lags by a few
    # weeks for the most recent dates so don't assume current year is full.
    end_year = datetime.now().year - 1
    start_year = end_year - 4
    start_date = f"{start_year}-01-01"
    end_date = f"{end_year}-12-31"

    lat, lon = coords
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": (
            "temperature_2m_mean,temperature_2m_max,"
            "temperature_2m_min,precipitation_sum"
        ),
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=15.0)

    try:
        try:
            resp = await client.get(_OPEN_METEO_ARCHIVE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("open_meteo.http_error", error=str(e), location=location)
            return None

        daily = data.get("daily") or {}
        times: list[str] = daily.get("time") or []
        if not times:
            return None

        try:
            target_idx = [i for i, t in enumerate(times) if int(t.split("-")[1]) == month_num]
        except (IndexError, ValueError):
            return None
        if not target_idx:
            return None

        def _vals(key: str) -> list[float]:
            arr = daily.get(key) or []
            return [arr[i] for i in target_idx if i < len(arr) and arr[i] is not None]

        means = _vals("temperature_2m_mean")
        maxes = _vals("temperature_2m_max")
        mins = _vals("temperature_2m_min")
        rains = _vals("precipitation_sum")

        if not (means and maxes and mins and rains):
            return None

        # Distinct years in the sampled month — this is the correct denominator
        # for converting a multi-year sum into a per-month figure. Counting
        # `len(target_idx) / 30` would mis-handle 28-/31-day months and any
        # missing days in the archive.
        distinct_years = {times[i].split("-", 1)[0] for i in target_idx}
        years_in_data = max(1, len(distinct_years))

        avg_temp = round(mean(means), 1)
        avg_high = round(mean(maxes), 1)
        avg_low = round(mean(mins), 1)
        avg_rain_mm = round(sum(rains) / years_in_data, 1)
        # "Rain day" = day with ≥ 1mm precipitation, the WMO-standard threshold.
        rain_days = round(sum(1 for r in rains if r >= 1.0) / years_in_data)

        return GetWeatherOutput(
            location=location,
            month=month,
            avg_temp_celsius=avg_temp,
            avg_high_celsius=avg_high,
            avg_low_celsius=avg_low,
            rain_days_per_month=rain_days,
            avg_rain_mm=avg_rain_mm,
            notes=(
                f"Real climate norm — Open-Meteo Archive (ECMWF ERA5), "
                f"{start_year}–{end_year}, {len(target_idx)} {month} days sampled. "
                f"No API key required."
            ),
        )
    finally:
        if own_client:
            await client.aclose()

# Per-city, per-month climate norms.
# Sourced from typical climate averages for these European cities.
# (avg_temp_c, avg_high_c, avg_low_c, rain_days, avg_rain_mm, notes)
_City = str
_Stats = tuple[float, float, float, int, float, str | None]

_CLIMATE: dict[_City, dict[Month, _Stats]] = {
    "amsterdam": {
        "April": (10.0, 13.5, 5.0, 13, 50.0, "Cool, frequent showers — pack waterproofs."),
        "May": (13.0, 17.0, 8.5, 11, 55.0, None),
        "June": (16.0, 19.5, 11.5, 11, 65.0, "Mild, occasional rain. Long daylight hours."),
        "July": (18.0, 22.0, 13.5, 11, 75.0, "Warmest month. Westerly headwinds common."),
        "August": (18.0, 22.0, 13.5, 11, 80.0, None),
        "September": (15.5, 19.0, 11.0, 12, 75.0, None),
    },
    "hoorn": {
        "May": (13.0, 17.0, 8.5, 11, 55.0, None),
        "June": (16.0, 19.5, 11.5, 11, 65.0, None),
        "July": (18.0, 22.0, 13.5, 11, 75.0, None),
    },
    "groningen": {
        "May": (12.5, 16.5, 7.5, 11, 50.0, None),
        "June": (15.5, 19.0, 11.0, 11, 65.0, None),
        "July": (17.5, 21.0, 13.0, 11, 75.0, None),
    },
    "bremen": {
        "May": (12.5, 17.0, 7.5, 11, 55.0, None),
        "June": (15.5, 20.0, 11.0, 11, 75.0, "Mild but rain-prone — 75mm avg in June."),
        "July": (17.5, 22.0, 13.0, 12, 80.0, None),
    },
    "hamburg": {
        "May": (12.5, 17.0, 7.5, 11, 55.0, None),
        "June": (15.5, 20.0, 11.0, 11, 75.0, None),
        "July": (17.5, 22.0, 13.0, 12, 80.0, None),
    },
    "lübeck": {
        "May": (12.5, 17.0, 7.0, 11, 55.0, None),
        "June": (15.5, 20.0, 10.5, 11, 70.0, None),
        "July": (17.5, 22.0, 13.0, 12, 75.0, None),
    },
    "puttgarden": {
        "June": (14.5, 18.5, 10.5, 10, 55.0, "Coastal — wind exposure on the Fehmarn ferry crossing."),
        "July": (17.0, 21.0, 13.0, 11, 65.0, None),
    },
    "rødby": {
        "June": (14.5, 18.5, 10.5, 10, 55.0, "Lolland is flat and exposed — headwinds likely."),
        "July": (17.0, 21.0, 13.0, 11, 65.0, None),
    },
    "vordingborg": {
        "June": (14.5, 18.5, 10.5, 10, 50.0, None),
        "July": (17.0, 21.0, 13.0, 10, 60.0, None),
    },
    "copenhagen": {
        "May": (11.5, 16.0, 7.0, 10, 45.0, None),
        "June": (15.0, 19.5, 10.5, 10, 55.0, "Mild and dry-ish. Daylight until ~22:00."),
        "July": (17.5, 21.5, 13.0, 11, 65.0, None),
        "August": (17.5, 21.5, 13.0, 12, 65.0, None),
    },
    # ---- Avenue Verte corridor (London → Paris) ---------------------------
    "london": {
        "April": (10.0, 14.0, 6.0, 11, 45.0, "Cool, changeable. Pack layers."),
        "May": (13.5, 17.5, 9.0, 11, 50.0, None),
        "June": (16.5, 20.5, 12.0, 10, 50.0, "Mild. Long daylight. Showers possible — pack waterproofs."),
        "July": (18.5, 23.0, 14.0, 9, 45.0, "Warmest month. Driest of the year on average."),
        "August": (18.0, 22.5, 13.5, 10, 50.0, None),
        "September": (15.5, 20.0, 11.0, 11, 55.0, None),
    },
    "east grinstead": {
        "May": (12.5, 16.5, 8.0, 11, 55.0, None),
        "June": (15.5, 19.5, 11.0, 10, 55.0, "South Downs climbs feel cooler — bring a layer."),
        "July": (17.5, 22.0, 13.0, 9, 50.0, None),
    },
    "lewes": {
        "May": (12.5, 16.5, 7.5, 11, 55.0, None),
        "June": (15.5, 19.5, 10.5, 10, 50.0, None),
        "July": (17.5, 22.0, 12.5, 9, 45.0, None),
    },
    "newhaven": {
        "May": (12.0, 16.0, 8.0, 10, 45.0, None),
        "June": (15.0, 19.0, 11.0, 9, 45.0, "Coastal — wind exposure on the cliff approach to the ferry."),
        "July": (17.0, 21.0, 13.0, 8, 40.0, None),
    },
    "dieppe": {
        "May": (12.0, 16.0, 8.0, 10, 50.0, None),
        "June": (15.0, 19.0, 11.0, 9, 50.0, "Channel coast — prevailing south-westerlies tend to push you towards Paris."),
        "July": (17.0, 21.0, 13.0, 8, 45.0, None),
    },
    "forges-les-eaux": {
        "May": (12.5, 17.0, 7.5, 11, 60.0, None),
        "June": (16.0, 20.5, 11.0, 10, 60.0, "Rolling Picardy farmland — beautiful in June."),
        "July": (18.0, 22.5, 13.0, 9, 55.0, None),
    },
    "beauvais": {
        "May": (13.0, 17.5, 8.0, 10, 55.0, None),
        "June": (16.5, 21.0, 11.5, 9, 55.0, None),
        "July": (18.5, 23.0, 13.5, 9, 55.0, None),
    },
    "cergy-pontoise": {
        "May": (13.5, 18.0, 8.5, 10, 55.0, None),
        "June": (17.0, 22.0, 12.0, 9, 55.0, None),
        "July": (19.0, 24.0, 14.0, 8, 55.0, None),
    },
    "paris": {
        "April": (11.5, 16.0, 6.5, 11, 50.0, None),
        "May": (15.0, 19.5, 9.5, 11, 60.0, None),
        "June": (18.0, 22.5, 12.5, 9, 55.0, "Mild and pleasant. Watch for weekend crowds at the Champs-Élysées."),
        "July": (20.5, 25.0, 15.0, 8, 50.0, "Warmest month. Heatwaves possible."),
        "August": (20.0, 25.0, 14.5, 9, 50.0, None),
        "September": (17.0, 21.5, 12.0, 10, 55.0, None),
    },
    "crystal palace": {
        "June": (16.0, 20.0, 12.0, 10, 50.0, None),
        "July": (18.0, 22.5, 13.5, 9, 45.0, None),
    },
    "brighton": {
        "May": (12.0, 16.0, 8.0, 10, 45.0, None),
        "June": (15.0, 19.0, 11.0, 9, 40.0, "Sea breeze keeps it cooler than inland."),
        "July": (17.5, 21.5, 13.0, 8, 35.0, None),
        "August": (17.5, 21.5, 13.0, 9, 45.0, None),
    },
}


def _normalize(s: str) -> str:
    return s.strip().lower()


@register_tool(
    name="get_weather",
    description=(
        "Get typical/historical weather for a city and month — average "
        "temperature, high, low, rain frequency, and rainfall. Use once per "
        "overnight stop (or once for the corridor if the trip is short) to "
        "inform pacing, gear, and rest-day suggestions."
    ),
    input_model=GetWeatherInput,
    output_model=GetWeatherOutput,
)
async def get_weather(input: GetWeatherInput) -> GetWeatherOutput:
    location_lower = _normalize(input.location)

    # Phase 1.10: opt into real Open-Meteo data via the env flag.
    # Falls back to the DB mock on any failure — same Pydantic schema
    # either way, so the agent never sees the difference.
    if _use_real_weather():
        live = await _fetch_open_meteo_norm(input.location, location_lower, input.month)
        if live is not None:
            return live

    async with get_async_session() as session:
        result = await session.execute(
            select(WeatherRow).where(
                WeatherRow.location_lower == location_lower,
                WeatherRow.month == input.month,
            )
        )
        row = result.scalar_one_or_none()

    if row is None:
        # Fall back to a temperate-Europe approximation rather than failing —
        # keeps the agent moving and we flag the uncertainty in `notes`.
        return GetWeatherOutput(
            location=input.location,
            month=input.month,
            avg_temp_celsius=15.0,
            avg_high_celsius=19.0,
            avg_low_celsius=10.0,
            rain_days_per_month=11,
            avg_rain_mm=65.0,
            notes=(
                "Mock data — exact climate record unavailable for this "
                "location/month. Treat as a temperate-Europe approximation."
            ),
        )

    return GetWeatherOutput(
        location=input.location,
        month=input.month,  # validated by Pydantic against Month enum
        avg_temp_celsius=row.avg_temp_celsius,
        avg_high_celsius=row.avg_high_celsius,
        avg_low_celsius=row.avg_low_celsius,
        rain_days_per_month=row.rain_days_per_month,
        avg_rain_mm=row.avg_rain_mm,
        notes=row.notes,
    )
