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


class DayPlan(BaseModel):
    """Pre-computed daily breakdown for a route variant at the user's daily km
    target. Saves the agent from doing per-day arithmetic and prevents the
    "agent confidently sums 4 numbers wrong" failure mode that LLMs fall into
    even when the underlying data is correct.

    The agent should treat this as the canonical day split for the variant.
    Per-day deeper info (elevation, weather, accommodation) is added by the
    agent on top — it's the SPLIT itself that's pre-computed here.
    """

    day: int = Field(ge=1, description="1-indexed day number")
    from_city: str = Field(description="Name of the overnight stop the day starts from")
    to_city: str = Field(description="Name of the overnight stop the day ends at")
    cycling_km: float = Field(
        ge=0,
        description=(
            "Real cycling distance for the day (excludes ferry time). Computed "
            "by summing segment_km across every waypoint visited on this day, "
            "INCLUDING any pre-ferry leg. Trust this number — don't recompute."
        ),
    )
    has_ferry: bool = Field(
        default=False, description="True if the day includes a ferry crossing"
    )
    waypoints_visited: list[str] = Field(
        default_factory=list,
        description="Ordered city names visited on this day (start city first, end city last)",
    )
    notes: str | None = Field(
        default=None,
        description=(
            "Free-text flag if the day deviates materially from the daily km "
            "target (e.g. 'long day, +25% vs target', 'ferry day, short cycling')"
        ),
    )


class RouteVariant(BaseModel):
    """A single way to cycle the corridor — its own road choice, distance,
    and waypoint chain. Most signposted long-distance routes have multiple
    real variants (e.g. Avenue Verte: V16a Beauvais, Oise/Chantilly, Gisors)
    with different distances and characters.

    The agent's job is to surface 2-3 variants side-by-side and let the
    user choose, rather than picking silently.
    """

    name: str = Field(description="Short identifier, e.g. 'v16a_beauvais'")
    title: str = Field(
        description="Display title for side-by-side comparison, e.g. "
        "'V16a Beauvais — fastest signposted'",
    )
    description: str = Field(description="One-line summary the agent surfaces in the comparison")
    total_distance_km: float = Field(ge=0)
    estimated_days: int = Field(ge=1, description="Total days at the user's daily_km_target")
    waypoints: list[Waypoint] = Field(
        description="Ordered list including start and end. Used for day planning."
    )
    suggested_day_plan: list[DayPlan] = Field(
        default_factory=list,
        description=(
            "Pre-computed balanced day-by-day split at the user's daily_km_target. "
            "The agent SHOULD use this as the canonical breakdown — don't recompute "
            "per-day distances from cumulative km, that's where LLM math errors "
            "creep in. Each DayPlan carries from_city, to_city, cycling_km, "
            "has_ferry, and a deviation note when materially off-target."
        ),
    )
    distinguishing_features: list[str] = Field(
        default_factory=list,
        description="2-4 concrete things that make this variant distinct from the others",
    )
    trade_offs: list[str] = Field(
        default_factory=list,
        description="2-4 honest trade-offs (what you give up by choosing this one)",
    )
    best_for: str = Field(
        description="Who/when this variant fits, e.g. 'targeting the fastest crossing"
        " and prefer modern cities to chateaux'",
    )
    notes: str | None = None
    is_default: bool = Field(
        default=False,
        description="True if this is the variant the agent should default to when the "
        "user expresses no preference (e.g. fastest with widest signposting).",
    )


