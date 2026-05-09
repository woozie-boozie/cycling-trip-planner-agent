"""Tests for the tool layer.

Tools now query Postgres in production and SQLite in-memory in tests
(thanks to identical SQLModel schema). The `seeded_db` fixture in
conftest.py provisions a fresh SQLite + seeds tool data per test.

Network is never touched.
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
    EstimateBudgetOutput,
    FindAccommodationOutput,
    GetElevationProfileOutput,
    GetFerryScheduleOutput,
    GetPointsOfInterestOutput,
    GetRouteOutput,
    GetWeatherOutput,
)

# ---------------------------------------------------------------------------
# Registry contract — these don't need DB
# ---------------------------------------------------------------------------


def test_all_required_tools_registered() -> None:
    required = {"get_route", "find_accommodation", "get_weather", "get_elevation_profile"}
    assert required.issubset(TOOL_REGISTRY.keys())


def test_anthropic_definitions_well_formed() -> None:
    for d in all_anthropic_definitions():
        assert isinstance(d["name"], str) and d["name"]
        assert isinstance(d["description"], str) and len(d["description"]) > 20
        schema = d["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_error() -> None:
    result = await dispatch("does_not_exist", {})
    assert result.is_error is True
    assert result.content["error"] == "unknown_tool"


@pytest.mark.asyncio
async def test_dispatch_bad_arguments_returns_error() -> None:
    """Invalid args are caught by Pydantic and returned to the agent as data."""
    result = await dispatch("get_route", {"start": "Amsterdam"})  # missing 'end'
    assert result.is_error is True
    assert result.content["error"] == "invalid_arguments"
    assert result.content["tool"] == "get_route"


# ---------------------------------------------------------------------------
# get_route — DB-backed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_route_amsterdam_to_copenhagen(seeded_db: None) -> None:
    result = await dispatch(
        "get_route",
        {"start": "Amsterdam", "end": "Copenhagen", "daily_km_target": 100},
    )
    assert result.is_error is False
    parsed = GetRouteOutput.model_validate(result.content)
    assert parsed.start == "Amsterdam"
    assert parsed.end == "Copenhagen"
    assert 700 < parsed.total_distance_km < 1000
    assert parsed.estimated_days >= 7
    assert any(w.is_ferry_required for w in parsed.waypoints)
    distances = [w.distance_from_start_km for w in parsed.waypoints]
    assert distances == sorted(distances)


@pytest.mark.asyncio
async def test_get_route_estimated_days_scales_with_target(seeded_db: None) -> None:
    fast = await dispatch(
        "get_route", {"start": "Amsterdam", "end": "Copenhagen", "daily_km_target": 200}
    )
    slow = await dispatch(
        "get_route", {"start": "Amsterdam", "end": "Copenhagen", "daily_km_target": 50}
    )
    assert not fast.is_error and not slow.is_error
    assert (
        GetRouteOutput.model_validate(fast.content).estimated_days
        < GetRouteOutput.model_validate(slow.content).estimated_days
    )


@pytest.mark.asyncio
async def test_get_route_unknown_corridor_falls_back_gracefully(seeded_db: None) -> None:
    result = await dispatch("get_route", {"start": "Lisbon", "end": "Helsinki"})
    assert result.is_error is False
    parsed = GetRouteOutput.model_validate(result.content)
    assert parsed.notes is not None
    assert len(parsed.waypoints) == 2  # only start + end


@pytest.mark.asyncio
async def test_get_route_london_to_paris_avenue_verte(seeded_db: None) -> None:
    """London → Paris should follow the Avenue Verte with the Newhaven–Dieppe ferry."""
    result = await dispatch(
        "get_route",
        {"start": "London", "end": "Paris", "daily_km_target": 100},
    )
    assert result.is_error is False
    parsed = GetRouteOutput.model_validate(result.content)
    assert parsed.start == "London"
    assert parsed.end == "Paris"
    assert 350 < parsed.total_distance_km < 420
    waypoint_names = [w.name.lower() for w in parsed.waypoints]
    assert "newhaven" in waypoint_names
    assert "dieppe" in waypoint_names
    ferry_waypoints = [w for w in parsed.waypoints if w.is_ferry_required]
    assert any(w.name == "Dieppe" for w in ferry_waypoints)
    assert parsed.notes is not None
    assert "Newhaven" in parsed.notes or "Dieppe" in parsed.notes


@pytest.mark.asyncio
async def test_get_route_london_to_brighton_short_ride(seeded_db: None) -> None:
    """London → Brighton is a famous one-day classic."""
    result = await dispatch(
        "get_route", {"start": "London", "end": "Brighton", "daily_km_target": 100}
    )
    parsed = GetRouteOutput.model_validate(result.content)
    assert 80 < parsed.total_distance_km < 110
    assert parsed.estimated_days == 1
    assert not any(w.is_ferry_required for w in parsed.waypoints)


# ---------------------------------------------------------------------------
# find_accommodation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_accommodation_returns_known_city_results(seeded_db: None) -> None:
    result = await dispatch("find_accommodation", {"location": "Hamburg"})
    assert not result.is_error
    parsed = FindAccommodationOutput.model_validate(result.content)
    assert parsed.location == "Hamburg"
    assert len(parsed.results) >= 1
    assert all(a.location == "Hamburg" for a in parsed.results)


@pytest.mark.asyncio
async def test_find_accommodation_filters_by_type(seeded_db: None) -> None:
    result = await dispatch(
        "find_accommodation",
        {"location": "Bremen", "types": ["camping"]},
    )
    parsed = FindAccommodationOutput.model_validate(result.content)
    assert all(a.type == "camping" for a in parsed.results)


@pytest.mark.asyncio
async def test_find_accommodation_unknown_location_falls_back(seeded_db: None) -> None:
    result = await dispatch("find_accommodation", {"location": "Some Tiny Village"})
    parsed = FindAccommodationOutput.model_validate(result.content)
    assert len(parsed.results) >= 1
    assert all(a.notes and "Mock data" in a.notes for a in parsed.results)


# ---------------------------------------------------------------------------
# get_weather
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_weather_known_city_month(seeded_db: None) -> None:
    result = await dispatch("get_weather", {"location": "Amsterdam", "month": "June"})
    assert not result.is_error
    parsed = GetWeatherOutput.model_validate(result.content)
    assert parsed.month == "June"
    assert 10 < parsed.avg_temp_celsius < 22


@pytest.mark.asyncio
async def test_get_weather_unknown_location_falls_back(seeded_db: None) -> None:
    result = await dispatch("get_weather", {"location": "Atlantis", "month": "June"})
    parsed = GetWeatherOutput.model_validate(result.content)
    assert parsed.notes is not None
    assert "Mock data" in parsed.notes


@pytest.mark.asyncio
async def test_get_weather_invalid_month_rejected(seeded_db: None) -> None:
    result = await dispatch("get_weather", {"location": "Amsterdam", "month": "Smarch"})
    assert result.is_error is True
    assert result.content["error"] == "invalid_arguments"


# ---------------------------------------------------------------------------
# get_elevation_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_elevation_profile_known_segment(seeded_db: None) -> None:
    result = await dispatch(
        "get_elevation_profile",
        {"start": "Hamburg", "end": "Lübeck"},
    )
    assert not result.is_error
    parsed = GetElevationProfileOutput.model_validate(result.content)
    assert 60 < parsed.distance_km < 90
    assert parsed.difficulty in {"easy", "moderate"}
    assert parsed.elevation_gain_m >= 0


@pytest.mark.asyncio
async def test_get_elevation_reverse_direction_works(seeded_db: None) -> None:
    """Both directions seeded, reverse should swap gain/loss."""
    forward = await dispatch("get_elevation_profile", {"start": "Hamburg", "end": "Lübeck"})
    reverse = await dispatch("get_elevation_profile", {"start": "Lübeck", "end": "Hamburg"})
    f = GetElevationProfileOutput.model_validate(forward.content)
    r = GetElevationProfileOutput.model_validate(reverse.content)
    assert f.elevation_gain_m == r.elevation_loss_m
    assert f.elevation_loss_m == r.elevation_gain_m


@pytest.mark.asyncio
async def test_get_elevation_unknown_segment_falls_back(seeded_db: None) -> None:
    result = await dispatch(
        "get_elevation_profile",
        {"start": "Mars Base Alpha", "end": "Mars Base Beta"},
    )
    parsed = GetElevationProfileOutput.model_validate(result.content)
    assert parsed.notes is not None
    assert "Mock data" in parsed.notes


# ---------------------------------------------------------------------------
# Integration: tools cooperate to plan a leg
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_cooperate_to_plan_one_segment(seeded_db: None) -> None:
    """Smoke test: the agent's expected calling pattern works end-to-end."""
    route_result = await dispatch(
        "get_route",
        {"start": "Amsterdam", "end": "Copenhagen", "daily_km_target": 100},
    )
    route = GetRouteOutput.model_validate(route_result.content)
    assert len(route.waypoints) >= 2

    first, second = route.waypoints[0], route.waypoints[1]

    elev = await dispatch("get_elevation_profile", {"start": first.name, "end": second.name})
    assert not elev.is_error

    weather = await dispatch("get_weather", {"location": second.name, "month": "June"})
    assert not weather.is_error

    accom = await dispatch(
        "find_accommodation",
        {"location": second.name, "types": ["camping", "hostel"]},
    )
    assert not accom.is_error
    assert len(FindAccommodationOutput.model_validate(accom.content).results) >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("get_route", {"start": "Amsterdam", "end": "Copenhagen"}),
        ("find_accommodation", {"location": "Bremen"}),
        ("get_weather", {"location": "Hamburg", "month": "June"}),
        ("get_elevation_profile", {"start": "Bremen", "end": "Hamburg"}),
        ("get_points_of_interest", {"location": "Paris"}),
        ("get_ferry_schedule", {"from_port": "Newhaven", "to_port": "Dieppe"}),
        (
            "estimate_budget",
            {
                "daily_km_target": 80,
                "days": 4,
                "accommodation_mix": {"camping_nights": 2, "hostel_nights": 2},
            },
        ),
    ],
)
async def test_each_tool_output_validates_against_its_schema(
    tool_name: str, args: dict, seeded_db: None
) -> None:
    result = await dispatch(tool_name, args)
    assert not result.is_error
    output_model = TOOL_REGISTRY[tool_name].output_model
    output_model.model_validate(result.content)


