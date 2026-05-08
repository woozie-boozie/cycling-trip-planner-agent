"""get_weather — typical weather for a location and month.

Climate norms live in the `weather_norms` table in Postgres (seeded from
`_CLIMATE` below via `src/db/seed.py`). Norms are real (June in Hamburg
averages 17°C, not 28°C) so the agent's recommendations stay credible.

Real OpenWeather integration arrives in Phase 1.10 via the USE_REAL_WEATHER
env flag — same Pydantic schema, swap the data source.
"""

from __future__ import annotations

from sqlmodel import select

from src.db import get_async_session
from src.db.models import WeatherNorm as WeatherRow
from src.tools.base import register_tool
from src.tools.schemas import GetWeatherInput, GetWeatherOutput, Month

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