class GetRouteOutput(BaseModel):
    """Output for get_route — multiple route variants for the corridor.

    For corridors with one catalogued variant (or unknown corridors that
    fall back to the stub), `variants` is length 1. For corridors with
    multiple signposted alternatives, `variants` carries 2-3 entries and
    the agent should present them side-by-side for the user to pick.

    Legacy single-variant fields (`total_distance_km`, `waypoints`, `notes`,
    `estimated_days`) mirror the default variant so older consumers keep
    working without code changes.
    """

    start: str
    end: str
    variants: list[RouteVariant] = Field(
        description="One entry per available variant. Length-1 for single-route corridors.",
    )
    # ── Legacy fields ── populated from the default variant for back-compat ──
    total_distance_km: float = Field(ge=0)
    estimated_days: int = Field(ge=1, description="Total days assuming the daily_km_target")
    waypoints: list[Waypoint] = Field(
        description="Ordered list including start and end. Use to break trip into daily segments.",
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

    name: str = Field(
        description=(
            "Display name of the accommodation (e.g. 'Generator Hamburg', "
            "'Camping Vliegenbos'). Surfaced verbatim in the agent's final "
            "Stay line."
        ),
    )
    type: AccommodationType = Field(
        description=(
            "Accommodation type. Drives both the icon glyph in the ItineraryCard "
            "(tent / bed / building / B&B-house) and the agent's matching against "
            "the cyclist's preferred mix (e.g. 'camping but hostel every 4th night')."
        ),
    )
    location: str = Field(description="City or town the accommodation is in")
    distance_from_location_km: float = Field(
        ge=0, description="Distance from the queried location's center"
    )
    estimated_price_eur_per_night: float = Field(
        ge=0,
        description=(
            "Typical nightly rate in EUR for a solo cyclist. Camping pitches "
            "~€18-30, hostels ~€30-55, hotels ~€80-200 depending on country."
        ),
    )
    bike_friendly: bool = Field(
        default=True, description="True if secure bike storage / repair is available"
    )
    notes: str | None = Field(
        default=None,
        description=(
            "Optional human-readable caveats (e.g. 'reception closes 22:00', "
            "'covered bike shed for free'). Agent should surface these inline "
            "when present — they're the difference between a working stop and "
            "an arriving-too-late surprise."
        ),
    )
    # Rich fields populated by the Google Places real-data path. None on seed
    # data so the agent can tell the difference (and downstream UI can show
    # photos/ratings only when present).
    rating: float | None = Field(
        default=None, ge=0, le=5, description="Aggregate user rating (1-5), None on seed"
    )
    review_count: int | None = Field(
        default=None, ge=0, description="Number of user reviews, None on seed"
    )
    price_level: str | None = Field(
        default=None,
        description="Google price tier — INEXPENSIVE / MODERATE / EXPENSIVE / VERY_EXPENSIVE",
    )
    photo_url: str | None = Field(
        default=None, description="Single-photo URL (Google Places photo endpoint)"
    )
    place_id: str | None = Field(
        default=None, description="Google place_id for deeplinks (e.g. https://maps.google.com/?cid=...)"
    )


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
    accommodation_name: str | None = Field(
        default=None,
        description=(
            "Specific accommodation chosen for the night after riding day_number "
            "(e.g. 'Generator Hamburg'). None if no specific pick yet — critique "
            "will flag this only when the user's preference is an exact type."
        ),
    )
    has_ferry: bool = Field(
        default=False, description="True if this day involves a ferry crossing"
    )
    notes: str | None = Field(
        default=None,
        description=(
            "Optional free-text notes about the day (e.g. 'rest day suggested', "
            "'ferry boards at 14:00'). Critique reads these for flag patterns "
            "but otherwise doesn't enforce structure."
        ),
    )


CritiqueSeverity = Literal["info", "warning", "blocker"]
CritiqueCategory = Literal[
    "pacing",
    "accommodation_mismatch",
    "elevation_pacing",
    "consistency",
    "ferry_missing",
    "constraint_drift",  # plan's daily km avg drifted from user's stated target
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

    name: str = Field(
        description=(
            "Display name of the POI (e.g. 'Brixton Cycles', 'Café Smart' or — "
            "for unnamed public infrastructure — 'Drinking Fountain · Main Square')."
        ),
    )
    category: POICategory = Field(
        description=(
            "POI category — drives the cyclist's mental sorting (a bike_shop "
            "fixes you, a water_fountain refills you, a market feeds you). "
            "Agent should match the category to the user's intent rather than "
            "dumping all categories together."
        ),
    )
    location: str = Field(description="City/town the POI is in")
    distance_from_location_km: float = Field(
        ge=0,
        description=(
            "Walking/cycling distance from the queried location's centre, in km."
        ),
    )
    description: str = Field(description="One-line description for the agent")
    opening_hours: str | None = Field(
        default=None,
        description="Free-text hours (e.g. '9am-6pm Mon-Sat'); None means 24/7 or unknown",
    )
    cyclist_friendly: bool = Field(
        default=True,
        description="True if known to welcome cyclists (bike racks, repair stand, etc.)",
    )
    notes: str | None = Field(
        default=None,
        description=(
            "Optional caveats (e.g. 'closed Mondays', 'cash only', 'no espresso'). "
            "Surface to the cyclist when material to their decision."
        ),
    )
    # Rich fields populated by the Google Places real-data path.
    rating: float | None = Field(
        default=None,
        ge=0,
        le=5,
        description="Aggregate Google rating (1.0-5.0). None on seed data.",
    )
    review_count: int | None = Field(
        default=None,
        ge=0,
        description="Number of Google reviews. None on seed data.",
    )
    photo_url: str | None = Field(
        default=None,
        description="Single Google Places photo URL. None when not available.",
    )
    place_id: str | None = Field(
        default=None,
        description="Google place_id for deeplinks (https://maps.google.com/?cid=…).",
    )


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

    departure_time: str = Field(description="24h local time at the origin port, e.g. '08:00'")
    arrival_time: str = Field(
        description="24h local time at the destination port (may be a different timezone)",
    )
    duration_hours: float = Field(
        gt=0,
        description=(
            "Crossing time excluding boarding. Short hops (Rødby–Puttgarden) "
            "are ~0.75h; channel crossings (Newhaven–Dieppe) are ~4h."
        ),
    )
    operator: str = Field(description="Ferry operator (DFDS, Scandlines, etc.)")
    price_per_cyclist_eur: float = Field(
        ge=0,
        description=(
            "Foot-passenger fare in EUR (cyclists travel as foot passengers — "
            "no separate cyclist tier). Excludes bike."
        ),
    )
    price_per_bike_eur: float = Field(
        default=0, ge=0, description="0 if bikes carried free of charge"
    )
    bike_policy: str = Field(
        description=(
            "Free-text bike-handling rules (e.g. 'walk on, no booking needed', "
            "'wheeled aboard at car deck door, secured to railing')."
        ),
    )
    advance_booking_required: bool = Field(
        default=False,
        description=(
            "True if the operator generally requires booking ahead. Most "
            "North Sea / Channel routes accept walk-on cyclists; some peak-"
            "summer crossings require it."
        ),
    )


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
    operator: str = Field(
        description=(
            "Primary operator on this route (e.g. 'DFDS Seaways', "
            "'Scandlines', 'P&O Ferries'). Some routes have multiple operators "
            "but we surface the dominant one."
        ),
    )
    departures: list[FerryDeparture] = Field(
        description=(
            "Ordered list of typical daily sailings. Surface 2-3 in the agent's "
            "response so the cyclist sees real timing options, not the entire "
            "schedule dump."
        ),
    )
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
