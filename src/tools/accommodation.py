"""find_accommodation — places to stay near a location.

Mock data is per-city and includes a mix of camping, hostel, hotel, and
guesthouse options with realistic prices and bike-friendliness flags.

The agent uses this to honor preferences like "camping but a hostel every
4th night" — by filtering `types` per segment as it builds the day-by-day
plan.
"""

from __future__ import annotations

from src.tools.base import register_tool
from src.tools.schemas import (
    Accommodation,
    AccommodationType,
    FindAccommodationInput,
    FindAccommodationOutput,
)

# Rough per-city accommodation catalog. Designed to *look* like real listings:
# bike-friendly campings on the outskirts, central hostels, mid-range hotels.
_CATALOG: dict[str, list[Accommodation]] = {
    "amsterdam": [
        Accommodation(
            name="Camping Zeeburg",
            type="camping",
            location="Amsterdam",
            distance_from_location_km=4.5,
            estimated_price_eur_per_night=25,
            bike_friendly=True,
            notes="Direct cycle path into the city center.",
        ),
        Accommodation(
            name="ClinkNOORD Hostel",
            type="hostel",
            location="Amsterdam",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=45,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hotel V Nesplein",
            type="hotel",
            location="Amsterdam",
            distance_from_location_km=0.5,
            estimated_price_eur_per_night=180,
            bike_friendly=True,
        ),
    ],
    "hoorn": [
        Accommodation(
            name="Camping de Kogge",
            type="camping",
            location="Hoorn",
            distance_from_location_km=3.0,
            estimated_price_eur_per_night=22,
            bike_friendly=True,
        ),
        Accommodation(
            name="Stadslogement Oud Hoorn",
            type="guesthouse",
            location="Hoorn",
            distance_from_location_km=0.4,
            estimated_price_eur_per_night=85,
            bike_friendly=True,
        ),
    ],
    "groningen": [
        Accommodation(
            name="Camping Stadspark",
            type="camping",
            location="Groningen",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=20,
            bike_friendly=True,
        ),
        Accommodation(
            name="Simplon Jongerenhotel",
            type="hostel",
            location="Groningen",
            distance_from_location_km=1.5,
            estimated_price_eur_per_night=40,
            bike_friendly=True,
        ),
    ],
    "bremen": [
        Accommodation(
            name="Stadtcamping Bremen",
            type="camping",
            location="Bremen",
            distance_from_location_km=4.0,
            estimated_price_eur_per_night=24,
            bike_friendly=True,
        ),
        Accommodation(
            name="Bremen Hostel",
            type="hostel",
            location="Bremen",
            distance_from_location_km=1.0,
            estimated_price_eur_per_night=38,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hotel Bremer Haus",
            type="hotel",
            location="Bremen",
            distance_from_location_km=0.3,
            estimated_price_eur_per_night=110,
            bike_friendly=True,
        ),
    ],
    "hamburg": [
        Accommodation(
            name="Camping Buchholz",
            type="camping",
            location="Hamburg",
            distance_from_location_km=8.0,
            estimated_price_eur_per_night=28,
            bike_friendly=True,
        ),
        Accommodation(
            name="Generator Hamburg",
            type="hostel",
            location="Hamburg",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=42,
            bike_friendly=True,
            notes="Locked bike room and on-site repair stand.",
        ),
        Accommodation(
            name="25hours Hotel HafenCity",
            type="hotel",
            location="Hamburg",
            distance_from_location_km=1.0,
            estimated_price_eur_per_night=160,
            bike_friendly=True,
        ),
    ],
    "lübeck": [
        Accommodation(
            name="Campingplatz Schönböcken",
            type="camping",
            location="Lübeck",
            distance_from_location_km=4.5,
            estimated_price_eur_per_night=22,
            bike_friendly=True,
        ),
        Accommodation(
            name="Rucksackhotel Backpackers",
            type="hostel",
            location="Lübeck",
            distance_from_location_km=0.8,
            estimated_price_eur_per_night=35,
            bike_friendly=True,
        ),
    ],
    "puttgarden": [
        Accommodation(
            name="Camping Wulfener Hals",
            type="camping",
            location="Puttgarden",
            distance_from_location_km=12.0,
            estimated_price_eur_per_night=26,
            bike_friendly=True,
            notes="Short ride to the ferry terminal.",
        ),
    ],
    "rødby": [
        Accommodation(
            name="Lalandia Camping",
            type="camping",
            location="Rødby",
            distance_from_location_km=5.0,
            estimated_price_eur_per_night=24,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hotel Maribo Søpark",
            type="hotel",
            location="Rødby",
            distance_from_location_km=15.0,
            estimated_price_eur_per_night=120,
            bike_friendly=True,
        ),
    ],
    "vordingborg": [
        Accommodation(
            name="Vordingborg Camping",
            type="camping",
            location="Vordingborg",
            distance_from_location_km=2.0,
            estimated_price_eur_per_night=22,
            bike_friendly=True,
        ),
        Accommodation(
            name="Danhostel Vordingborg",
            type="hostel",
            location="Vordingborg",
            distance_from_location_km=1.0,
            estimated_price_eur_per_night=40,
            bike_friendly=True,
        ),
    ],
    "copenhagen": [
        Accommodation(
            name="Camping Charlottenlund Fort",
            type="camping",
            location="Copenhagen",
            distance_from_location_km=7.0,
            estimated_price_eur_per_night=30,
            bike_friendly=True,
            notes="On the seafront, direct cycle path to the city.",
        ),
        Accommodation(
            name="Generator Copenhagen",
            type="hostel",
            location="Copenhagen",
            distance_from_location_km=1.5,
            estimated_price_eur_per_night=50,
            bike_friendly=True,
        ),
        Accommodation(
            name="Hotel Skt. Petri",
            type="hotel",
            location="Copenhagen",
            distance_from_location_km=0.5,
            estimated_price_eur_per_night=200,
            bike_friendly=True,
        ),
    ],
}


