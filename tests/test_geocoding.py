"""Regression tests for the geocoding + BRouter sanity-check fixes.

Covers two production bugs surfaced by the London → Norfolk Broads chat on
2026-05-11:

  1. ``_geocode_location`` resolved bare UK city names (Cambridge, Newmarket,
     Hertford, Thetford, Ely) to their more-populous US namesakes because
     the *first* endpoint geocoded with no bias and Open-Meteo's count=1
     ranks by population. BRouter then routed across the wrong continent
     and returned ~120 km for a real ~25 km segment.

  2. Even after geocoding, BRouter can return wildly-wrong distances
     (timeouts, route-not-found, OSM data gaps). A 542 km return for a
     ~40 km segment slipped through to the LLM, which had to dance around
     the nonsense mid-conversation.

Both tests mock external services (Open-Meteo, BRouter) so they're
fast and hermetic — no network required.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest


# ---------------------------------------------------------------------------
# Joint geocoding — _geocode_pair must pick the UK pair over the US one
# ---------------------------------------------------------------------------


def _open_meteo_candidates(*coords: tuple[float, float]) -> dict[str, Any]:
    """Build a minimal Open-Meteo geocoding response from a list of (lat, lon)
    candidates in population-ranked order."""
    return {
        "results": [
            {
                "id": idx,
                "name": "test",
                "latitude": lat,
                "longitude": lon,
            }
            for idx, (lat, lon) in enumerate(coords)
        ]
    }


@pytest.mark.asyncio
async def test_geocode_pair_picks_uk_pair_over_us_namesakes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression — Phase 1.13: Cambridge → Newmarket must resolve to the
    UK pair, not Cambridge MA + Newmarket NH (the population-ranked top
    results). The joint-haversine minimisation does the disambiguation."""
    from src.tools import route as route_module

    # Real-world coordinates (rough):
    # Cambridge MA, USA — pop 118k, top global by relevance
    # Cambridge, UK     — pop 145k, but ranked below in Open-Meteo's data
    # Cambridge, Ontario
    cambridge_candidates = _open_meteo_candidates(
        (42.3736, -71.1097),  # Cambridge MA (top by Open-Meteo population)
        (52.2053, 0.1218),    # Cambridge UK (real intent)
        (43.3601, -80.3144),  # Cambridge Ontario
    )
    # Newmarket Ontario — most populous
    # Newmarket NH USA — much closer to Cambridge MA (the wrong start)
    # Newmarket UK (Suffolk) — only ~25 km from Cambridge UK
    newmarket_candidates = _open_meteo_candidates(
        (44.0531, -79.4612),  # Newmarket Ontario
        (43.0762, -70.9356),  # Newmarket NH (~110 km from Cambridge MA)
        (52.2455, 0.4108),    # Newmarket UK (~25 km from Cambridge UK)
    )

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        # Return Cambridge candidates first, then Newmarket — matches the
        # order _geocode_pair calls _geocode_candidates(start, end).
        call_count["n"] += 1
        if call_count["n"] == 1:
            assert "Cambridge" in str(request.url)
            return httpx.Response(200, json=cambridge_candidates)
        assert "Newmarket" in str(request.url)
        return httpx.Response(200, json=newmarket_candidates)

    transport = httpx.MockTransport(handler)

    # Patch httpx.AsyncClient inside the module under test to use our mock.
    real_async_client = httpx.AsyncClient

    def patched_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(route_module.httpx, "AsyncClient", patched_client)

    result = await route_module._geocode_pair("Cambridge", "Newmarket")
    assert result is not None
    start_coords, end_coords = result

    # The UK pair: Cambridge UK (~52.20, 0.12) + Newmarket UK (~52.24, 0.41)
    # — ~25 km apart. The disambiguator should pick this over the US pairs
    # which are 100+ km apart.
    assert 52.0 < start_coords[0] < 52.4, (
        f"Expected Cambridge UK latitude (~52.20), got {start_coords[0]}"
    )
    assert -0.5 < start_coords[1] < 0.5, (
        f"Expected Cambridge UK longitude (~0.12), got {start_coords[1]}"
    )
    assert 52.0 < end_coords[0] < 52.4, (
        f"Expected Newmarket UK latitude (~52.24), got {end_coords[0]}"
    )
    assert 0.2 < end_coords[1] < 0.6, (
        f"Expected Newmarket UK longitude (~0.41), got {end_coords[1]}"
    )


