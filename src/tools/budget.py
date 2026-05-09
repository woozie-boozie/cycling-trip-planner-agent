"""estimate_budget — €/day breakdown across accommodation, food, ferries.

Closes a specific user-research item from the May 2026 cyclist interviews:
*"how much fuel do I need to eat the night before"* — i.e. tie the trip to a
calorie target alongside the financial budget.

Numbers are deterministic so the agent (and downstream critique tool) can
reason about them — no LLM in the cost calculation.
"""

from __future__ import annotations

from src.tools.base import register_tool
from src.tools.schemas import (
    AccommodationMix,
    AccommodationType,
    CountryNights,
    DailyBudgetItem,
    EstimateBudgetInput,
    EstimateBudgetOutput,
)

# ---------------------------------------------------------------------------
# Cost references
# ---------------------------------------------------------------------------
#
# Mid-range Western Europe averages, May 2026. Tuned against the seeded
# accommodation prices so the budget tool isn't wildly off from what
# `find_accommodation` would return for a real route.

_NIGHTLY_PRICE_EUR: dict[AccommodationType, float] = {
    "camping": 18.0,  # campsite pitch, includes shower
    "hostel": 38.0,  # dorm bed in a EuroVelo-friendly hostel
    "guesthouse": 78.0,  # B&B / chambres d'hôtes
    "hotel": 110.0,  # mid-tier 3-star
}

# Per-country food cost — base €/day for groceries + one café meal.
# Updated from cyclist forum survey (Cyclo-Camping, May 2026).
_FOOD_EUR_PER_DAY: dict[str, float] = {
    "GB": 28.0,  # United Kingdom — pubs and Tesco
    "FR": 24.0,  # France — boulangerie + supermarché
    "BE": 25.0,  # Belgium
    "NL": 26.0,  # Netherlands
    "DE": 22.0,  # Germany — cheap supermarkets
    "DK": 32.0,  # Denmark — expensive
    "SE": 30.0,  # Sweden
    "NO": 38.0,  # Norway — eye-watering
    "CH": 36.0,  # Switzerland
    "AT": 24.0,  # Austria
    "IT": 24.0,  # Italy
    "ES": 22.0,  # Spain
    "PT": 20.0,  # Portugal
    "IE": 28.0,  # Ireland
}
_FOOD_EUR_PER_DAY_DEFAULT = 25.0

# Realistic ferry costs (cyclist + bike, one-way) sampled May 2026.
_FERRY_PRICE_EUR: dict[str, float] = {
    "newhaven-dieppe": 65.0,  # DFDS, ~4h
    "dover-calais": 45.0,  # P&O / DFDS, ~1.5h
    "rodby-puttgarden": 25.0,  # Scandlines, ~45min
    "harwich-hook of holland": 70.0,
}
_FERRY_PRICE_EUR_DEFAULT = 50.0

# Calorie model: 1800 kcal sedentary base + 30 kcal per km cycled (mid-range
# touring intensity, ~150 W average). Calibrated against published
# cycle-touring studies (~2.5–4k kcal/day depending on terrain + weight).
_BASE_CALORIES_PER_DAY = 1800
_CALORIES_PER_KM = 30


def _expand_accommodation_schedule(
    mix: AccommodationMix, days: int
) -> list[AccommodationType | None]:
    """Spread the requested mix across N days in a deterministic order.

    The agent tells us "3 nights camping, 1 hostel, 1 hotel" — we don't try
    to optimise day-by-day; we just round-robin them in a sensible order
    (camping → hostel → guesthouse → hotel) so the daily breakdown is stable.
    A trip is `days` days but only `days` nights of accommodation (we sleep
    after each riding day, including the last).
    """
    schedule: list[AccommodationType | None] = []
    counts: dict[AccommodationType, int] = {
        "camping": mix.camping_nights,
        "hostel": mix.hostel_nights,
        "guesthouse": mix.guesthouse_nights,
        "hotel": mix.hotel_nights,
    }
    order: list[AccommodationType] = ["camping", "hostel", "guesthouse", "hotel"]
    while sum(counts.values()) > 0 and len(schedule) < days:
        for kind in order:
            if counts[kind] > 0 and len(schedule) < days:
                schedule.append(kind)
                counts[kind] -= 1
    while len(schedule) < days:
        schedule.append(None)  # nights not covered by the user's mix
    return schedule[:days]