# ---------------------------------------------------------------------------
# Phase 2D · 2 — bonus tools: POI / ferry / budget
# ---------------------------------------------------------------------------


def test_phase2d_bonus_tools_registered() -> None:
    """Three new tools must register on import."""
    expected = {"get_points_of_interest", "get_ferry_schedule", "estimate_budget"}
    assert expected.issubset(TOOL_REGISTRY.keys())


# get_points_of_interest -------------------------------------------------------


@pytest.mark.asyncio
async def test_poi_known_city_returns_curated_results() -> None:
    result = await dispatch("get_points_of_interest", {"location": "Paris"})
    assert not result.is_error
    parsed = GetPointsOfInterestOutput.model_validate(result.content)
    assert parsed.location == "Paris"
    assert len(parsed.results) >= 1
    cats = {p.category for p in parsed.results}
    # Paris is curated to cover at least bike + food + safety
    assert "bike_shop" in cats
    assert "hospital" in cats


@pytest.mark.asyncio
async def test_poi_filters_by_category() -> None:
    result = await dispatch(
        "get_points_of_interest",
        {"location": "London", "categories": ["bike_shop"]},
    )
    parsed = GetPointsOfInterestOutput.model_validate(result.content)
    assert all(p.category == "bike_shop" for p in parsed.results)
    assert parsed.categories_searched == ["bike_shop"]


