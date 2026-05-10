"""get_points_of_interest — bike shops, pubs, water fountains, toilets, etc.

Cyclist user research (May 2026) made it clear that route + accommodation + weather
isn't enough. Real cyclists also need: bike repair, food/drink along the route,
toilets and water fountains, hospitals for safety reference, supermarkets for snacks,
and scenic viewpoints worth stopping for.

Rather than ship one tool per category, this single multi-category POI tool
covers all of them. The agent calls it with `categories=['bike_shop']` for a
puncture-recovery question, `categories=['water_fountain', 'toilet']` for a
fueling-stop question, or no `categories` at all for a city overview.

Mock data per known city, same fallback pattern as `find_accommodation`.
"""

from __future__ import annotations

from src.tools.base import register_tool
from src.tools.places_real import fetch_real_pois, use_real_places
from src.tools.schemas import (
    POI,
    GetPointsOfInterestInput,
    GetPointsOfInterestOutput,
    POICategory,
)

# Per-city catalog of POIs. Designed to *look* like real listings — actual
# bike shops in London, real pubs along the Avenue Verte, etc. Where I
# couldn't verify a specific name I picked plausible names + locations.
#
# Each entry: (name, category, distance_km_from_centre, description, hours, friendly, notes)
_POIRow = tuple[str, POICategory, float, str, str | None, bool, str | None]

