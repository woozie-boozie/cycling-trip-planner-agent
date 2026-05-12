"""Tests for the GPX export pipeline.

Mocks ``_brouter_fetch`` so we don't depend on the live BRouter API. The
assertions cover the structural contract callers rely on:

* GPX 1.1 ``<?xml ...?>`` declaration + ``<gpx>`` root
* one ``<trk>`` with one or more ``<trkseg>`` containing ``<trkpt>`` points
* ``<wpt>`` entries for named overnight stops + ferry terminals
* ``Content-Disposition`` filename slugging (kebab-cased corridor/variant)
* per-day mode scopes the track and pins correctly
"""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

import pytest

from src.tools import route_gpx
from src.tools.route_gpx import (
    GPX_MIME,
    _filename,
    _resolve_variant,
    build_gpx_for_variant,
)


@pytest.fixture(autouse=True)
def _patch_brouter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake BRouter — returns synthetic but lat/lon-realistic polylines.

    For each (a, b) anchor pair we emit a 5-point linear interpolation
    between the two anchors. Distance is the haversine × 1.2 (mirrors how
    BRouter compares to great-circle on flat ground). Ascend/time are
    stub-ish — the GPX builder doesn't read them past the cache plumbing.
    """
    import math

    async def fake_fetch(client: Any, a: Any, b: Any) -> tuple[float, float, float, list[list[float]]]:
        # 6378.137 km Earth radius — same constant the real haversine uses
        lat1, lon1 = math.radians(a.lat), math.radians(a.lon)
        lat2, lon2 = math.radians(b.lat), math.radians(b.lon)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        h = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        gc_km = 2 * 6371.0 * math.asin(math.sqrt(h))
        distance_km = gc_km * 1.2
        coords = []
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            coords.append([
                a.lon + (b.lon - a.lon) * t,
                a.lat + (b.lat - a.lat) * t,
                10.0 + t * 5.0,  # synthetic elevation
            ])
        return distance_km, 50.0, 3600.0, coords

    monkeypatch.setattr(route_gpx, "_brouter_fetch", fake_fetch)


@pytest.mark.asyncio
async def test_full_trip_gpx_has_track_and_waypoints() -> None:
    build = await build_gpx_for_variant(
        start="London",
        end="Paris",
        variant_name="v16a_beauvais",
        mode="full",
    )
    assert build is not None

    # Filename is kebab-cased and ends in -full.gpx
    assert build.filename.endswith("-full.gpx")
    assert " " not in build.filename
    assert build.waypoint_count >= 2

    # Parse as XML so we know it's well-formed.
    root = ET.fromstring(build.xml)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    assert root.tag.endswith("gpx")
    tracks = root.findall("g:trk", ns)
    assert len(tracks) == 1
    segs = tracks[0].findall("g:trkseg", ns)
    # Avenue Verte V16a has ~10 overnight stretches; segs should match.
    assert len(segs) >= 3
    total_pts = sum(len(s.findall("g:trkpt", ns)) for s in segs)
    assert total_pts >= len(segs) * 4  # at least 4 pts per stretch

    wpts = root.findall("g:wpt", ns)
    wpt_names = {w.find("g:name", ns).text for w in wpts if w.find("g:name", ns) is not None}
    assert "London" in wpt_names
    assert "Paris" in wpt_names
    # Beauvais is the variant-defining overnight stop — must be a pin.
    assert any("Beauvais" in n for n in wpt_names)


@pytest.mark.asyncio
async def test_day_mode_with_from_to_scopes_to_one_stretch() -> None:
    # Day 1 on V16a Avenue Verte is London → East Grinstead.
    build = await build_gpx_for_variant(
        start="London",
        end="Paris",
        variant_name="v16a_beauvais",
        mode="day",
        day=1,
        from_city="London",
        to_city="East Grinstead",
    )
    assert build is not None
    assert build.filename.endswith("day-1.gpx")

    root = ET.fromstring(build.xml)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    segs = root.findall("g:trk/g:trkseg", ns)
    # One overnight-to-overnight stretch.
    assert len(segs) == 1

    wpt_names = {w.find("g:name", ns).text for w in root.findall("g:wpt", ns)}
    assert "London" in wpt_names
    assert "East Grinstead" in wpt_names
    # Day 1 should not include the destination of the trip.
    assert "Paris" not in wpt_names


@pytest.mark.asyncio
async def test_unknown_corridor_returns_none() -> None:
    build = await build_gpx_for_variant(
        start="Atlantis",
        end="Narnia",
        variant_name=None,
        mode="full",
    )
    assert build is None


@pytest.mark.asyncio
async def test_unknown_variant_returns_none() -> None:
    build = await build_gpx_for_variant(
        start="London",
        end="Paris",
        variant_name="not_a_real_variant",
        mode="full",
    )
    assert build is None


@pytest.mark.asyncio
async def test_day_mode_without_day_or_cities_returns_none() -> None:
    # Caller forgot to scope the day — builder refuses gracefully.
    build = await build_gpx_for_variant(
        start="London",
        end="Paris",
        variant_name="v16a_beauvais",
        mode="day",
    )
    assert build is None


def test_filename_slugs_are_safe() -> None:
    assert _filename("London-Paris", "v16a_beauvais", "full") == (
        "london-paris-v16a-beauvais-full.gpx"
    )
    # → arrow + spaces collapse cleanly
    assert _filename("London → Paris", "oise_chantilly", "day-3") == (
        "london-paris-oise-chantilly-day-3.gpx"
    )


def test_variant_resolution_is_case_insensitive() -> None:
    v = _resolve_variant("LONDON", "paris", "V16a_Beauvais")
    assert v is not None
    assert v.name == "v16a_beauvais"


def test_default_variant_when_name_omitted() -> None:
    v = _resolve_variant("london", "paris", None)
    assert v is not None
    # is_default=True on V16a Beauvais in the catalogue.
    assert v.is_default


def test_gpx_mime_constant() -> None:
    assert GPX_MIME == "application/gpx+xml"