@pytest.mark.asyncio
async def test_geocode_pair_returns_none_when_either_endpoint_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If Open-Meteo can't find either endpoint, _geocode_pair returns None
    so the caller can fall through to the generic stub."""
    from src.tools import route as route_module

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def patched_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(route_module.httpx, "AsyncClient", patched_client)

    result = await route_module._geocode_pair("Atlantis", "El Dorado")
    assert result is None


@pytest.mark.asyncio
async def test_geocode_pair_handles_unique_endpoint_paired_with_ambiguous_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When one endpoint is globally unique (e.g. 'Forges-les-Eaux' — only
    one such place in the world) and the other is ambiguous, joint
    disambiguation still works: the unique endpoint constrains the
    ambiguous one to the same region."""
    from src.tools import route as route_module

    # Forges-les-Eaux: only one such place, in Normandy, France
    forges_candidates = _open_meteo_candidates((49.6133, 1.5350))
    # Beauvais: one in France, one in Quebec
    beauvais_candidates = _open_meteo_candidates(
        (46.0833, -73.0667),  # Beauvais, Quebec (less populous but listed first in test data)
        (49.4297, 2.0809),    # Beauvais, France (the cycling intent)
    )

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(200, json=forges_candidates)
        return httpx.Response(200, json=beauvais_candidates)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def patched_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(route_module.httpx, "AsyncClient", patched_client)

    result = await route_module._geocode_pair("Forges-les-Eaux", "Beauvais")
    assert result is not None
    start_coords, end_coords = result
    # Beauvais should be the French one (much closer to Forges than the
    # Quebec namesake)
    assert 49.0 < end_coords[0] < 50.0, f"Expected Beauvais France, got {end_coords}"
    assert 1.5 < end_coords[1] < 2.5


# ---------------------------------------------------------------------------
# BRouter sanity check — > 2.5× haversine or > 300 km absolute = fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brouter_sanity_check_rejects_egregious_overestimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression — Phase 1.13: when BRouter returns a distance > 2.5× the
    haversine (or > 300 km absolute), _fetch_real_elevation must fall
    back to the haversine estimate. Without this guard, the agent gets
    a nonsense 542 km segment and has to apologise mid-conversation."""
    from src.tools import elevation as elevation_module

    # Set up the patched geocode_pair to return real UK coordinates so
    # the haversine fallback computes a sensible ~40 km estimate.
    async def fake_geocode_pair(
        start: str, end: str
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        # Newmarket UK (52.2455, 0.4108) and Thetford UK (52.4119, 0.7517)
        # — real road distance ~40 km, haversine ~25 km.
        return ((52.2455, 0.4108), (52.4119, 0.7517))

    # And patch BRouter to return the production failure mode: 542 km
    # for a real ~40 km segment.
    async def fake_brouter_segment(
        client: Any, start: Any, end: Any
    ) -> tuple[float, float, float]:
        return (542.0, 100.0, 1800.0)

    from src.tools import route as route_module
    from src.tools import route_real

    monkeypatch.setattr(route_module, "_geocode_pair", fake_geocode_pair)
    monkeypatch.setattr(route_real, "_brouter_segment", fake_brouter_segment)

    output = await elevation_module._fetch_real_elevation("Newmarket", "Thetford")
    assert output is not None

    # The output must NOT carry the 542 km value — sanity check should
    # have routed us through the haversine fallback.
    assert output.distance_km < 100, (
        f"Sanity check failed: BRouter's 542 km leaked through, got "
        f"distance_km={output.distance_km}"
    )
    # Roughly haversine × 1.25 ~= 25 × 1.25 ~= 31 km. Allow a generous range.
    assert 20 < output.distance_km < 50, (
        f"Expected haversine-fallback distance ~31 km, got {output.distance_km}"
    )
    # Notes must flag the haversine fallback so the agent knows to surface it.
    assert output.notes is not None
    assert "great-circle" in output.notes.lower() or "haversine" in output.notes.lower()
    # Elevation is zero in the fallback path — we don't fabricate it.
    assert output.elevation_gain_m == 0


@pytest.mark.asyncio
async def test_brouter_sanity_check_accepts_realistic_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reverse case — a normal BRouter return (within sanity envelope) must
    pass through unchanged. Ensures the sanity check isn't false-positiving
    on legitimate routes."""
    from src.tools import elevation as elevation_module

    async def fake_geocode_pair(
        start: str, end: str
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        # Cambridge UK to Ely UK — real ~30 km, haversine ~25 km.
        return ((52.2053, 0.1218), (52.3993, 0.2625))

    async def fake_brouter_segment(
        client: Any, start: Any, end: Any
    ) -> tuple[float, float, float]:
        # 37 km is realistic (1.5× haversine) — should pass sanity.
        return (37.0, 50.0, 7400.0)

    from src.tools import route as route_module
    from src.tools import route_real

    monkeypatch.setattr(route_module, "_geocode_pair", fake_geocode_pair)
    monkeypatch.setattr(route_real, "_brouter_segment", fake_brouter_segment)

    output = await elevation_module._fetch_real_elevation("Cambridge", "Ely")
    assert output is not None
    # Realistic value passes through.
    assert output.distance_km == 37.0
    assert output.elevation_gain_m == 50
    # NOT a haversine fallback — notes should describe a real BRouter run.
    if output.notes:
        assert "great-circle" not in output.notes.lower()