_CATALOG: dict[str, list[_POIRow]] = {
    # ---- Avenue Verte corridor (London → Paris) ----------------------------
    "london": [
        (
            "Brixton Cycles",
            "bike_shop",
            5.0,
            "Co-op bike shop, repairs while you wait, knowledgeable on touring builds.",
            "10:00-18:00 Mon-Sat",
            True,
            None,
        ),
        (
            "Cycle Surgery — Holborn",
            "bike_shop",
            1.0,
            "Central London chain. Tools and parts; some repair availability.",
            "09:00-19:00 daily",
            True,
            None,
        ),
        (
            "The Doric Arch",
            "pub",
            0.2,
            "Cyclist-tolerant pub by Euston station — outside seating, bike-rack adjacent.",
            "11:00-23:00 daily",
            True,
            None,
        ),
        (
            "Borough Market",
            "market",
            1.5,
            "London's flagship food market. Local produce, cheese, baked goods, prepared snacks for the road.",
            "10:00-17:00 Mon-Sat",
            True,
            "Closed Sundays.",
        ),
        (
            "Sainsbury's — Holborn",
            "market",
            0.8,
            "24-hour supermarket; useful for a top-up the night before departure.",
            "Open 24h",
            True,
            None,
        ),
        (
            "Embankment Drinking Fountains",
            "water_fountain",
            1.5,
            "Multiple Refill London fountains along Victoria Embankment.",
            None,
            True,
            None,
        ),
        (
            "UCH (University College Hospital)",
            "hospital",
            1.0,
            "Major NHS hospital with A&E.",
            "24h",
            False,
            None,
        ),
        (
            "Trafalgar Square Public Toilets",
            "toilet",
            1.2,
            "Operational public WCs (small charge).",
            "07:00-22:00 daily",
            False,
            None,
        ),
        (
            "Primrose Hill Viewpoint",
            "scenic_viewpoint",
            4.5,
            "Panorama of central London skyline — worth a 10min detour at sunrise.",
            None,
            True,
            None,
        ),
        (
            "Brompton Junction Covent Garden",
            "bike_rental",
            1.3,
            "Bike rental + brand store; folders by the day.",
            "10:00-19:00 daily",
            True,
            None,
        ),
    ],
    "east grinstead": [
        (
            "EG Cycles",
            "bike_shop",
            0.5,
            "Independent bike shop, tubed and stocked. Good for South Downs prep.",
            "09:30-17:30 Tue-Sat",
            True,
            None,
        ),
        (
            "The Crown Inn",
            "pub",
            0.3,
            "Historic coaching inn on the high street — beer garden, food till 21:00.",
            "11:00-23:00 daily",
            True,
            None,
        ),
        (
            "Tesco — East Grinstead",
            "market",
            0.8,
            "Large Tesco for snack and route resupply.",
            "07:00-22:00 daily",
            True,
            None,
        ),
        (
            "East Grinstead Public WC",
            "toilet",
            0.3,
            "By the King Street car park.",
            "08:00-18:00",
            False,
            None,
        ),
        (
            "Standen House Viewpoint",
            "scenic_viewpoint",
            3.0,
            "National Trust property, viewpoint over the Weald.",
            "10:00-17:00 Mar-Oct",
            True,
            None,
        ),
    ],
    "lewes": [
        (
            "Cycle Lewes Co-op",
            "bike_shop",
            0.6,
            "Workshop + new/used parts. Good emergency stop before the Newhaven ferry.",
            "09:00-17:00 Mon-Sat",
            True,
            "Sunday closed.",
        ),
        (
            "The Lewes Arms",
            "pub",
            0.3,
            "Historic pub, Harvey's Brewery on tap, regular folk nights.",
            "12:00-23:00 daily",
            True,
            None,
        ),
        (
            "Lewes Friday Market",
            "market",
            0.4,
            "Weekly farmer's market — Sussex produce, cheeses, breads.",
            "Fri 09:00-14:00",
            True,
            None,
        ),
        (
            "Drinking Fountain — Lewes Castle",
            "water_fountain",
            0.5,
            "Refill point at the castle entrance.",
            None,
            True,
            None,
        ),
        (
            "Lewes Public WC — Westgate",
            "toilet",
            0.3,
            "Standard public WC.",
            "08:00-18:00",
            False,
            None,
        ),
        (
            "Lewes Castle Viewpoint",
            "scenic_viewpoint",
            0.5,
            "Views across the Ouse valley to the South Downs.",
            "10:00-17:00",
            True,
            None,
        ),
    ],
    "newhaven": [
        (
            "Newhaven Cycle Centre",
            "bike_shop",
            0.4,
            "Last-chance bike check before the ferry. Quick spannering and tubes.",
            "09:00-17:00 Mon-Sat",
            True,
            None,
        ),
        (
            "Hope Inn",
            "pub",
            0.5,
            "Harbour pub, food till 21:00, very used to ferry-bound cyclists.",
            "11:00-23:00 daily",
            True,
            None,
        ),
        (
            "Co-op — Newhaven",
            "market",
            0.5,
            "For ferry crossings — pre-pack lunch and snacks.",
            "07:00-22:00 daily",
            True,
            None,
        ),
        (
            "Newhaven Ferry Terminal WC",
            "toilet",
            0.0,
            "Standard ferry-terminal WCs.",
            None,
            False,
            None,
        ),
    ],
    "dieppe": [
        (
            "Cycles Boch",
            "bike_shop",
            0.6,
            "Family-run since 1962. Repairs and second-hand parts.",
            "09:30-12:00 / 14:00-19:00",
            True,
            "Closed Mondays.",
        ),
        (
            "Le Sully",
            "pub",
            0.3,
            "Bar-brasserie near the port. Cyclists welcome, plat du jour ~€14.",
            "10:00-23:00 daily",
            True,
            None,
        ),
        (
            "Café des Tribunaux",
            "cafe",
            0.4,
            "Atmospheric old-Dieppe café — coffee + Norman crêpes.",
            "07:30-19:00 daily",
            True,
            None,
        ),
        (
            "Marché de Dieppe",
            "market",
            0.5,
            "Saturday market — Norman cheese, cider, seafood. World-famous in cycling circles.",
            "Sat 08:00-13:00",
            True,
            None,
        ),
        (
            "Dieppe Hospital — CHU",
            "hospital",
            1.5,
            "Regional hospital with 24h A&E.",
            "24h",
            False,
            None,
        ),
        (
            "Falaises de Dieppe",
            "scenic_viewpoint",
            1.5,
            "White-cliff coastal viewpoint, great photo from the western headland.",
            None,
            True,
            None,
        ),
    ],
    "forges-les-eaux": [
        (
            "Cycles Pays de Bray",
            "bike_shop",
            0.4,
            "Small-town bike shop, mainly Pays-de-Bray locals; fixes and tubes.",
            "09:00-12:00 / 14:00-18:00",
            True,
            "Closed Sundays + Mondays.",
        ),
        (
            "Le Saint-Michel",
            "pub",
            0.4,
            "Bar-tabac. Coffee + lottery + occasional live football.",
            "07:00-22:00 daily",
            True,
            None,
        ),
        (
            "Marché de Forges",
            "market",
            0.3,
            "Thursday market square; fresh produce + small bakery stalls.",
            "Thu 08:00-13:00",
            True,
            None,
        ),
        ("Forges-les-Eaux Public WC", "toilet", 0.3, "Park WCs.", None, False, None),
    ],
    "beauvais": [
        (
            "Cycles Decathlon Beauvais",
            "bike_shop",
            1.5,
            "Big-box but reliable. Wide parts inventory; quick wheel-true and brake service.",
            "09:30-19:30 Mon-Sat",
            True,
            None,
        ),
        (
            "L'Hostellerie St-Vincent",
            "pub",
            0.3,
            "Old-town brasserie — food, beer, atmosphere.",
            "11:30-23:00 daily",
            True,
            None,
        ),
        (
            "Cathédrale Saint-Pierre Café",
            "cafe",
            0.2,
            "Café opposite the world's tallest Gothic choir vault.",
            "08:00-19:00 daily",
            True,
            None,
        ),
        (
            "Marché Beauvais",
            "market",
            0.3,
            "Wednesday + Saturday markets, place Jeanne-Hachette.",
            "Wed/Sat 08:00-13:00",
            True,
            None,
        ),
        (
            "Centre Hospitalier de Beauvais",
            "hospital",
            1.8,
            "Regional hospital, 24h A&E.",
            "24h",
            False,
            None,
        ),
        (
            "Cathédrale Saint-Pierre Viewpoint",
            "scenic_viewpoint",
            0.2,
            "Tallest Gothic cathedral vault in the world — climb the tower for the panorama.",
            "09:00-18:00",
            True,
            None,
        ),
    ],
    "cergy-pontoise": [
        (
            "L'Atelier Vélo Cergy",
            "bike_shop",
            1.0,
            "Repair-focused bike shop; handles touring builds.",
            "10:00-19:00 Tue-Sat",
            True,
            None,
        ),
        (
            "Le Saint-Christophe",
            "cafe",
            0.6,
            "Riverside café/restaurant by the Oise.",
            "08:00-22:00 daily",
            True,
            None,
        ),
        (
            "Carrefour Market — Cergy",
            "market",
            0.7,
            "Mid-size supermarket for the final-day push into Paris.",
            "08:30-21:30 daily",
            True,
            None,
        ),
        (
            "Centre Hospitalier de Pontoise",
            "hospital",
            2.0,
            "Regional hospital with 24h A&E.",
            "24h",
            False,
            None,
        ),
    ],
    "paris": [
        (
            "Cycles Laurent — Bastille",
            "bike_shop",
            1.5,
            "Long-standing Bastille shop. Tubular tires, racing parts, classic touring.",
            "10:00-19:00 Mon-Sat",
            True,
            None,
        ),
        (
            "Café de Flore",
            "cafe",
            1.5,
            "Iconic Saint-Germain café — pricey but a cyclist's victory pause earned.",
            "07:30-01:30 daily",
            True,
            None,
        ),
        (
            "Le Bouillon Pigalle",
            "pub",
            2.5,
            "Affordable French classics, no-reservation; queue-friendly post-ride.",
            "12:00-00:00 daily",
            True,
            None,
        ),
        (
            "Marché Bastille",
            "market",
            1.5,
            "Thursday + Sunday market on Boulevard Richard Lenoir.",
            "Thu/Sun 07:00-14:30",
            True,
            None,
        ),
        (
            "Hôpital de la Pitié-Salpêtrière",
            "hospital",
            2.0,
            "Major Paris hospital with 24h A&E.",
            "24h",
            False,
            None,
        ),
        (
            "Jardin du Luxembourg",
            "scenic_viewpoint",
            1.5,
            "Wind-down stop — green, central, unhurried.",
            "07:30-21:30 daily",
            True,
            None,
        ),
        (
            "Vélib' — Multiple stations",
            "bike_rental",
            0.0,
            "Paris's public bike-share system — pick up at any station.",
            "24h",
            True,
            "App registration required.",
        ),
        (
            "Bois de Boulogne Drinking Fountains",
            "water_fountain",
            8.0,
            "Wallace fountains throughout the park.",
            "Daylight hours",
            True,
            None,
        ),
    ],
    # ---- Amsterdam → Copenhagen corridor ----------------------------------
    "amsterdam": [
        (
            "MacBike",
            "bike_rental",
            0.3,
            "Touristy but reliable — bikes by the day or week, central location.",
            "09:00-17:30 daily",
            True,
            None,
        ),
        (
            "Cycles Roberto",
            "bike_shop",
            1.5,
            "Independent bike shop, repairs and parts; popular with locals.",
            "09:00-18:00 Tue-Sat",
            True,
            None,
        ),
        (
            "Albert Cuyp Markt",
            "market",
            1.8,
            "Famous open-air market, food + bric-a-brac, central.",
            "09:00-17:00 Mon-Sat",
            True,
            None,
        ),
        (
            "De Pijp Bars",
            "pub",
            1.8,
            "Cluster of pubs in the De Pijp neighbourhood.",
            "16:00-01:00 daily",
            True,
            None,
        ),
        (
            "AMC Hospital",
            "hospital",
            8.0,
            "Academisch Medisch Centrum, 24h A&E.",
            "24h",
            False,
            None,
        ),
        (
            "Vondelpark Drinking Fountains",
            "water_fountain",
            1.5,
            "Multiple fountains in Amsterdam's biggest park.",
            "Daylight hours",
            True,
            None,
        ),
    ],
    "bremen": [
        (
            "Veloversum Bremen",
            "bike_shop",
            0.8,
            "Repair-strong shop, friendly with EuroVelo tourers.",
            "10:00-19:00 Mon-Fri",
            True,
            "Closed Sundays.",
        ),
        (
            "Schüttinger Brauhaus",
            "pub",
            0.4,
            "Historic brewpub — food, locally brewed Pils.",
            "11:00-00:00 daily",
            True,
            None,
        ),
        (
            "Bremen Wochenmarkt",
            "market",
            0.5,
            "Fresh-produce market, central square.",
            "Tue/Fri 08:00-14:00",
            True,
            None,
        ),
        (
            "Klinikum Bremen-Mitte",
            "hospital",
            1.5,
            "Central hospital, 24h A&E.",
            "24h",
            False,
            None,
        ),
        (
            "Bremen Stadtmusikanten",
            "scenic_viewpoint",
            0.3,
            "Iconic statue — touristy but the obligatory bike-tour photo.",
            None,
            True,
            None,
        ),
    ],
    "hamburg": [
        (
            "Stadtrad Hamburg",
            "bike_rental",
            0.0,
            "Public bike-share with stations every few blocks.",
            "24h",
            True,
            "App registration required.",
        ),
        (
            "Velo Hamburg",
            "bike_shop",
            1.5,
            "Touring-focused workshop, prepares EuroVelo riders.",
            "09:30-18:30 Mon-Sat",
            True,
            None,
        ),
        (
            "Café Paris",
            "cafe",
            0.5,
            "Tile-walled grand café off Rathausmarkt — coffee + cake.",
            "09:00-23:00 daily",
            True,
            None,
        ),
        (
            "Fischmarkt Altona",
            "market",
            4.0,
            "Sunday-morning fish market, opens absurdly early; cyclists love it.",
            "Sun 05:00-09:30",
            True,
            None,
        ),
        (
            "UKE — Universitätsklinikum",
            "hospital",
            5.0,
            "Major Hamburg hospital, 24h A&E.",
            "24h",
            False,
            None,
        ),
        (
            "Speicherstadt Viewpoint",
            "scenic_viewpoint",
            1.0,
            "UNESCO warehouse district viewpoint, bike-friendly Elbe path.",
            None,
            True,
            None,
        ),
    ],
    "copenhagen": [
        (
            "Baisikeli",
            "bike_rental",
            1.0,
            "Quality rentals; profits fund African bike workshops.",
            "09:00-18:00 daily",
            True,
            None,
        ),
        (
            "Velo Service Copenhagen",
            "bike_shop",
            1.5,
            "Top-rated workshop with 48h turnaround for big jobs.",
            "10:00-18:00 Mon-Fri",
            True,
            "Saturday by appointment.",
        ),
        (
            "Torvehallerne",
            "market",
            1.5,
            "Indoor food market, glass-walled hall — Nordic produce + prepared food.",
            "10:00-19:00 daily",
            True,
            None,
        ),
        (
            "Mikkeller Bar",
            "pub",
            1.2,
            "Famous Danish craft brewery's flagship bar. Cyclist-friendly, bike racks outside.",
            "13:00-01:00 daily",
            True,
            None,
        ),
        (
            "Rigshospitalet",
            "hospital",
            1.5,
            "Denmark's largest hospital, 24h A&E.",
            "24h",
            False,
            None,
        ),
        (
            "Drinking Fountain — Kongens Nytorv",
            "water_fountain",
            1.0,
            "Refill point in the central square.",
            None,
            True,
            None,
        ),
        (
            "The Round Tower (Rundetårn)",
            "scenic_viewpoint",
            1.0,
            "17th-century tower, panoramic view of central Copenhagen.",
            "10:00-18:00 daily",
            True,
            None,
        ),
    ],
    # ---- London → Brighton ------------------------------------------------
    "brighton": [
        (
            "Mickle Bicycle Repair",
            "bike_shop",
            0.5,
            "Indie repair specialist; great for post-Ditchling-Beacon adjustments.",
            "09:00-18:00 Mon-Sat",
            True,
            None,
        ),
        (
            "The Evening Star",
            "pub",
            0.3,
            "Real-ale pub by the station; cyclist-friendly garden.",
            "12:00-23:00 daily",
            True,
            None,
        ),
        (
            "Brighton Open Market",
            "market",
            0.7,
            "Daily covered market; fresh produce + South-Downs cheeses.",
            "09:00-17:00 daily",
            True,
            None,
        ),
        (
            "Royal Sussex County Hospital",
            "hospital",
            1.5,
            "Brighton's main hospital with 24h A&E.",
            "24h",
            False,
            None,
        ),
        (
            "Brighton Pier Drinking Fountain",
            "water_fountain",
            0.5,
            "Refill point at the pier entrance.",
            None,
            True,
            None,
        ),
        (
            "Devil's Dyke Viewpoint",
            "scenic_viewpoint",
            8.0,
            "South Downs ridge with views to the sea — short detour, worth it.",
            None,
            True,
            None,
        ),
    ],
}


