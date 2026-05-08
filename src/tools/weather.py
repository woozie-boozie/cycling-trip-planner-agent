"""get_weather — typical weather for a location and month.

Mock data is grounded in real climate norms — June in Hamburg averages 17°C,
not 28°C — so the agent's recommendations stay credible. Real OpenWeather
integration arrives in Phase 1.10 via the USE_REAL_WEATHER env flag.
"""

from __future__ import annotations

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
def get_weather(input: GetWeatherInput) -> GetWeatherOutput:
    city_data = _CLIMATE.get(_normalize(input.location))
    if city_data is None or input.month not in city_data:
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

    avg, high, low, rain_days, rain_mm, note = city_data[input.month]
    return GetWeatherOutput(
        location=input.location,
        month=input.month,
        avg_temp_celsius=avg,
        avg_high_celsius=high,
        avg_low_celsius=low,
        rain_days_per_month=rain_days,
        avg_rain_mm=rain_mm,
        notes=note,
    )
