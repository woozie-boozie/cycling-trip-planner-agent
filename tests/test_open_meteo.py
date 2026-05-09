"""Tests for the Open-Meteo integration in get_weather (Phase 1.10).

Two layers:

  1. Mocked tests (run by default, no network) — exercise the env-flag
     toggle, the parsing logic, and the fallback-on-failure behavior.
     Use `httpx.MockTransport` so we control responses precisely.

  2. Live tests marked with `@pytest.mark.evals` — hit the real Open-Meteo
     archive API. Skipped by default (CI doesn't need internet); run via
     `make evals` for end-to-end verification.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx
import pytest

import src.tools  # noqa: F401 — register tools
from src.tools import dispatch
from src.tools.schemas import GetWeatherOutput
from src.tools.weather import _fetch_open_meteo_norm


# ---------------------------------------------------------------------------
# Mocked unit tests — no network
# ---------------------------------------------------------------------------


def _make_archive_response(
    target_month_num: int,
    target_temps: list[float],
    target_maxes: list[float],
    target_mins: list[float],
    target_rains: list[float],
    other_month_temps: list[float] | None = None,
) -> dict:
    """Build a minimal Open-Meteo archive response that includes the target
    month plus some other-month noise so we test month-filtering."""
    other_month_temps = other_month_temps or []
    times: list[str] = []
    means: list[float] = []
    maxes: list[float] = []
    mins: list[float] = []
    rains: list[float] = []

    # Target month: 5 years × N days
    for year in range(2019, 2024):
        for day_idx, t in enumerate(target_temps):
            times.append(f"{year}-{target_month_num:02d}-{day_idx + 1:02d}")
            means.append(t)
            maxes.append(target_maxes[day_idx])
            mins.append(target_mins[day_idx])
            rains.append(target_rains[day_idx])

    # Other month noise (e.g. December) we should NOT include
    for year in range(2019, 2024):
        for day_idx, t in enumerate(other_month_temps):
            other_month = 12 if target_month_num != 12 else 1
            times.append(f"{year}-{other_month:02d}-{day_idx + 1:02d}")
            means.append(t)
            maxes.append(t + 5)
            mins.append(t - 5)
            rains.append(0.0)

    return {
        "latitude": 51.5,
        "longitude": -0.1,
        "daily": {
            "time": times,
            "temperature_2m_mean": means,
            "temperature_2m_max": maxes,
            "temperature_2m_min": mins,
            "precipitation_sum": rains,
        },
    }


@pytest.mark.asyncio
async def test_open_meteo_returns_aggregated_norm_for_known_city() -> None:
    """Happy path: city is in our coords table, archive returns clean data,
    we aggregate target-month days into a monthly norm."""
    archive_payload = _make_archive_response(
        target_month_num=6,
        target_temps=[16.0, 17.0, 18.0],  # June: 3 days × 5 years = 15 samples
        target_maxes=[20.0, 21.0, 22.0],
        target_mins=[12.0, 13.0, 14.0],
        target_rains=[0.0, 2.5, 0.5],
        other_month_temps=[2.0, 3.0],  # December noise we should ignore
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "archive-api.open-meteo.com" in request.url.host
        return httpx.Response(200, json=archive_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await _fetch_open_meteo_norm("London", "london", "June", client=client)

    assert result is not None
    assert result.location == "London"
    assert result.month == "June"
    # Aggregated mean of [16, 17, 18] = 17.0
    assert result.avg_temp_celsius == 17.0
    assert result.avg_high_celsius == 21.0
    assert result.avg_low_celsius == 13.0
    # 5 years × 1 rain-day-per-year (the 2.5mm one) = 1 rain day per month avg
    assert result.rain_days_per_month == 1
    assert "Open-Meteo" in (result.notes or "")


@pytest.mark.asyncio
async def test_open_meteo_returns_none_for_unknown_city() -> None:
    """City not in our coords table → return None so caller falls back to DB."""
    result = await _fetch_open_meteo_norm("Atlantis", "atlantis", "June")
    assert result is None


@pytest.mark.asyncio
async def test_open_meteo_returns_none_on_http_error() -> None:
    """5xx from the archive API → fall back, don't break the agent."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await _fetch_open_meteo_norm("London", "london", "June", client=client)
    assert result is None


@pytest.mark.asyncio
async def test_open_meteo_returns_none_on_malformed_response() -> None:
    """Archive returns 200 but with garbage payload → fall back."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"daily": {"time": []}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await _fetch_open_meteo_norm("London", "london", "June", client=client)
    assert result is None


@pytest.mark.asyncio
async def test_get_weather_uses_db_when_flag_disabled(
    monkeypatch: pytest.MonkeyPatch, seeded_db: None
) -> None:
    """Default behavior: USE_REAL_WEATHER unset → DB-backed mock."""
    monkeypatch.delenv("USE_REAL_WEATHER", raising=False)
    result = await dispatch("get_weather", {"location": "Amsterdam", "month": "June"})
    assert not result.is_error
    parsed = GetWeatherOutput.model_validate(result.content)
    # DB mock is the seeded value (Amsterdam June 16°C avg from `_CLIMATE`)
    assert parsed.notes is None or "Open-Meteo" not in (parsed.notes or "")


@pytest.mark.asyncio
async def test_get_weather_falls_back_to_db_when_flag_enabled_but_unknown_city(
    monkeypatch: pytest.MonkeyPatch, seeded_db: None
) -> None:
    """USE_REAL_WEATHER=true but city not in coords table → DB mock still works."""
    monkeypatch.setenv("USE_REAL_WEATHER", "true")
    # "Atlantis" isn't in _CITY_COORDS; tool falls through to DB
    result = await dispatch("get_weather", {"location": "Atlantis", "month": "June"})
    assert not result.is_error
    parsed = GetWeatherOutput.model_validate(result.content)
    # DB has its own "mock data" fallback for unknown city
    assert "Mock data" in (parsed.notes or "")


# ---------------------------------------------------------------------------
# Live test against real Open-Meteo — opt-in via the evals marker
# ---------------------------------------------------------------------------


@pytest.mark.evals
@pytest.mark.asyncio
async def test_open_meteo_live_london_june() -> None:
    """Hit the real Open-Meteo Archive API. Free, no auth, ~1s. Verifies
    the integration end-to-end against the live service.

    Skipped by default (run via `make evals`).
    """
    result = await _fetch_open_meteo_norm("London", "london", "June")
    assert result is not None, "Open-Meteo Archive API should be reachable"
    assert result.location == "London"
    assert result.month == "June"
    # Sanity range — London June is mild
    assert 10 < result.avg_temp_celsius < 22
    assert result.avg_high_celsius > result.avg_temp_celsius
    assert result.avg_low_celsius < result.avg_temp_celsius
    assert 0 <= result.rain_days_per_month <= 31
    assert result.avg_rain_mm >= 0
    assert "Open-Meteo" in (result.notes or "")
    print(
        f"\n  Live Open-Meteo result for London / June:"
        f"\n    avg_temp = {result.avg_temp_celsius}°C"
        f"\n    avg_high = {result.avg_high_celsius}°C"
        f"\n    avg_low  = {result.avg_low_celsius}°C"
        f"\n    rain_days_per_month = {result.rain_days_per_month}"
        f"\n    avg_rain_mm = {result.avg_rain_mm}"
    )