def _normalize(name: str) -> str:
    return name.strip().lower()


def _generic_results(location: str) -> list[POI]:
    """Sensible stub when a location isn't in the catalog. Keeps the agent moving."""
    return [
        POI(
            name=f"Local bike shop near {location}",
            category="bike_shop",
            location=location,
            distance_from_location_km=1.0,
            description="Mock data — exact bike shop names aren't in the catalog for this location.",
            cyclist_friendly=True,
            notes="Mock fallback.",
        ),
        POI(
            name=f"Public toilets near {location} centre",
            category="toilet",
            location=location,
            distance_from_location_km=0.3,
            description="Mock data — typical town-centre WC.",
            cyclist_friendly=False,
            notes="Mock fallback.",
        ),
    ]


@register_tool(
    name="get_points_of_interest",
    description=(
        "Find cyclist-relevant points of interest near a location — bike shops "
        "(repairs, rentals), pubs, cafes, water fountains, toilets, hospitals "
        "(safety reference), markets (food + local produce), and scenic viewpoints. "
        "Use when the user asks 'where can I get my bike fixed in X', 'what are "
        "good food stops in Y', 'is there a hospital nearby', etc. Filter via "
        "`categories` for focused queries."
    ),
    input_model=GetPointsOfInterestInput,
    output_model=GetPointsOfInterestOutput,
)
async def get_points_of_interest(input: GetPointsOfInterestInput) -> GetPointsOfInterestOutput:
    # Real-data path: opt-in via USE_REAL_PLACES + GOOGLE_PLACES_API_KEY.
    # If the user filtered to seed-only categories (water_fountain, toilet),
    # fetch_real_pois returns None and we fall through to the seed catalog.
    if use_real_places():
        live = await fetch_real_pois(
            input.location, input.categories, input.max_results
        )
        if live is not None:
            return GetPointsOfInterestOutput(
                location=input.location,
                categories_searched=list(input.categories) if input.categories else [],
                results=live,
            )

    rows = _CATALOG.get(_normalize(input.location))

    pois: list[POI]
    if rows:
        pois = [
            POI(
                name=name,
                category=cat,
                location=input.location,
                distance_from_location_km=dist,
                description=desc,
                opening_hours=hours,
                cyclist_friendly=friendly,
                notes=note,
            )
            for name, cat, dist, desc, hours, friendly, note in rows
        ]
    else:
        pois = _generic_results(input.location)

    if input.categories:
        wanted: set[POICategory] = set(input.categories)
        filtered = [p for p in pois if p.category in wanted]
        # If the strict filter eliminates everything, fall back to the full
        # catalog (better than empty + lets agent surface the gap).
        pois = filtered if filtered else pois

    return GetPointsOfInterestOutput(
        location=input.location,
        categories_searched=list(input.categories) if input.categories else [],
        results=pois[: input.max_results],
    )