@pytest.mark.asyncio
async def test_poi_unknown_city_falls_back_to_generic() -> None:
    result = await dispatch(
        "get_points_of_interest",
        {"location": "Tiny Hamlet Nowhere"},
    )
    parsed = GetPointsOfInterestOutput.model_validate(result.content)
    assert len(parsed.results) >= 1
    assert all(p.notes and "Mock fallback" in p.notes for p in parsed.results)


@pytest.mark.asyncio
async def test_poi_max_results_caps_output() -> None:
    result = await dispatch(
        "get_points_of_interest",
        {"location": "London", "max_results": 3},
    )
    parsed = GetPointsOfInterestOutput.model_validate(result.content)
    assert len(parsed.results) <= 3


# get_ferry_schedule -----------------------------------------------------------


@pytest.mark.asyncio
async def test_ferry_known_route_newhaven_dieppe() -> None:
    result = await dispatch(
        "get_ferry_schedule",
        {"from_port": "Newhaven", "to_port": "Dieppe", "travel_month": "June"},
    )
    assert not result.is_error
    parsed = GetFerryScheduleOutput.model_validate(result.content)
    assert parsed.operator == "DFDS"
    assert len(parsed.departures) >= 1
    assert all(d.duration_hours > 0 for d in parsed.departures)


@pytest.mark.asyncio
async def test_ferry_known_route_rodby_puttgarden_is_short_and_cheap() -> None:
    result = await dispatch(
        "get_ferry_schedule",
        {"from_port": "Rødby", "to_port": "Puttgarden"},
    )
    parsed = GetFerryScheduleOutput.model_validate(result.content)
    assert parsed.operator == "Scandlines"
    # Scandlines crossing is famously ~45 minutes
    assert all(d.duration_hours <= 1.0 for d in parsed.departures)
    # Bikes carried free on this route
    assert all(d.price_per_bike_eur == 0 for d in parsed.departures)


