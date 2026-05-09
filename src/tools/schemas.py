"""Pydantic schemas for tool inputs and outputs.

These are the *single source of truth* for tool typing:

  - Tool implementations consume the Input model
  - Anthropic's `input_schema` is generated from the Input model's JSON schema
  - Tool outputs are validated against the Output model before returning to the agent
  - The agent's system prompt can reference these field names confidently

Keep field names self-documenting (units in the name where ambiguous: `_km`, `_m`,
`_celsius`, etc.) so the agent doesn't need to guess.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

Difficulty = Literal["easy", "moderate", "hard", "extreme"]
AccommodationType = Literal["camping", "hostel", "hotel", "guesthouse"]
Month = Literal[
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


# ---------------------------------------------------------------------------
# get_route
# ---------------------------------------------------------------------------


class Waypoint(BaseModel):
    """A point along a cycling route."""

    name: str = Field(description="City or town name")
    country: str = Field(description="ISO country name")
    distance_from_start_km: float = Field(
        ge=0, description="Cumulative distance from the route's start point in km"
    )
    segment_km: float = Field(
        default=0.0,
        ge=0,
        description=(
            "Cycling distance from the PREVIOUS waypoint to this one. The first "
            "waypoint has segment_km=0. Use this when computing per-day cycling "
            "distances — sum segment_km across all waypoints visited on the day, "
            "including any pre-ferry leg. Avoids the math error of subtracting "
            "cumulative distances and missing legs that share a cumulative value "
            "with a ferry crossing."
        ),
    )
    is_ferry_required: bool = Field(
        default=False,
        description="True if reaching this waypoint requires a ferry (e.g. Rødby–Puttgarden)",
    )


class GetRouteInput(BaseModel):
    """Input for get_route."""

    start: str = Field(description="Starting city, e.g. 'Amsterdam'")
    end: str = Field(description="Destination city, e.g. 'Copenhagen'")
    daily_km_target: float = Field(
        default=80.0,
        gt=0,
        le=300,
        description="Cyclist's target distance per day in km. Used to compute estimated_days.",
    )


class GetRouteOutput(BaseModel):
    """Output for get_route — full route summary plus ordered waypoints."""

    start: str
    end: str
    total_distance_km: float = Field(ge=0)
    estimated_days: int = Field(ge=1, description="Total days assuming the daily_km_target")
    waypoints: list[Waypoint] = Field(
        description="Ordered list including start and end. Use to break trip into daily segments."
    )
    notes: str | None = Field(
        default=None,
        description="Free-text notes the agent should surface to the user (e.g. ferry crossings)",
    )


# ---------------------------------------------------------------------------
# find_accommodation
# ---------------------------------------------------------------------------


class Accommodation(BaseModel):
    """A single place to stay near a location."""

    name: str
    type: AccommodationType
    location: str = Field(description="City or town the accommodation is in")
    distance_from_location_km: float = Field(
        ge=0, description="Distance from the queried location's center"
    )
    estimated_price_eur_per_night: float = Field(ge=0)
    bike_friendly: bool = Field(
        default=True, description="True if secure bike storage / repair is available"
    )
    notes: str | None = None


class FindAccommodationInput(BaseModel):
    """Input for find_accommodation."""

    location: str = Field(description="City or town to find lodging near, e.g. 'Bremen'")
    types: list[AccommodationType] | None = Field(
        default=None,
        description=(
            "Optional filter by accommodation type. If None, returns a mix of all types. "
            "Use ['camping'] to honor a 'camping only' preference."
        ),
    )
    max_results: int = Field(default=5, ge=1, le=20)


class FindAccommodationOutput(BaseModel):
    """Output for find_accommodation — list of nearby places."""

    location: str
    results: list[Accommodation]


# ---------------------------------------------------------------------------
# get_weather
# ---------------------------------------------------------------------------


class GetWeatherInput(BaseModel):
    """Input for get_weather."""

    location: str = Field(description="City or town to get weather for")
    month: Month = Field(description="Month of travel — typical/historical weather is returned")


class GetWeatherOutput(BaseModel):
    """Output for get_weather — historical averages for the given location/month."""

    location: str
    month: Month
    avg_temp_celsius: float
    avg_high_celsius: float
    avg_low_celsius: float
    rain_days_per_month: int = Field(ge=0, le=31)
    avg_rain_mm: float = Field(ge=0)
    notes: str | None = Field(
        default=None,
        description=(
            "Free-text guidance the agent should surface to the user (e.g. prevailing wind, "
            "frequent rain warnings)."
        ),
    )


# ---------------------------------------------------------------------------
# get_elevation_profile
# ---------------------------------------------------------------------------


class GetElevationProfileInput(BaseModel):
    """Input for get_elevation_profile."""

    start: str = Field(description="Segment start city/town")
    end: str = Field(description="Segment end city/town")


class GetElevationProfileOutput(BaseModel):
    """Output for get_elevation_profile — terrain difficulty for a single segment."""

    start: str
    end: str
    distance_km: float = Field(ge=0)
    elevation_gain_m: int = Field(ge=0, description="Total ascent across the segment, in meters")
    elevation_loss_m: int = Field(ge=0, description="Total descent across the segment, in meters")
    max_grade_percent: float = Field(
        ge=0, le=100, description="Steepest gradient encountered as a percentage"
    )
    difficulty: Difficulty
    notes: str | None = None


# ---------------------------------------------------------------------------
# critique_trip_plan — self-critique tool the agent calls before finalizing
# ---------------------------------------------------------------------------


class DraftedDay(BaseModel):
    """A single day in the agent's draft plan, structured for critique.

    Required fields: day_number + distance_km. Everything else is optional but
    informative — the more the agent fills in, the more thorough the critique.
    """

    day_number: int = Field(ge=1)
    distance_km: float = Field(ge=0, description="Distance cycled this day in km")
    elevation_gain_m: int = Field(default=0, ge=0)
    difficulty: Difficulty | None = None
    accommodation_type: AccommodationType | None = Field(
        default=None,
        description="Where the cyclist sleeps THIS NIGHT (after riding day_number)",
    )
    accommodation_name: str | None = None
    has_ferry: bool = Field(
        default=False, description="True if this day involves a ferry crossing"
    )
    notes: str | None = None


CritiqueSeverity = Literal["info", "warning", "blocker"]
CritiqueCategory = Literal[
    "pacing",
    "accommodation_mismatch",
    "elevation_pacing",
    "consistency",
    "ferry_missing",
]


class CritiqueIssue(BaseModel):
    """A single issue surfaced by the critique."""

    severity: CritiqueSeverity
    category: CritiqueCategory
    message: str
    affects_days: list[int] = Field(default_factory=list)
    suggestion: str | None = None


CritiqueAssessment = Literal["ship_it", "minor_revisions", "major_revisions"]


class CritiqueTripPlanInput(BaseModel):
    """Input for critique_trip_plan."""

    days: list[DraftedDay] = Field(min_length=1)
    daily_km_target: float = Field(gt=0, description="The user's stated daily distance target")
    accommodation_preference: str = Field(
        default="any",
        description=(
            "Free-text describing the user's accommodation preference, e.g. "
            "'mostly camping', 'hostel every 3rd night', 'hotels every night'. "
            "The critique parses this for known patterns ('every Nth night', 'camping')."
        ),
    )


class CritiqueTripPlanOutput(BaseModel):
    """Output for critique_trip_plan — issues found + overall assessment.

    Agent uses this to decide whether to ship the plan, surface warnings to
    the user, or revise. `overall_assessment` is the headline:
      - ship_it          → present the plan as-is
      - minor_revisions  → surface the warnings to the user (Heads up section)
      - major_revisions  → revise the plan, optionally re-critique
    """

    issues: list[CritiqueIssue]
    overall_assessment: CritiqueAssessment
    summary: str


# ---------------------------------------------------------------------------
# Phase 2D · bonus tools — POI / budget / ferry (driven by user research)
# ---------------------------------------------------------------------------

# get_points_of_interest --------------------------------------------------------

POICategory = Literal[
    "bike_shop",  # bike repair, parts, rental adjacent
    "bike_rental",  # rentals (e-bikes, road, hybrid)
    "pub",
    "cafe",
    "water_fountain",  # potable water (drinking fountains, springs, refill stations)
    "toilet",  # public toilets / WC
    "hospital",  # for safety reference
    "market",  # supermarket, farmer's market, local-produce stop
    "scenic_viewpoint",  # photo spots, lookouts
]


class POI(BaseModel):
    """A single point of interest near a location."""

    name: str
    category: POICategory
    location: str = Field(description="City/town the POI is in")
    distance_from_location_km: float = Field(ge=0)
    description: str = Field(description="One-line description for the agent")
    opening_hours: str | None = Field(
        default=None,
        description="Free-text hours (e.g. '9am-6pm Mon-Sat'); None means 24/7 or unknown",
    )
    cyclist_friendly: bool = Field(
        default=True,
        description="True if known to welcome cyclists (bike racks, repair stand, etc.)",
    )
    notes: str | None = None


class GetPointsOfInterestInput(BaseModel):
    """Input for get_points_of_interest."""

    location: str = Field(description="City or town to search around, e.g. 'Bremen'")
    categories: list[POICategory] | None = Field(
        default=None,
        description=(
            "Optional category filter. Common cyclist queries: ['bike_shop'] for "
            "repairs, ['water_fountain', 'toilet'] for fueling stops, ['pub', 'market'] "
            "for food and drink. If None, returns a mix across all categories."
        ),
    )
    max_results: int = Field(default=8, ge=1, le=30)


class GetPointsOfInterestOutput(BaseModel):
    """Output for get_points_of_interest."""

    location: str
    categories_searched: list[POICategory]
    results: list[POI]


# get_ferry_schedule -----------------------------------------------------------


class FerryDeparture(BaseModel):
    """A single departure on a ferry route."""

    departure_time: str = Field(description="24h local time, e.g. '08:00'")
    arrival_time: str
    duration_hours: float = Field(gt=0)
    operator: str = Field(description="Ferry operator (DFDS, Scandlines, etc.)")
    price_per_cyclist_eur: float = Field(ge=0)
    price_per_bike_eur: float = Field(
        default=0, ge=0, description="0 if bikes carried free of charge"
    )
    bike_policy: str = Field(description="Free-text bike-handling policy")
    advance_booking_required: bool = Field(default=False)


class GetFerryScheduleInput(BaseModel):
    """Input for get_ferry_schedule."""

    from_port: str = Field(description="Departure port, e.g. 'Newhaven'")
    to_port: str = Field(description="Arrival port, e.g. 'Dieppe'")
    travel_month: Month | None = Field(
        default=None,
        description="Optional month context; June schedules differ from January for some routes",
    )


class GetFerryScheduleOutput(BaseModel):
    """Output for get_ferry_schedule — typical sailings on the route."""

    from_port: str
    to_port: str
    operator: str
    departures: list[FerryDeparture]
    notes: str = Field(
        description=(
            "Practical notes for cyclists — e.g. 'arrive 30min early', 'book online "
            "for €5 discount', 'foot-passenger desk handles bikes'."
        )
    )


# estimate_budget --------------------------------------------------------------


class AccommodationMix(BaseModel):
    """How many of each accommodation type the cyclist plans to use."""

    camping_nights: int = Field(default=0, ge=0)
    hostel_nights: int = Field(default=0, ge=0)
    hotel_nights: int = Field(default=0, ge=0)
    guesthouse_nights: int = Field(default=0, ge=0)


class CountryNights(BaseModel):
    """Number of nights spent in a country — drives food cost estimates."""

    country_code: str = Field(
        min_length=2,
        max_length=3,
        description="ISO 3166 alpha-2 code: GB, FR, NL, DE, DK, BE, etc.",
    )
    nights: int = Field(ge=0)


class EstimateBudgetInput(BaseModel):
    """Input for estimate_budget."""

    daily_km_target: float = Field(gt=0, le=400)
    days: int = Field(ge=1, le=60)
    accommodation_mix: AccommodationMix
    country_breakdown: list[CountryNights] | None = Field(
        default=None,
        description=(
            "Optional per-country night allocation. If omitted, uses a generic "
            "Western European €25/day food estimate."
        ),
    )
    has_ferry: bool = Field(
        default=False,
        description="If True, includes a generic ferry cost in the breakdown.",
    )
    ferry_route: str | None = Field(
        default=None,
        description=(
            "Optional ferry route hint: 'newhaven-dieppe', 'rodby-puttgarden', "
            "'dover-calais'. Used to pick a realistic ferry price."
        ),
    )


class DailyBudgetItem(BaseModel):
    """Per-day cost + calorie breakdown."""

    day: int = Field(ge=1)
    accommodation_type: AccommodationType | None = None
    accommodation_eur: float = Field(ge=0)
    food_eur: float = Field(ge=0)
    ferry_eur: float = Field(default=0, ge=0)
    daily_calorie_estimate: int = Field(
        ge=0,
        description=(
            "Rough kcal target for the day = base 1800 + daily_km × 30. Useful for "
            "the 'how much fuel do I need the night before' question that came out "
            "of cyclist user research."
        ),
    )
    notes: str | None = None


class EstimateBudgetOutput(BaseModel):
    """Output for estimate_budget."""

    daily_breakdown: list[DailyBudgetItem]
    total_accommodation_eur: float = Field(ge=0)
    total_food_eur: float = Field(ge=0)
    total_ferry_eur: float = Field(ge=0)
    contingency_eur: float = Field(
        ge=0, description="10% buffer for unforeseen costs (repairs, weather diversion)"
    )
    grand_total_eur: float = Field(ge=0)
    total_calories: int = Field(ge=0)
    average_per_day_eur: float = Field(ge=0)
    notes: str = Field(description="Caveats, assumptions, sources")
