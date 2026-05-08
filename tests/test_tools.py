"""Tests for the tool layer.

We're testing three things:
  1. Each tool's mock data conforms to its declared output schema.
  2. The registry/dispatch contract handles success, missing tool, bad
     arguments, and exceptions in handlers.
  3. The Anthropic tool definitions are well-formed (Claude expects this shape).

Network is never touched. Mock data only.
"""

from __future__ import annotations

import pytest

# Importing src.tools triggers registration of all four tools.
from src.tools import (
    TOOL_REGISTRY,
    all_anthropic_definitions,
    dispatch,
)
from src.tools.schemas import (
    FindAccommodationOutput,
    GetElevationProfileOutput,
    GetRouteOutput,
    GetWeatherOutput,
)

# ---------------------------------------------------------------------------
# Registry contract
# ---------------------------------------------------------------------------


def test_all_required_tools_registered() -> None:
    """The brief mandates these four tools — non-negotiable."""
    required = {"get_route", "find_accommodation", "get_weather", "get_elevation_profile"}
    assert required.issubset(TOOL_REGISTRY.keys())


def test_anthropic_definitions_well_formed() -> None:
    """Each tool definition must have name, description, and a JSON-schema input_schema."""
    for d in all_anthropic_definitions():
        assert isinstance(d["name"], str) and d["name"]
        assert isinstance(d["description"], str) and len(d["description"]) > 20
        schema = d["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema


def test_dispatch_unknown_tool_returns_error() -> None:
    result = dispatch("does_not_exist", {})
    assert result.is_error is True
    assert result.content["error"] == "unknown_tool"


def test_dispatch_bad_arguments_returns_error() -> None:
    """Invalid args are caught by Pydantic and returned to the agent as data."""
    result = dispatch("get_route", {"start": "Amsterdam"})  # missing 'end'
    assert result.is_error is True
    assert result.content["error"] == "invalid_arguments"
    assert result.content["tool"] == "get_route"


# ---------------------------------------------------------------------------
# get_route
# ---------------------------------------------------------------------------


def test_get_route_amsterdam_to_copenhagen() -> None:
    result = dispatch(
        "get_route",
        {"start": "Amsterdam", "end": "Copenhagen", "daily_km_target": 100},
    )
    assert result.is_error is False
    parsed = GetRouteOutput.model_validate(result.content)
    assert parsed.start == "Amsterdam"
    assert parsed.end == "Copenhagen"
    assert 700 < parsed.total_distance_km < 1000
    assert parsed.estimated_days >= 7
    # Ferry must surface — Rødby–Puttgarden is the canonical crossing
    assert any(w.is_ferry_required for w in parsed.waypoints)
    # Waypoint distances must be monotonically non-decreasing from start
    distances = [w.distance_from_start_km for w in parsed.waypoints]
    assert distances == sorted(distances)


def test_get_route_estimated_days_scales_with_target() -> None:
    fast = dispatch("get_route", {"start": "Amsterdam", "end": "Copenhagen", "daily_km_target": 200})
    slow = dispatch("get_route", {"start": "Amsterdam", "end": "Copenhagen", "daily_km_target": 50})
    assert not fast.is_error and not slow.is_error
    assert GetRouteOutput.model_validate(fast.content).estimated_days < GetRouteOutput.model_validate(slow.content).estimated_days


def test_get_route_unknown_corridor_falls_back_gracefully() -> None:
    """The agent should be able to handle off-catalog corridors."""
    result = dispatch("get_route", {"start": "Lisbon", "end": "Helsinki"})
    assert result.is_error is False
    parsed = GetRouteOutput.model_validate(result.content)
    assert parsed.notes is not None
    assert len(parsed.waypoints) == 2  # only start + end


def test_get_route_london_to_paris_avenue_verte() -> None:
    """London → Paris should follow the Avenue Verte with the Newhaven–Dieppe ferry."""
    result = dispatch(
        "get_route",
        {"start": "London", "end": "Paris", "daily_km_target": 100},
    )
    assert result.is_error is False
    parsed = GetRouteOutput.model_validate(result.content)
    assert parsed.start == "London"
    assert parsed.end == "Paris"
    # Avenue Verte is roughly 380km of cycling (ferry distance excluded)
    assert 350 < parsed.total_distance_km < 420
    # Ferry must surface — Newhaven–Dieppe across the Channel
    waypoint_names = [w.name.lower() for w in parsed.waypoints]
    assert "newhaven" in waypoint_names
    assert "dieppe" in waypoint_names
    ferry_waypoints = [w for w in parsed.waypoints if w.is_ferry_required]
    assert any(w.name == "Dieppe" for w in ferry_waypoints)
    # Notes should mention the Newhaven–Dieppe crossing, NOT Rødby–Puttgarden
    assert parsed.notes is not None
    assert "Newhaven" in parsed.notes or "Dieppe" in parsed.notes


def test_get_route_london_to_brighton_short_ride() -> None:
    """London → Brighton is a famous one-day classic."""
    result = dispatch("get_route", {"start": "London", "end": "Brighton", "daily_km_target": 100})
    parsed = GetRouteOutput.model_validate(result.content)
    assert 80 < parsed.total_distance_km < 110
    assert parsed.estimated_days == 1
    assert not any(w.is_ferry_required for w in parsed.waypoints)


# ---------------------------------------------------------------------------
# find_accommodation
# ---------------------------------------------------------------------------


def test_find_accommodation_returns_known_city_results() -> None:
    result = dispatch("find_accommodation", {"location": "Hamburg"})
    assert not result.is_error
    parsed = FindAccommodationOutput.model_validate(result.content)
    assert parsed.location == "Hamburg"
    assert len(parsed.results) >= 1
    assert all(a.location == "Hamburg" for a in parsed.results)


def test_find_accommodation_filters_by_type() -> None:
    result = dispatch(
        "find_accommodation",
        {"location": "Bremen", "types": ["camping"]},
    )
    parsed = FindAccommodationOutput.model_validate(result.content)
    assert all(a.type == "camping" for a in parsed.results)


def test_find_accommodation_unknown_location_falls_back() -> None:
    """Unknown locations get generic stubs with notes — keeps agent moving."""
    result = dispatch("find_accommodation", {"location": "Some Tiny Village"})
    parsed = FindAccommodationOutput.model_validate(result.content)
    assert len(parsed.results) >= 1
    assert all(a.notes and "Mock data" in a.notes for a in parsed.results)


# ---------------------------------------------------------------------------
# get_weather
# ---------------------------------------------------------------------------


def test_get_weather_known_city_month() -> None:
    result = dispatch("get_weather", {"location": "Amsterdam", "month": "June"})
    assert not result.is_error
    parsed = GetWeatherOutput.model_validate(result.content)
    assert parsed.month == "June"
    # Sanity: June in Amsterdam is mild, not tropical and not freezing
    assert 10 < parsed.avg_temp_celsius < 22


def test_get_weather_unknown_location_falls_back() -> None:
    result = dispatch("get_weather", {"location": "Atlantis", "month": "June"})
    parsed = GetWeatherOutput.model_validate(result.content)
    assert parsed.notes is not None
    assert "Mock data" in parsed.notes


def test_get_weather_invalid_month_rejected() -> None:
    """Months are a Literal — bad inputs caught by Pydantic, not at runtime."""
    result = dispatch("get_weather", {"location": "Amsterdam", "month": "Smarch"})
    assert result.is_error is True
    assert result.content["error"] == "invalid_arguments"


# ---------------------------------------------------------------------------
# get_elevation_profile
# ---------------------------------------------------------------------------


def test_get_elevation_profile_known_segment() -> None:
    result = dispatch(
        "get_elevation_profile",
        {"start": "Hamburg", "end": "Lübeck"},
    )
    assert not result.is_error
    parsed = GetElevationProfileOutput.model_validate(result.content)
    # Hamburg→Lübeck is ~75km of gentle rolling moraine
    assert 60 < parsed.distance_km < 90
    assert parsed.difficulty in {"easy", "moderate"}
    assert parsed.elevation_gain_m >= 0


def test_get_elevation_reverse_direction_works() -> None:
    """We auto-mirror reverse segments — gain/loss should swap."""
    forward = dispatch("get_elevation_profile", {"start": "Hamburg", "end": "Lübeck"})
    reverse = dispatch("get_elevation_profile", {"start": "Lübeck", "end": "Hamburg"})
    f = GetElevationProfileOutput.model_validate(forward.content)
    r = GetElevationProfileOutput.model_validate(reverse.content)
    assert f.elevation_gain_m == r.elevation_loss_m
    assert f.elevation_loss_m == r.elevation_gain_m


def test_get_elevation_unknown_segment_falls_back() -> None:
    result = dispatch(
        "get_elevation_profile",
        {"start": "Mars Base Alpha", "end": "Mars Base Beta"},
    )
    parsed = GetElevationProfileOutput.model_validate(result.content)
    assert parsed.notes is not None
    assert "Mock data" in parsed.notes


# ---------------------------------------------------------------------------
# Integration: tools cooperate to plan a leg
# ---------------------------------------------------------------------------


def test_tools_cooperate_to_plan_one_segment() -> None:
    """Smoke test: the agent's expected calling pattern works end-to-end."""
    # 1. Get the route
    route_result = dispatch(
        "get_route",
        {"start": "Amsterdam", "end": "Copenhagen", "daily_km_target": 100},
    )
    route = GetRouteOutput.model_validate(route_result.content)
    assert len(route.waypoints) >= 2

    # 2. For the first segment, get elevation, weather, and accommodation
    first, second = route.waypoints[0], route.waypoints[1]

    elev = dispatch("get_elevation_profile", {"start": first.name, "end": second.name})
    assert not elev.is_error

    weather = dispatch("get_weather", {"location": second.name, "month": "June"})
    assert not weather.is_error

    accom = dispatch(
        "find_accommodation",
        {"location": second.name, "types": ["camping", "hostel"]},
    )
    assert not accom.is_error
    assert len(FindAccommodationOutput.model_validate(accom.content).results) >= 1


@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("get_route", {"start": "Amsterdam", "end": "Copenhagen"}),
        ("find_accommodation", {"location": "Bremen"}),
        ("get_weather", {"location": "Hamburg", "month": "June"}),
        ("get_elevation_profile", {"start": "Bremen", "end": "Hamburg"}),
    ],
)
def test_each_tool_output_validates_against_its_schema(tool_name: str, args: dict) -> None:
    """Belt-and-suspenders: dispatch already validates, but we re-validate
    the JSON-serialized form to catch any mode='json' surprises."""
    result = dispatch(tool_name, args)
    assert not result.is_error
    output_model = TOOL_REGISTRY[tool_name].output_model
    output_model.model_validate(result.content)
