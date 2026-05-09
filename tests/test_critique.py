"""Tests for the critique_trip_plan tool.

Critique is deterministic Python — these tests don't need network or DB,
just the registered tool. Each test exercises one rule path in isolation,
so a regression points straight at the offending check.
"""

from __future__ import annotations

import pytest

import src.tools  # noqa: F401 — register tools
from src.tools import dispatch
from src.tools.schemas import CritiqueTripPlanOutput


def _make_day(
    day_number: int,
    distance_km: float = 100,
    elevation_gain_m: int = 200,
    difficulty: str = "easy",
    accommodation_type: str | None = "camping",
    has_ferry: bool = False,
) -> dict:
    return {
        "day_number": day_number,
        "distance_km": distance_km,
        "elevation_gain_m": elevation_gain_m,
        "difficulty": difficulty,
        "accommodation_type": accommodation_type,
        "has_ferry": has_ferry,
    }


# ---------------------------------------------------------------------------
# Happy path — well-balanced plan should ship clean
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critique_clean_plan_ships() -> None:
    """4-day camping trip, all days within target, all camping. No issues."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, distance_km=95),
                _make_day(2, distance_km=100),
                _make_day(3, distance_km=105),
                _make_day(4, distance_km=80),
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping",
        },
    )
    assert not result.is_error
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    assert parsed.overall_assessment == "ship_it"
    assert len(parsed.issues) == 0


# ---------------------------------------------------------------------------
# Pacing — over and under
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critique_flags_overlong_day() -> None:
    """Day 4 is 160km when target is 100 — 60% over. Should warn."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, distance_km=100),
                _make_day(2, distance_km=100),
                _make_day(3, distance_km=100),
                _make_day(4, distance_km=160),
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping",
        },
    )
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    pacing_warnings = [i for i in parsed.issues if i.category == "pacing" and i.severity == "warning"]
    assert len(pacing_warnings) == 1
    assert 4 in pacing_warnings[0].affects_days


@pytest.mark.asyncio
async def test_critique_short_day_is_only_info_not_warning() -> None:
    """20km against a 100km target should be info, not blocker — could be a planned short day."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, distance_km=100),
                _make_day(2, distance_km=20),
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping",
        },
    )
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    pacing_infos = [i for i in parsed.issues if i.category == "pacing" and i.severity == "info"]
    assert len(pacing_infos) == 1


@pytest.mark.asyncio
async def test_critique_short_ferry_day_not_flagged_as_short() -> None:
    """A short day that's also a ferry day shouldn't be flagged — ferry shortens it."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, distance_km=100),
                _make_day(2, distance_km=15, has_ferry=True),
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping",
        },
    )
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    pacing_issues = [i for i in parsed.issues if i.category == "pacing"]
    assert len(pacing_issues) == 0


# ---------------------------------------------------------------------------
# Elevation pacing — hard after long, big-gain back-to-back
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critique_flags_hard_day_after_long_day() -> None:
    """Day 2 is 'hard' difficulty, day 1 was 130km — should warn."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, distance_km=130, difficulty="moderate"),
                _make_day(2, distance_km=80, difficulty="hard"),
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping",
        },
    )
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    elev_warnings = [
        i for i in parsed.issues
        if i.category == "elevation_pacing" and i.severity == "warning"
    ]
    assert len(elev_warnings) >= 1
    assert {1, 2}.issubset(set(elev_warnings[0].affects_days))


@pytest.mark.asyncio
async def test_critique_flags_back_to_back_big_climbs() -> None:
    """Two consecutive days >600m gain — should warn."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, distance_km=80, elevation_gain_m=750, difficulty="moderate"),
                _make_day(2, distance_km=80, elevation_gain_m=800, difficulty="moderate"),
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping",
        },
    )
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    big_climb_warnings = [
        i for i in parsed.issues
        if i.category == "elevation_pacing"
        and "gain" in i.message
    ]
    assert len(big_climb_warnings) >= 1


# ---------------------------------------------------------------------------
# Accommodation pattern — "hostel every Nth night"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critique_honored_hostel_every_3_nights_passes() -> None:
    """User wants hostel every 3rd night → days 3, 6 should be hostels.
    If they are, no mismatch flagged."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, accommodation_type="camping"),
                _make_day(2, accommodation_type="camping"),
                _make_day(3, accommodation_type="hostel"),
                _make_day(4, accommodation_type="camping"),
                _make_day(5, accommodation_type="camping"),
                _make_day(6, accommodation_type="hostel"),
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping but a hostel every 3rd night",
        },
    )
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    mismatches = [i for i in parsed.issues if i.category == "accommodation_mismatch"]
    assert len(mismatches) == 0
    assert parsed.overall_assessment == "ship_it"


@pytest.mark.asyncio
async def test_critique_violated_hostel_every_3_nights_warns() -> None:
    """Day 3 should be a hostel per the preference, but it's camping → warn."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, accommodation_type="camping"),
                _make_day(2, accommodation_type="camping"),
                _make_day(3, accommodation_type="camping"),  # ← should be hostel
                _make_day(4, accommodation_type="camping"),
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping but a hostel every 3rd night",
        },
    )
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    mismatches = [i for i in parsed.issues if i.category == "accommodation_mismatch"]
    assert len(mismatches) == 1
    assert 3 in mismatches[0].affects_days


@pytest.mark.asyncio
async def test_critique_camping_only_pref_flags_non_camping() -> None:
    """User said 'camping' (no hostel pattern). A hotel night should be info."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, accommodation_type="camping"),
                _make_day(2, accommodation_type="hotel"),
                _make_day(3, accommodation_type="camping"),
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping",
        },
    )
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    accom_infos = [
        i for i in parsed.issues
        if i.category == "accommodation_mismatch" and i.severity == "info"
    ]
    assert len(accom_infos) == 1
    assert 2 in accom_infos[0].affects_days


# ---------------------------------------------------------------------------
# Consistency — implausible difficulty/elevation combos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critique_flags_hard_with_zero_gain() -> None:
    """80km marked 'hard' with 0m elevation gain is implausible — flag for recheck."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, distance_km=80, elevation_gain_m=0, difficulty="hard"),
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping",
        },
    )
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    consistency = [i for i in parsed.issues if i.category == "consistency"]
    assert len(consistency) == 1


# ---------------------------------------------------------------------------
# Assessment escalation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critique_two_warnings_yields_minor_revisions() -> None:
    """≥2 warnings → minor_revisions assessment."""
    result = await dispatch(
        "critique_trip_plan",
        {
            "days": [
                _make_day(1, distance_km=100),
                _make_day(2, distance_km=170),  # warning #1: pacing
                _make_day(3, distance_km=80, difficulty="hard"),  # warning #2: hard after long
            ],
            "daily_km_target": 100,
            "accommodation_preference": "camping",
        },
    )
    parsed = CritiqueTripPlanOutput.model_validate(result.content)
    warnings = [i for i in parsed.issues if i.severity == "warning"]
    assert len(warnings) >= 2
    assert parsed.overall_assessment in {"minor_revisions", "major_revisions"}


# ---------------------------------------------------------------------------
# Registry — critique is registered + visible to Claude
# ---------------------------------------------------------------------------


def test_critique_registered_with_anthropic_definition() -> None:
    from src.tools import TOOL_REGISTRY, all_anthropic_definitions

    assert "critique_trip_plan" in TOOL_REGISTRY
    defs = {d["name"]: d for d in all_anthropic_definitions()}
    assert "critique_trip_plan" in defs
    schema = defs["critique_trip_plan"]["input_schema"]
    assert "days" in schema["properties"]
    assert "daily_km_target" in schema["properties"]