def _food_eur_for_day(day_index: int, breakdown: list[CountryNights] | None) -> float:
    if not breakdown:
        return _FOOD_EUR_PER_DAY_DEFAULT

    # Walk the country breakdown in order — first country fills the first
    # `nights` slots, second country the next `nights`, etc.
    cursor = 0
    for entry in breakdown:
        if day_index < cursor + entry.nights:
            return _FOOD_EUR_PER_DAY.get(entry.country_code.upper(), _FOOD_EUR_PER_DAY_DEFAULT)
        cursor += entry.nights
    return _FOOD_EUR_PER_DAY_DEFAULT


def _ferry_eur(route_hint: str | None) -> float:
    if route_hint is None:
        return _FERRY_PRICE_EUR_DEFAULT
    return _FERRY_PRICE_EUR.get(route_hint.lower().strip(), _FERRY_PRICE_EUR_DEFAULT)


@register_tool(
    name="estimate_budget",
    description=(
        "Estimate a cycling trip's day-by-day cost and calorie target. Returns "
        "accommodation, food and ferry costs per day, plus a daily kcal estimate "
        "(1800 base + 30 per km cycled). Use after the route is planned and an "
        "accommodation_mix is known — typically once toward the end of the "
        "conversation when the user asks 'how much will this cost' or 'how much "
        "should I eat'. Provide country_breakdown when crossing borders for more "
        "accurate food costs."
    ),
    input_model=EstimateBudgetInput,
    output_model=EstimateBudgetOutput,
)
async def estimate_budget(input: EstimateBudgetInput) -> EstimateBudgetOutput:
    schedule = _expand_accommodation_schedule(input.accommodation_mix, input.days)

    daily: list[DailyBudgetItem] = []
    total_accommodation = 0.0
    total_food = 0.0
    total_ferry = 0.0
    total_kcal = 0

    ferry_eur = _ferry_eur(input.ferry_route) if input.has_ferry else 0.0
    # Charge the ferry to a single mid-trip day so it shows up in the
    # breakdown rather than getting lost in a totals line.
    ferry_day = max(1, input.days // 2) if input.has_ferry else 0

    for i in range(input.days):
        kind = schedule[i]
        accom_eur = _NIGHTLY_PRICE_EUR.get(kind, 0.0) if kind else 0.0
        food_eur = _food_eur_for_day(i, input.country_breakdown)
        kcal = _BASE_CALORIES_PER_DAY + int(input.daily_km_target * _CALORIES_PER_KM)
        ferry_today = ferry_eur if (i + 1) == ferry_day else 0.0

        notes_parts: list[str] = []
        if kind is None:
            notes_parts.append("No accommodation type assigned (mix didn't cover this night)")
        if ferry_today > 0:
            notes_parts.append(f"Ferry crossing on this day (+€{ferry_today:.0f})")

        daily.append(
            DailyBudgetItem(
                day=i + 1,
                accommodation_type=kind,
                accommodation_eur=accom_eur,
                food_eur=food_eur,
                ferry_eur=ferry_today,
                daily_calorie_estimate=kcal,
                notes="; ".join(notes_parts) if notes_parts else None,
            )
        )
        total_accommodation += accom_eur
        total_food += food_eur
        total_ferry += ferry_today
        total_kcal += kcal

    subtotal = total_accommodation + total_food + total_ferry
    contingency = round(subtotal * 0.10, 2)
    grand_total = round(subtotal + contingency, 2)
    avg_per_day = round(grand_total / input.days, 2) if input.days > 0 else 0.0

    notes = (
        f"Mid-range Western Europe May-2026 averages. Calorie estimate uses "
        f"{_BASE_CALORIES_PER_DAY} kcal base + {_CALORIES_PER_KM} kcal/km cycled. "
        "Contingency = 10% of subtotal. Ferry priced from `ferry_route` hint when "
        "given (defaults to €50). Adjust upward for restaurants and downward for "
        "self-catering."
    )

    return EstimateBudgetOutput(
        daily_breakdown=daily,
        total_accommodation_eur=round(total_accommodation, 2),
        total_food_eur=round(total_food, 2),
        total_ferry_eur=round(total_ferry, 2),
        contingency_eur=contingency,
        grand_total_eur=grand_total,
        total_calories=total_kcal,
        average_per_day_eur=avg_per_day,
        notes=notes,
    )