@pytest.mark.asyncio
async def test_ferry_unknown_route_falls_back() -> None:
    result = await dispatch(
        "get_ferry_schedule",
        {"from_port": "Atlantis", "to_port": "Lemuria"},
    )
    parsed = GetFerryScheduleOutput.model_validate(result.content)
    assert "No precise schedule" in parsed.notes
    assert len(parsed.departures) >= 1


# estimate_budget --------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_basic_4day_camping_trip() -> None:
    result = await dispatch(
        "estimate_budget",
        {
            "daily_km_target": 80,
            "days": 4,
            "accommodation_mix": {"camping_nights": 4},
        },
    )
    assert not result.is_error
    parsed = EstimateBudgetOutput.model_validate(result.content)
    assert len(parsed.daily_breakdown) == 4
    # Calorie target = 1800 + 80*30 = 4200 kcal/day
    assert all(d.daily_calorie_estimate == 4200 for d in parsed.daily_breakdown)
    assert all(d.accommodation_type == "camping" for d in parsed.daily_breakdown)
    # Sanity: contingency is 10% of subtotal
    subtotal = parsed.total_accommodation_eur + parsed.total_food_eur + parsed.total_ferry_eur
    assert abs(parsed.contingency_eur - round(subtotal * 0.10, 2)) < 0.01
    assert parsed.grand_total_eur == round(subtotal + parsed.contingency_eur, 2)


@pytest.mark.asyncio
async def test_budget_country_breakdown_changes_food_cost() -> None:
    """Norway is much pricier than Portugal — food totals should reflect that."""
    norway = await dispatch(
        "estimate_budget",
        {
            "daily_km_target": 80,
            "days": 5,
            "accommodation_mix": {"hostel_nights": 5},
            "country_breakdown": [{"country_code": "NO", "nights": 5}],
        },
    )
    portugal = await dispatch(
        "estimate_budget",
        {
            "daily_km_target": 80,
            "days": 5,
            "accommodation_mix": {"hostel_nights": 5},
            "country_breakdown": [{"country_code": "PT", "nights": 5}],
        },
    )
    assert not norway.is_error and not portugal.is_error
    no_total = EstimateBudgetOutput.model_validate(norway.content).total_food_eur
    pt_total = EstimateBudgetOutput.model_validate(portugal.content).total_food_eur
    assert no_total > pt_total


@pytest.mark.asyncio
async def test_budget_with_ferry_includes_ferry_line_item() -> None:
    result = await dispatch(
        "estimate_budget",
        {
            "daily_km_target": 90,
            "days": 4,
            "accommodation_mix": {"hostel_nights": 4},
            "has_ferry": True,
            "ferry_route": "newhaven-dieppe",
        },
    )
    parsed = EstimateBudgetOutput.model_validate(result.content)
    assert parsed.total_ferry_eur > 0
    # Exactly one day should carry the ferry charge
    ferry_days = [d for d in parsed.daily_breakdown if d.ferry_eur > 0]
    assert len(ferry_days) == 1


@pytest.mark.asyncio
async def test_budget_calorie_scales_with_daily_km() -> None:
    """1800 base + 30 per km — short days < long days."""
    short = await dispatch(
        "estimate_budget",
        {"daily_km_target": 40, "days": 2, "accommodation_mix": {"camping_nights": 2}},
    )
    long_ = await dispatch(
        "estimate_budget",
        {"daily_km_target": 150, "days": 2, "accommodation_mix": {"camping_nights": 2}},
    )
    short_kcal = (
        EstimateBudgetOutput.model_validate(short.content).daily_breakdown[0].daily_calorie_estimate
    )
    long_kcal = (
        EstimateBudgetOutput.model_validate(long_.content).daily_breakdown[0].daily_calorie_estimate
    )
    assert short_kcal == 1800 + 40 * 30
    assert long_kcal == 1800 + 150 * 30


@pytest.mark.asyncio
async def test_budget_invalid_accommodation_mix_rejected_by_pydantic() -> None:
    """Negative nights must fail at the Pydantic boundary, surfaced as data."""
    result = await dispatch(
        "estimate_budget",
        {
            "daily_km_target": 80,
            "days": 4,
            "accommodation_mix": {"camping_nights": -1},
        },
    )
    assert result.is_error is True
    assert result.content["error"] == "invalid_arguments"