def _normalize(name: str) -> str:
    return name.strip().lower()


def _generic_results(location: str) -> list[Accommodation]:
    """Sensible stub when a location isn't in the catalog. We keep the agent
    moving rather than blowing up."""
    return [
        Accommodation(
            name=f"Generic Campground near {location}",
            type="camping",
            location=location,
            distance_from_location_km=4.0,
            estimated_price_eur_per_night=25,
            bike_friendly=True,
            notes="Mock data — exact listings unavailable for this location.",
        ),
        Accommodation(
            name=f"Generic Hostel in {location}",
            type="hostel",
            location=location,
            distance_from_location_km=1.5,
            estimated_price_eur_per_night=40,
            bike_friendly=True,
            notes="Mock data — exact listings unavailable for this location.",
        ),
    ]


@register_tool(
    name="find_accommodation",
    description=(
        "Find places to stay near a given location, optionally filtered by type "
        "(camping, hostel, hotel, guesthouse). Use after get_route, once per "
        "overnight stop, to honor the cyclist's accommodation preferences "
        "(e.g. 'camping but a hostel every 4th night')."
    ),
    input_model=FindAccommodationInput,
    output_model=FindAccommodationOutput,
)
def find_accommodation(input: FindAccommodationInput) -> FindAccommodationOutput:
    catalog = _CATALOG.get(_normalize(input.location)) or _generic_results(input.location)

    filtered: list[Accommodation]
    if input.types:
        wanted: set[AccommodationType] = set(input.types)
        filtered = [a for a in catalog if a.type in wanted]
        # If the strict filter eliminates everything, fall back to the full
        # catalog with a note in the agent prompt rather than returning empty.
        if not filtered:
            filtered = catalog
    else:
        filtered = catalog

    return FindAccommodationOutput(
        location=input.location,
        results=filtered[: input.max_results],
    )
