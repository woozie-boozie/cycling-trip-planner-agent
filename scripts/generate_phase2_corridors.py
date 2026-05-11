"""Generate the 20 Phase 2 corridor YAMLs + the TS fragment for corridors.ts.

One-shot: holds the corridor data as structured Python, emits 20 files
to ``data/corridors/`` and a TS append fragment to stdout (for paste
into ``web/lib/corridors.ts``).

Coordinates are approximate (1-decimal-degree precision is fine for the
catalog — the agent's planning uses live BRouter geocoding at runtime).
Waypoint counts are 5-10 per corridor; the agent fills in finer detail
via generic-mode per-segment tool calls if the user wants more granular
overnight stops.

Run:
    python scripts/generate_phase2_corridors.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import yaml

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "corridors"
_TS_OUT = Path(__file__).resolve().parent / "_phase2_corridors_ts_fragment.txt"


# Country name → ISO 2-letter code for the frontend Corridor.country field.
_COUNTRY_ISO: dict[str, str] = {
    "United Kingdom": "UK",
    "France": "FR",
    "Spain": "ES",
    "Portugal": "PT",
    "Italy": "IT",
    "Germany": "DE",
    "Netherlands": "NL",
    "Belgium": "BE",
    "Denmark": "DK",
    "Sweden": "SE",
    "Austria": "AT",
    "Czech Republic": "CZ",
    "Slovakia": "SK",
    "Hungary": "HU",
    "Switzerland": "CH",
    "Poland": "PL",
    "Norway": "NO",
}


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in km between two (lat, lon) points."""
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# The 20 corridors — each is one canonical signposted route (single variant).
# ---------------------------------------------------------------------------
# Schema per corridor:
#   slug, label, start, end, aliases, description,
#   variant_title, variant_tag, variant_features, variant_trade_offs,
#   variant_best_for, anchors[(name, country, lat, lon, ferry?, overnight?)]

_PHASE_2: list[dict[str, object]] = [
    # --- Western Europe / flat / family-friendly ----------------------------
    {
        "slug": "loire-a-velo",
        "label": "Nevers → Saint-Brevin-les-Pins",
        "start": "Nevers",
        "end": "Saint-Brevin-les-Pins",
        "aliases": ["loire", "loire a velo", "loire à vélo", "eurovelo 6 france", "nevers"],
        "description": (
            "Loire à Vélo — the canonical signposted EuroVelo 6 western "
            "segment. ~800 km of mostly flat, dedicated cycle paths along "
            "France's longest river, through vineyards, châteaux country, "
            "and gentle Atlantic-coast finale. The flattest 800 km of any "
            "EV6 segment."
        ),
        "variant_name": "ev6_loire",
        "variant_title": "EuroVelo 6 Loire — the canonical signposted path",
        "variant_tag": "Direct",
        "variant_description": (
            "The fully signposted EuroVelo 6 from Nevers via Sancerre, "
            "Orléans, Blois, Tours, Saumur, Angers and Nantes to the "
            "Atlantic at Saint-Brevin-les-Pins."
        ),
        "variant_features": [
            "Flattest 800 km of any EuroVelo 6 segment",
            "Vineyard + château villages every 30-40 km",
            "Loire river views for ~60% of the ride",
            "Mostly dedicated traffic-free cycle paths",
        ],
        "variant_trade_offs": [
            "Tourist-heavy in July/August around the major châteaux",
            "Some sections traffic-shared near Tours and Nantes",
        ],
        "variant_best_for": (
            "first-time multi-day tourers wanting flat + scenic + signposted"
        ),
        "anchors": [
            ("Nevers", "France", 47.00, 3.16),
            ("Sancerre", "France", 47.33, 2.84),
            ("Orléans", "France", 47.90, 1.91),
            ("Blois", "France", 47.58, 1.34),
            ("Tours", "France", 47.39, 0.69),
            ("Saumur", "France", 47.26, -0.07),
            ("Angers", "France", 47.47, -0.55),
            ("Nantes", "France", 47.22, -1.55),
            ("Saint-Brevin-les-Pins", "France", 47.25, -2.17),
        ],
    },
    {
        "slug": "danube-passau-vienna",
        "label": "Passau → Vienna",
        "start": "Passau",
        "end": "Vienna",
        "aliases": ["danube", "donauradweg", "eurovelo 6 austria", "passau", "vienna"],
        "description": (
            "Donauradweg / EuroVelo 6 — the most popular long-distance "
            "cycling route in Europe. ~330 km along the Danube through "
            "Austria, with Linz, Melk's hilltop monastery, and the "
            "Wachau wine valley en route. Doable in 4-7 days."
        ),
        "variant_name": "donauradweg",
        "variant_title": "Donauradweg — the classic Danube week",
        "variant_tag": "Direct",
        "variant_description": (
            "The signposted Donauradweg from Passau (Bavaria/Austria border) "
            "via Linz, Melk and Krems to Vienna. Mostly traffic-free river "
            "path on both banks, ferry crossings to swap sides as needed."
        ),
        "variant_features": [
            "Most-cycled long-distance route in Europe",
            "Wachau valley UNESCO World Heritage (between Melk and Krems)",
            "Linz, Melk and Krems for hostel density + Austrian beer",
            "Mostly flat, both-bank cycle paths, ferry crossings to swap sides",
        ],
        "variant_trade_offs": [
            "Booked-out accommodation in July/August — reserve ahead",
            "Cruise-boat traffic can spoil the views at popular waypoints",
        ],
        "variant_best_for": (
            "first-time bike-tourers, gravel-shy roadies, or anyone wanting "
            "a stress-free week of European river cycling"
        ),
        "anchors": [
            ("Passau", "Germany", 48.57, 13.46),
            ("Linz", "Austria", 48.31, 14.29),
            ("Melk", "Austria", 48.23, 15.33),
            ("Krems", "Austria", 48.41, 15.61),
            ("Vienna", "Austria", 48.21, 16.37),
        ],
    },
    {
        "slug": "lf-kustroute",
        "label": "Den Helder → Cadzand",
        "start": "Den Helder",
        "end": "Cadzand",
        "aliases": [
            "lf kustroute", "nl coast", "dutch coast", "north sea cycle",
            "den helder", "cadzand",
        ],
        "description": (
            "LF Kustroute — the entire Dutch North Sea coast in one "
            "signposted route. ~570 km of dunes, beaches, and seaside "
            "towns from Den Helder in the north to the Belgian border at "
            "Cadzand. Pure flat, occasional dune climbs, headwinds the "
            "constant companion."
        ),
        "variant_name": "lf_kustroute",
        "variant_title": "LF Kustroute — the full Dutch coast",
        "variant_tag": "Coastal",
        "variant_description": (
            "The fully signposted LF Kustroute (LF1 + LF12) along the "
            "Dutch North Sea coast from the Wadden Sea to the Western "
            "Scheldt — dune paths, beach towns, ferry crossings at the "
            "river deltas."
        ),
        "variant_features": [
            "Dune cycle paths most of the way — traffic-free and scenic",
            "Multiple short ferry crossings at river-mouth deltas",
            "Beach swimming at every overnight stop",
            "Hoek van Holland ferry connects to UK if extending the trip",
        ],
        "variant_trade_offs": [
            "Constant westerly headwinds — plan north-to-south for tailwind",
            "Limited inland alternatives if the coast gets stormy",
            "Tourist crowds in Scheveningen / Zandvoort in July/August",
        ],
        "variant_best_for": (
            "riders who want pure coast + tailwind plans, beach swimmers, "
            "Wadden Sea ecology enthusiasts"
        ),
        "anchors": [
            ("Den Helder", "Netherlands", 52.96, 4.76),
            ("Egmond aan Zee", "Netherlands", 52.62, 4.63),
            ("IJmuiden", "Netherlands", 52.46, 4.61),
            ("Zandvoort", "Netherlands", 52.37, 4.53),
            ("The Hague", "Netherlands", 52.07, 4.30),
            ("Hoek van Holland", "Netherlands", 51.98, 4.13),
            ("Vlissingen", "Netherlands", 51.45, 3.57),
            ("Cadzand", "Netherlands", 51.37, 3.40),
        ],
    },
    {
        "slug": "velodyssee",
        "label": "Roscoff → Hendaye",
        "start": "Roscoff",
        "end": "Hendaye",
        "aliases": [
            "velodyssee", "vélodyssée", "atlantic france", "eurovelo 1",
            "roscoff", "hendaye",
        ],
        "description": (
            "La Vélodyssée — France's longest signposted cycle route. "
            "~1,200 km of Atlantic coast from Brittany to the Spanish "
            "border, EuroVelo 1's French segment. Pine forest paths, "
            "Bordeaux wine country detour, surf towns, Basque coast finish."
        ),
        "variant_name": "velodyssee_full",
        "variant_title": "La Vélodyssée — full Atlantic-coast traverse",
        "variant_tag": "Coastal",
        "variant_description": (
            "The full signposted Vélodyssée from the Brittany ferry port "
            "of Roscoff to the Spanish border at Hendaye. Includes the "
            "Nantes-Brest canal section, the Landes pine forest cycle "
            "paths, and the Basque-country coastal finale."
        ),
        "variant_features": [
            "Longest signposted French cycle route",
            "Landes pine forests — 200 km of dedicated traffic-free paths",
            "Surf towns (Lacanau, Hossegor) for off-bike rest days",
            "Crosses into Spain at Hendaye if extending to San Sebastián",
        ],
        "variant_trade_offs": [
            "12+ days at 100 km/day — significant time commitment",
            "Atlantic-side weather: cool summer evenings, frequent fog",
            "Pine-forest sections can feel monotonous after Day 4",
        ],
        "variant_best_for": (
            "experienced multi-day tourers wanting a flagship French tour, "
            "Basque-coast riders, surfers cycling between breaks"
        ),
        "anchors": [
            ("Roscoff", "France", 48.72, -3.99),
            ("Brest", "France", 48.39, -4.49),
            ("Quimper", "France", 47.99, -4.10),
            ("Nantes", "France", 47.22, -1.55),
            ("La Rochelle", "France", 46.16, -1.15),
            ("Royan", "France", 45.62, -1.03),
            ("Bordeaux", "France", 44.84, -0.58),
            ("Arcachon", "France", 44.66, -1.17),
            ("Hossegor", "France", 43.66, -1.39),
            ("Hendaye", "France", 43.36, -1.78),
        ],
    },
    {
        "slug": "danube-vienna-budapest",
        "label": "Vienna → Budapest",
        "start": "Vienna",
        "end": "Budapest",
        "aliases": [
            "danube east", "donauradweg east", "vienna to budapest",
            "eurovelo 6 hungary",
        ],
        "description": (
            "Donauradweg east — Vienna to Budapest via Bratislava and "
            "Győr. ~330 km, ~5 days, the natural continuation if you've "
            "already done Passau → Vienna. Three capital cities in one "
            "tour, mostly flat, signposted both banks."
        ),
        "variant_name": "donauradweg_east",
        "variant_title": "Donauradweg east — Vienna → Budapest via Bratislava",
        "variant_tag": "Direct",
        "variant_description": (
            "The continuation of EuroVelo 6 east from Vienna through "
            "Slovakia (Bratislava) and Hungary (Győr, Esztergom) to "
            "Budapest. Excellent for week-long ride at 70-80 km/day."
        ),
        "variant_features": [
            "Three capital cities (Vienna, Bratislava, Budapest) in one tour",
            "Esztergom Basilica — one of the largest churches in Europe",
            "Hungarian thermal baths every overnight",
            "Mostly flat both-bank cycle paths",
        ],
        "variant_trade_offs": [
            "Hungarian sections less signposted than Austrian",
            "Currency change at the Slovak/Hungarian borders",
        ],
        "variant_best_for": (
            "riders extending a Passau → Vienna trip, capital-city "
            "collectors, Central European history enthusiasts"
        ),
        "anchors": [
            ("Vienna", "Austria", 48.21, 16.37),
            ("Bratislava", "Slovakia", 48.15, 17.11),
            ("Győr", "Hungary", 47.68, 17.64),
            ("Komárom", "Hungary", 47.74, 18.13),
            ("Esztergom", "Hungary", 47.79, 18.74),
            ("Budapest", "Hungary", 47.50, 19.04),
        ],
    },
    # --- UK / beyond London ---------------------------------------------------
    {
        "slug": "lejog",
        "label": "Land's End → John o' Groats",
        "start": "Land's End",
        "end": "John o' Groats",
        "aliases": [
            "lejog", "lands end to john o groats", "lands end john o'groats",
            "end to end", "uk end-to-end",
        ],
        "description": (
            "LEJOG — the iconic UK end-to-end. ~1,600 km from Cornwall's "
            "south-westernmost point to the north-eastern Scottish tip. "
            "The most famous long-distance cycling challenge in Britain; "
            "every cyclist's bucket-list traverse."
        ),
        "variant_name": "lejog_ncn",
        "variant_title": "LEJOG — the classic NCN-signposted route",
        "variant_tag": "Direct",
        "variant_description": (
            "The most-ridden LEJOG path — NCN 3 from Land's End north "
            "via Exeter, Bristol, Birmingham, Manchester and Carlisle to "
            "Scotland, then NCN 7/1 via Glasgow and Inverness to John "
            "o' Groats. 14-21 days at 80-120 km/day."
        ),
        "variant_features": [
            "The bucket-list British end-to-end traverse",
            "Crosses every climate band the UK has — Cornwall to Caithness",
            "NCN signposting on most segments",
            "Major-city overnight options if you need bike shops mid-trip",
        ],
        "variant_trade_offs": [
            "1,600 km is a serious commitment — average ~14 days at 110 km/day",
            "Some A-road sections are unavoidable in remoter Scottish stretches",
            "Headwind risk on the Scottish leg from west-coast prevailing winds",
        ],
        "variant_best_for": (
            "experienced multi-day tourers; once-in-a-lifetime UK trips; "
            "charity-fundraising rides"
        ),
        "anchors": [
            ("Land's End", "United Kingdom", 50.07, -5.71),
            ("Exeter", "United Kingdom", 50.72, -3.53),
            ("Bristol", "United Kingdom", 51.45, -2.58),
            ("Birmingham", "United Kingdom", 52.49, -1.89),
            ("Manchester", "United Kingdom", 53.48, -2.24),
            ("Carlisle", "United Kingdom", 54.89, -2.94),
            ("Glasgow", "United Kingdom", 55.86, -4.25),
            ("Inverness", "United Kingdom", 57.48, -4.22),
            ("John o' Groats", "United Kingdom", 58.64, -3.07),
        ],
    },
    {
        "slug": "c2c-whitehaven-tynemouth",
        "label": "Whitehaven → Tynemouth",
        "start": "Whitehaven",
        "end": "Tynemouth",
        "aliases": [
            "coast to coast", "c2c", "ncn 7", "ncn 14", "whitehaven",
            "tynemouth", "lake district coast to coast",
        ],
        "description": (
            "Coast to Coast (C2C) — Britain's most-ridden multi-day "
            "challenge. ~225 km from the Irish Sea (Whitehaven) over "
            "the Pennines to the North Sea (Tynemouth). Doable in 3-5 "
            "days, signposted as NCN 7/14."
        ),
        "variant_name": "c2c_classic",
        "variant_title": "C2C classic — Whitehaven to Tynemouth via Penrith",
        "variant_tag": "Direct",
        "variant_description": (
            "The classic NCN 7 + NCN 14 routing from the Cumbrian coast "
            "via Keswick, Penrith and the North Pennines to Newcastle "
            "and Tynemouth. Includes the Hartside climb."
        ),
        "variant_features": [
            "Britain's most-ridden multi-day challenge",
            "Lake District scenery on day 1-2",
            "Hartside Pass — the headline climb (~580 m at the top)",
            "Disused railway paths (Waskerley Way) on the eastern half",
        ],
        "variant_trade_offs": [
            "Hartside climb is a real challenge — not flat",
            "Western Lake District weather can be wet even in summer",
        ],
        "variant_best_for": (
            "intermediate-and-up riders wanting a proper UK challenge in "
            "under a week"
        ),
        "anchors": [
            ("Whitehaven", "United Kingdom", 54.55, -3.59),
            ("Keswick", "United Kingdom", 54.60, -3.13),
            ("Penrith", "United Kingdom", 54.66, -2.75),
            ("Alston", "United Kingdom", 54.81, -2.44),
            ("Consett", "United Kingdom", 54.85, -1.83),
            ("Newcastle upon Tyne", "United Kingdom", 54.97, -1.61),
            ("Tynemouth", "United Kingdom", 55.02, -1.42),
        ],
    },
    {
        "slug": "hebridean-way",
        "label": "Vatersay → Stornoway",
        "start": "Vatersay",
        "end": "Stornoway",
        "aliases": [
            "hebridean way", "outer hebrides", "western isles", "vatersay",
            "stornoway",
        ],
        "description": (
            "Hebridean Way — the Outer Hebrides traverse. ~300 km of "
            "single-track machair-edge roads, ferry crossings between "
            "islands, Atlantic-edge isolation. Often described as "
            "Britain's most beautiful long cycle route."
        ),
        "variant_name": "hebridean_way",
        "variant_title": "Hebridean Way — south-to-north traverse",
        "variant_tag": "Quiet",
        "variant_description": (
            "The signposted Hebridean Way from Vatersay in the south to "
            "Stornoway on Lewis, hopping inter-island ferries along the "
            "way. Plan around ferry schedules — they're the binding "
            "constraint on the trip."
        ),
        "variant_features": [
            "Often-rated UK's most beautiful long-distance cycling route",
            "Machair grasslands + white-shell beaches every overnight",
            "Wildlife: seals, sea eagles, otters — daily sightings",
            "Single-track roads, near-zero traffic outside summer weekends",
        ],
        "variant_trade_offs": [
            "Ferry schedules dictate the daily distance",
            "Atlantic weather — gales possible even in summer",
            "Limited resupply between Lochboisdale and Tarbert",
        ],
        "variant_best_for": (
            "wildlife-focused tourers, photographers, riders wanting genuine "
            "remoteness inside the UK"
        ),
        "anchors": [
            ("Vatersay", "United Kingdom", 56.92, -7.55),
            ("Castlebay", "United Kingdom", 56.96, -7.49),
            ("Eriskay", "United Kingdom", 57.07, -7.30, True, True),  # ferry arrival
            ("Lochboisdale", "United Kingdom", 57.15, -7.31),
            ("Berneray", "United Kingdom", 57.71, -7.18, True, True),  # ferry arrival
            ("Lochmaddy", "United Kingdom", 57.60, -7.16),
            ("Tarbert", "United Kingdom", 57.90, -6.79, True, True),  # ferry from Uig
            ("Stornoway", "United Kingdom", 58.21, -6.39),
        ],
    },
    {
        "slug": "way-of-the-roses",
        "label": "Morecambe → Bridlington",
        "start": "Morecambe",
        "end": "Bridlington",
        "aliases": [
            "way of the roses", "morecambe", "bridlington", "lancashire to yorkshire",
            "sea to sea north", "ncn 69",
        ],
        "description": (
            "Way of the Roses — the 170-mile sea-to-sea across northern "
            "England's two historic rose counties (Lancashire's red, "
            "Yorkshire's white). ~270 km, signposted as NCN 69 + variants, "
            "3-4 days at intermediate pace."
        ),
        "variant_name": "way_of_the_roses",
        "variant_title": "Way of the Roses — west-to-east",
        "variant_tag": "Heritage",
        "variant_description": (
            "The signposted NCN 69 route from Morecambe Bay over the "
            "Yorkshire Dales via Settle, Pateley Bridge and York to "
            "Bridlington on the North Sea coast. Quieter alternative "
            "to the Coast to Coast."
        ),
        "variant_features": [
            "Yorkshire Dales National Park — limestone landscape",
            "Historic York with its walls + Minster as a mid-trip stop",
            "Quieter than the C2C — less famous, less ridden",
            "Sea-to-sea structure with photogenic start and finish piers",
        ],
        "variant_trade_offs": [
            "Climbing through the Dales — not flat",
            "Pateley Bridge to Ripon is a single long-day option",
        ],
        "variant_best_for": (
            "Yorkshire Dales aficionados, riders wanting a less-crowded "
            "alternative to the C2C, York heritage stop"
        ),
        "anchors": [
            ("Morecambe", "United Kingdom", 54.07, -2.86),
            ("Settle", "United Kingdom", 54.07, -2.28),
            ("Pateley Bridge", "United Kingdom", 54.09, -1.77),
            ("Ripon", "United Kingdom", 54.14, -1.52),
            ("York", "United Kingdom", 53.96, -1.08),
            ("Pocklington", "United Kingdom", 53.93, -0.78),
            ("Bridlington", "United Kingdom", 54.08, -0.20),
        ],
    },
    # --- Italy / Mediterranean -----------------------------------------------
    {
        "slug": "venice-florence",
        "label": "Venice → Florence",
        "start": "Venice",
        "end": "Florence",
        "aliases": [
            "venice to florence", "venezia firenze", "italy classic",
            "po valley to tuscany",
        ],
        "description": (
            "Venice → Florence — Italy's most heritage-dense corridor. "
            "~370 km via the Po valley flatlands and Apennine foothills. "
            "Padua, Ferrara, Bologna and Pistoia as overnight stops, each "
            "a major UNESCO or near-UNESCO heritage city."
        ),
        "variant_name": "venice_florence_classic",
        "variant_title": "Venice → Florence — Po valley + Apennines",
        "variant_tag": "Heritage",
        "variant_description": (
            "The flat-then-hilly traverse from the Venetian lagoon south "
            "through the Po valley to Bologna, then the Apennine climb "
            "to Florence via Pistoia. Mix of cycle paths and quiet lanes."
        ),
        "variant_features": [
            "Four UNESCO or near-UNESCO cities (Venice, Ferrara, Bologna, Florence)",
            "Po valley pancake-flat first 200 km",
            "Bologna food scene — best gastronomic stop in Italy",
            "Apennine climb to Pistoia (gentle but sustained) as the only real elevation",
        ],
        "variant_trade_offs": [
            "Po valley summer heat brutal in July/August",
            "Bologna → Pistoia involves real climbing",
            "Less signposting than the EuroVelo network",
        ],
        "variant_best_for": (
            "heritage-focused tourers, gastronomes, intermediate-and-up "
            "riders who don't mind one climbing day"
        ),
        "anchors": [
            ("Venice", "Italy", 45.44, 12.32),
            ("Padua", "Italy", 45.41, 11.88),
            ("Ferrara", "Italy", 44.84, 11.62),
            ("Bologna", "Italy", 44.49, 11.34),
            ("Pistoia", "Italy", 43.93, 10.92),
            ("Florence", "Italy", 43.77, 11.25),
        ],
    },
    {
        "slug": "sicily-loop",
        "label": "Palermo → Catania → Palermo",
        "start": "Palermo",
        "end": "Palermo",
        "aliases": [
            "sicily", "sicilia", "palermo loop", "sicilian coast",
            "palermo catania",
        ],
        "description": (
            "Sicily coastal loop — the full island circumnavigation by "
            "bike. ~750 km via Cefalù, Messina, Taormina, Catania, "
            "Syracuse, Ragusa, Agrigento and Trapani back to Palermo. "
            "Mt Etna views, Greek temples, Norman cathedrals — packed."
        ),
        "variant_name": "sicily_coast_loop",
        "variant_title": "Sicily coastal loop — full island circumnavigation",
        "variant_tag": "Scenic",
        "variant_description": (
            "Anti-clockwise from Palermo around Sicily's coast back to "
            "Palermo. Mix of coastal flatlands and short inland climbs "
            "(no proper mountain sections away from Etna)."
        ),
        "variant_features": [
            "Mt Etna views from Catania and Taormina sides",
            "Greek temples at Agrigento (UNESCO Valley of the Temples)",
            "Norman cathedrals (Monreale, Cefalù) bookend the trip",
            "Coastal seafood + Sicilian wine every overnight",
        ],
        "variant_trade_offs": [
            "Summer heat brutal — best ridden April/May or September/October",
            "Coastal traffic on the SS113 stretches",
            "Limited segregated cycle infrastructure",
        ],
        "variant_best_for": (
            "experienced riders wanting a self-contained loop, food + heritage tourists, "
            "shoulder-season Mediterranean lovers"
        ),
        "anchors": [
            ("Palermo", "Italy", 38.12, 13.36),
            ("Cefalù", "Italy", 38.04, 14.02),
            ("Messina", "Italy", 38.19, 15.55),
            ("Taormina", "Italy", 37.85, 15.29),
            ("Catania", "Italy", 37.51, 15.09),
            ("Syracuse", "Italy", 37.07, 15.29),
            ("Ragusa", "Italy", 36.93, 14.73),
            ("Agrigento", "Italy", 37.31, 13.59),
            ("Trapani", "Italy", 38.02, 12.51),
            ("Palermo", "Italy", 38.12, 13.36),
        ],
    },
    {
        "slug": "costa-brava",
        "label": "Barcelona → Cap de Creus",
        "start": "Barcelona",
        "end": "Cap de Creus",
        "aliases": [
            "costa brava", "barcelona to cap de creus", "catalan coast",
            "girona coast",
        ],
        "description": (
            "Costa Brava — Catalonia's wild coast. ~280 km from Barcelona "
            "north along the Mediterranean via Tossa de Mar, Palamós and "
            "Cadaqués to the rocky finale at Cap de Creus. Mix of beach "
            "towns and Dalí country."
        ),
        "variant_name": "costa_brava_coast",
        "variant_title": "Costa Brava coast — Barcelona to Cap de Creus",
        "variant_tag": "Coastal",
        "variant_description": (
            "Coastal route from Barcelona via the Maresme then Tossa, "
            "Palamós, L'Escala and Cadaqués to Cap de Creus — Europe's "
            "easternmost point of the Iberian peninsula."
        ),
        "variant_features": [
            "Wild Mediterranean coves between Tossa and Palamós",
            "Cadaqués — Dalí's coastal village",
            "Cap de Creus — easternmost point of mainland Spain",
            "Beach swimming + tapas + Catalan wine every overnight",
        ],
        "variant_trade_offs": [
            "Coastal road traffic between Barcelona and Blanes",
            "July/August tourist density, especially around Tossa",
            "Final 30 km to Cap de Creus has serious short climbs",
        ],
        "variant_best_for": (
            "Mediterranean lovers, Dalí enthusiasts, riders wanting a short "
            "5-day coastal trip with a dramatic finish"
        ),
        "anchors": [
            ("Barcelona", "Spain", 41.39, 2.17),
            ("Mataró", "Spain", 41.54, 2.44),
            ("Blanes", "Spain", 41.67, 2.79),
            ("Tossa de Mar", "Spain", 41.72, 2.93),
            ("Palamós", "Spain", 41.85, 3.13),
            ("L'Escala", "Spain", 42.12, 3.13),
            ("Cadaqués", "Spain", 42.29, 3.28),
            ("Cap de Creus", "Spain", 42.32, 3.32),
        ],
    },
    # --- Iberia ---------------------------------------------------------------
    {
        "slug": "camino-del-norte",
        "label": "Irún → Santiago de Compostela",
        "start": "Irún",
        "end": "Santiago de Compostela",
        "aliases": [
            "camino del norte", "northern way", "north camino",
            "irun to santiago", "basque coast", "asturias coast",
        ],
        "description": (
            "Camino del Norte — the northern Camino de Santiago, "
            "rideable as a cycle pilgrimage. ~825 km along Spain's "
            "Atlantic coast through Basque country, Cantabria, Asturias "
            "and Galicia. The greener, hillier alternative to the Camino "
            "Francés."
        ),
        "variant_name": "camino_norte_cycle",
        "variant_title": "Camino del Norte — Atlantic-coast pilgrimage by bike",
        "variant_tag": "Scenic",
        "variant_description": (
            "The cycleable variant of the Northern Camino from Irún at "
            "the French border to Santiago de Compostela. Follows the "
            "Bay of Biscay coast, then turns inland through Galicia."
        ),
        "variant_features": [
            "Atlantic-coast scenery vs the dry meseta of the Camino Francés",
            "Pilgrim infrastructure — albergues every 25-40 km, cyclist-priced",
            "Basque + Asturian + Galician food regions in one trip",
            "Compostela certificate at journey's end (200 km minimum by bike)",
        ],
        "variant_trade_offs": [
            "Hillier than the Francés — Asturias has real climbing days",
            "Rainier than the Francés — Atlantic coast weather",
            "Less waymarking than the Francés in places",
        ],
        "variant_best_for": (
            "pilgrim-cyclists wanting the scenic alternative; Atlantic + green "
            "Spain enthusiasts; experienced tourers"
        ),
        "anchors": [
            ("Irún", "Spain", 43.34, -1.79),
            ("San Sebastián", "Spain", 43.32, -1.98),
            ("Bilbao", "Spain", 43.26, -2.92),
            ("Santander", "Spain", 43.46, -3.81),
            ("Llanes", "Spain", 43.42, -4.75),
            ("Gijón", "Spain", 43.54, -5.66),
            ("Mondoñedo", "Spain", 43.43, -7.36),
            ("Sobrado", "Spain", 43.04, -8.03),
            ("Santiago de Compostela", "Spain", 42.88, -8.55),
        ],
    },
    {
        "slug": "algarve-coast",
        "label": "Lagos → Tavira",
        "start": "Lagos",
        "end": "Tavira",
        "aliases": ["algarve", "portugal coast", "lagos to tavira", "south portugal"],
        "description": (
            "Algarve coast — Portugal's southern coast end-to-end by "
            "bike. ~100 km of mostly flat coastal cycling from Lagos in "
            "the west to Tavira near the Spanish border. Short trip, big "
            "winter-sun appeal."
        ),
        "variant_name": "algarve_full",
        "variant_title": "Algarve coast — Lagos to Tavira full traverse",
        "variant_tag": "Coastal",
        "variant_description": (
            "The signposted Ecovia do Litoral from Lagos via Portimão, "
            "Albufeira and Faro to Tavira. Mostly flat, cliff-top + "
            "estuary cycling, end-to-end in 2-3 days."
        ),
        "variant_features": [
            "Year-round cyclable — Algarve has the warmest winter in mainland Europe",
            "Cliff-top sections between Lagos and Albufeira",
            "Ria Formosa wetlands UNESCO biosphere reserve",
            "Seafood + Portuguese pasteís every overnight",
        ],
        "variant_trade_offs": [
            "Coastal road can be busy with tourist traffic in summer",
            "Limited inland options if the coast gets crowded",
            "Short trip — only 2-3 days at any reasonable pace",
        ],
        "variant_best_for": (
            "winter tourers, short-break riders, families with older kids "
            "wanting a flat coastal week"
        ),
        "anchors": [
            ("Lagos", "Portugal", 37.10, -8.67),
            ("Portimão", "Portugal", 37.14, -8.54),
            ("Albufeira", "Portugal", 37.09, -8.25),
            ("Faro", "Portugal", 37.02, -7.93),
            ("Olhão", "Portugal", 37.03, -7.84),
            ("Tavira", "Portugal", 37.13, -7.65),
        ],
    },
    # --- Central / Eastern Europe ---------------------------------------------
    {
        "slug": "berlin-copenhagen",
        "label": "Berlin → Copenhagen",
        "start": "Berlin",
        "end": "Copenhagen",
        "aliases": [
            "berlin to copenhagen", "eurovelo 7 north", "rostock to copenhagen",
            "berlin copenhagen",
        ],
        "description": (
            "Berlin → Copenhagen — EuroVelo 7's northern German + Danish "
            "segment. ~700 km via Rostock and the Warnemünde-Gedser "
            "ferry. Flat throughout, both ends being two of Europe's "
            "most cyclist-friendly capitals."
        ),
        "variant_name": "berlin_copenhagen_ev7",
        "variant_title": "Berlin → Copenhagen — EuroVelo 7 + Gedser ferry",
        "variant_tag": "Direct",
        "variant_description": (
            "EuroVelo 7 north from Berlin via Wittstock and Rostock to "
            "Warnemünde, then the Scandlines ferry to Gedser in Denmark, "
            "and on via Vordingborg to Copenhagen."
        ),
        "variant_features": [
            "Two of Europe's most cyclist-friendly capitals as start + end",
            "Pancake-flat throughout — Brandenburg + Mecklenburg lakelands",
            "Warnemünde-Gedser ferry — 1h45m, cyclists ride on/off",
            "Connects the LDN → Berlin route below for a London → Copenhagen super-tour",
        ],
        "variant_trade_offs": [
            "Mecklenburg is sparser than the Avenue Verte — fewer overnight options",
            "Ferry timing constrains the day-2 / day-3 split",
        ],
        "variant_best_for": (
            "Scandinavia-curious cyclists, capital-city collectors, riders "
            "wanting a flat 7-day tour"
        ),
        "anchors": [
            ("Berlin", "Germany", 52.52, 13.40),
            ("Wittstock", "Germany", 53.16, 12.49),
            ("Rostock", "Germany", 54.09, 12.13),
            ("Warnemünde", "Germany", 54.18, 12.08),
            ("Gedser", "Denmark", 54.57, 11.93, True, True),  # ferry arrival
            ("Vordingborg", "Denmark", 55.01, 11.91),
            ("Copenhagen", "Denmark", 55.68, 12.57),
        ],
    },
    {
        "slug": "prague-vienna",
        "label": "Prague → Vienna",
        "start": "Prague",
        "end": "Vienna",
        "aliases": [
            "prague to vienna", "greenways prague vienna", "czech vienna",
            "prague vienna",
        ],
        "description": (
            "Prague → Vienna Greenways — the signposted Czech/Austrian "
            "cycle corridor. ~400 km via Český Krumlov UNESCO town and "
            "the Moravian wine region. 5-6 days at intermediate pace."
        ),
        "variant_name": "prague_vienna_greenways",
        "variant_title": "Prague → Vienna Greenways — UNESCO + Moravian wine",
        "variant_tag": "Heritage",
        "variant_description": (
            "The signposted Greenways route from Prague via Český "
            "Krumlov (UNESCO old town), České Budějovice (Budvar beer), "
            "and the Moravian wine region (Mikulov, Břeclav) into Vienna."
        ),
        "variant_features": [
            "Český Krumlov UNESCO World Heritage town as the mid-trip stop",
            "Moravian wine region — Czech rieslings + small-grower cellars",
            "Pilsner / Budvar / Austrian beer geography in one trip",
            "Czech sections quieter than the more popular Danube",
        ],
        "variant_trade_offs": [
            "Less signposted than the EuroVelos — bring GPX",
            "Some Czech sections traffic-shared on regional roads",
        ],
        "variant_best_for": (
            "Central European heritage tourists, wine + beer cyclists, "
            "riders wanting quieter alternative to the Danube"
        ),
        "anchors": [
            ("Prague", "Czech Republic", 50.08, 14.43),
            ("České Budějovice", "Czech Republic", 48.97, 14.47),
            ("Český Krumlov", "Czech Republic", 48.81, 14.32),
            ("Mikulov", "Czech Republic", 48.81, 16.64),
            ("Břeclav", "Czech Republic", 48.76, 16.88),
            ("Vienna", "Austria", 48.21, 16.37),
        ],
    },
    {
        "slug": "berlin-usedom",
        "label": "Berlin → Usedom",
        "start": "Berlin",
        "end": "Heringsdorf",
        "aliases": [
            "berlin to usedom", "berlin baltic", "usedom", "heringsdorf",
            "berlin-usedom-radweg",
        ],
        "description": (
            "Berlin-Usedom-Radweg — the signposted Berlin-to-Baltic "
            "ride. ~290 km via Prenzlau and Anklam to the island of "
            "Usedom and the seaside town of Heringsdorf. Mostly flat, "
            "lake-and-canal scenery on the inland section."
        ),
        "variant_name": "berlin_usedom_radweg",
        "variant_title": "Berlin-Usedom-Radweg — capital to Baltic beach",
        "variant_tag": "Coastal",
        "variant_description": (
            "The signposted Berlin-Usedom-Radweg from central Berlin "
            "via Brandenburg lakelands and Mecklenburg-Vorpommern to "
            "Usedom island and the Heringsdorf seafront. 4-5 days at "
            "casual pace."
        ),
        "variant_features": [
            "Capital city → Baltic beach in one tour",
            "Brandenburg lakelands — many swimming spots in summer",
            "Usedom Pier (Seebrücke Heringsdorf) — Germany's longest",
            "Connects to the Polish Baltic-coast routes",
        ],
        "variant_trade_offs": [
            "Limited shade — German Plain summer days can be hot + exposed",
            "Anklam → Wolgast section has some traffic-shared B-roads",
        ],
        "variant_best_for": (
            "Berliners wanting a week-long ride to the sea, German "
            "summer tour, family + intermediate level"
        ),
        "anchors": [
            ("Berlin", "Germany", 52.52, 13.40),
            ("Eberswalde", "Germany", 52.83, 13.83),
            ("Prenzlau", "Germany", 53.32, 13.86),
            ("Pasewalk", "Germany", 53.51, 13.99),
            ("Anklam", "Germany", 53.85, 13.69),
            ("Wolgast", "Germany", 54.05, 13.77),
            ("Heringsdorf", "Germany", 53.95, 14.16),
        ],
    },
    # --- Long-distance signature ----------------------------------------------
    {
        "slug": "amsterdam-berlin",
        "label": "Amsterdam → Berlin",
        "start": "Amsterdam",
        "end": "Berlin",
        "aliases": [
            "amsterdam to berlin", "europaradweg", "eurovelo 4 north",
            "amsterdam berlin",
        ],
        "description": (
            "Amsterdam → Berlin — the European capital-to-capital ride. "
            "~580 km via Utrecht, Münster, Hannover and Magdeburg. Mostly "
            "flat, mix of Dutch LF paths and German Radwege. 6-8 days at "
            "intermediate pace."
        ),
        "variant_name": "amsterdam_berlin_classic",
        "variant_title": "Amsterdam → Berlin — Dutch LF + German Radwege",
        "variant_tag": "Direct",
        "variant_description": (
            "The mostly-signposted capital-to-capital route from "
            "Amsterdam via Utrecht and Arnhem into Germany, then through "
            "Münster, Hannover, Magdeburg to Berlin. Mix of dedicated "
            "cycle paths and quiet country roads."
        ),
        "variant_features": [
            "Two of Europe's flagship cycling capitals as start + end",
            "Münsterland — Germany's most-cycled rural region",
            "Magdeburg + Hannover for mid-trip bike-shop density",
            "Mostly flat throughout — no real climbs",
        ],
        "variant_trade_offs": [
            "Signposting varies — Dutch LF excellent, German Radwege patchier",
            "580 km in a week is steady going — not a holiday pace",
        ],
        "variant_best_for": (
            "European capital-collectors, riders extending a Berlin tour "
            "west into NL, week-long intermediate tourers"
        ),
        "anchors": [
            ("Amsterdam", "Netherlands", 52.37, 4.90),
            ("Utrecht", "Netherlands", 52.09, 5.12),
            ("Arnhem", "Netherlands", 51.98, 5.91),
            ("Münster", "Germany", 51.96, 7.63),
            ("Osnabrück", "Germany", 52.28, 8.05),
            ("Hannover", "Germany", 52.37, 9.74),
            ("Magdeburg", "Germany", 52.13, 11.63),
            ("Berlin", "Germany", 52.52, 13.40),
        ],
    },
    {
        "slug": "paris-lyon",
        "label": "Paris → Lyon",
        "start": "Paris",
        "end": "Lyon",
        "aliases": [
            "paris to lyon", "bourgogne canal", "via fluvia", "paris lyon",
            "burgundy bike",
        ],
        "description": (
            "Paris → Lyon via the Burgundy canals — France's other "
            "headline corridor. ~500 km via Sens, Auxerre, Dijon and "
            "Beaune. Burgundy wine country, canal towpaths, châteaux, "
            "and gastronomic legend en route."
        ),
        "variant_name": "paris_lyon_bourgogne",
        "variant_title": "Paris → Lyon — via the Burgundy canals",
        "variant_tag": "Heritage",
        "variant_description": (
            "Cycling-friendly canal-towpath corridor from Paris via the "
            "Yonne and Burgundy canals to Dijon and the Côte d'Or wine "
            "villages, then south to Mâcon and Lyon. Mostly flat with "
            "vineyard climbs around Beaune."
        ),
        "variant_features": [
            "Burgundy Grand Cru wine villages — Beaune, Pommard, Meursault",
            "Canal towpaths for ~70% of the trip — traffic-free, flat",
            "Dijon mustard + Burgundy beef + Mâcon Chardonnay region",
            "Lyon as a finish — France's gastronomic capital",
        ],
        "variant_trade_offs": [
            "Côte d'Or vineyard sections have real short climbs",
            "Towpath surfaces vary — some unpaved, gravel-bike preferred",
            "Cellar tastings can shorten cycling time considerably",
        ],
        "variant_best_for": (
            "wine + food tourists, gravel-bike riders, week-long "
            "France-deep-cut tours"
        ),
        "anchors": [
            ("Paris", "France", 48.86, 2.35),
            ("Sens", "France", 48.20, 3.28),
            ("Auxerre", "France", 47.80, 3.57),
            ("Dijon", "France", 47.32, 5.04),
            ("Beaune", "France", 47.02, 4.83),
            ("Mâcon", "France", 46.31, 4.83),
            ("Lyon", "France", 45.76, 4.84),
        ],
    },
    {
        "slug": "eurovelo-15-rhine",
        "label": "Andermatt → Hook of Holland",
        "start": "Andermatt",
        "end": "Hook of Holland",
        "aliases": [
            "eurovelo 15", "rhine cycle route", "rheinradweg", "rhine bike",
            "andermatt hook of holland",
        ],
        "description": (
            "EuroVelo 15 — the full Rhine from the Swiss source town of "
            "Andermatt to the North Sea at Hook of Holland. ~1,230 km "
            "through Switzerland, France, Germany and the Netherlands. "
            "One of EuroVelo's signature long-distance corridors."
        ),
        "variant_name": "ev15_rhine_full",
        "variant_title": "EuroVelo 15 Rhine — source-to-sea full traverse",
        "variant_tag": "Scenic",
        "variant_description": (
            "The fully-signposted EuroVelo 15 from the Alps source at "
            "Andermatt down through Basel, Strasbourg, the German Rhine "
            "Gorge UNESCO area, Cologne and Nijmegen to Hook of Holland. "
            "12-14 days at 100 km/day."
        ),
        "variant_features": [
            "Rhine Gorge UNESCO World Heritage section (Mainz → Koblenz)",
            "Four-country traverse with three currency zones",
            "Strasbourg, Cologne, Mainz — major heritage stops",
            "Pancake-flat from Basel northwards — descent from the Alps does the work",
        ],
        "variant_trade_offs": [
            "Big-river barge traffic + industrial sections south of Cologne",
            "12+ days is a serious commitment",
            "Crowded with cruise-boat tourists between Koblenz and Mainz",
        ],
        "variant_best_for": (
            "experienced long-distance tourers, EuroVelo enthusiasts, riders "
            "ticking off the iconic European cycling routes"
        ),
        "anchors": [
            ("Andermatt", "Switzerland", 46.64, 8.59),
            ("Chur", "Switzerland", 46.85, 9.53),
            ("Basel", "Switzerland", 47.56, 7.59),
            ("Strasbourg", "France", 48.58, 7.75),
            ("Karlsruhe", "Germany", 49.00, 8.40),
            ("Mainz", "Germany", 50.00, 8.27),
            ("Koblenz", "Germany", 50.35, 7.59),
            ("Cologne", "Germany", 50.94, 6.96),
            ("Düsseldorf", "Germany", 51.23, 6.78),
            ("Nijmegen", "Netherlands", 51.84, 5.86),
            ("Rotterdam", "Netherlands", 51.92, 4.48),
            ("Hook of Holland", "Netherlands", 51.98, 4.13),
        ],
    },
]


# ---------------------------------------------------------------------------
# YAML emitter — matches the existing data/corridors/*.yaml schema
# ---------------------------------------------------------------------------


class _CompactDumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    """Block-literal for multi-line strings, plain for the rest."""
    if "\n" in data or len(data) > 70:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_CompactDumper.add_representer(str, _str_presenter)


def _anchor_dict(anchor: tuple) -> dict[str, object]:
    """Tuple → YAML anchor dict.

    Supports both:
      (name, country, lat, lon)
      (name, country, lat, lon, is_ferry_arrival, is_overnight)
    """
    out: dict[str, object] = {
        "name": anchor[0],
        "country": anchor[1],
        "lat": anchor[2],
        "lon": anchor[3],
    }
    if len(anchor) > 4 and anchor[4]:
        out["is_ferry_arrival"] = True
    if len(anchor) > 5 and not anchor[5]:
        out["is_overnight"] = False
    return out


def _write_yaml(corridor: dict[str, object]) -> Path:
    out = {
        "id": corridor["slug"],
        "label": corridor["label"],
        "start": corridor["start"],
        "end": corridor["end"],
        "aliases": corridor["aliases"],
        "description": corridor["description"],
        "variants": [
            {
                "name": corridor["variant_name"],
                "title": corridor["variant_title"],
                "headline_tag": corridor["variant_tag"],
                "is_default": True,
                "description": corridor["variant_description"],
                "distinguishing_features": corridor["variant_features"],
                "trade_offs": corridor["variant_trade_offs"],
                "best_for": corridor["variant_best_for"],
                "anchors": [_anchor_dict(a) for a in corridor["anchors"]],
            }
        ],
    }
    path = _DATA_DIR / f"{corridor['slug']}.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(
            out,
            f,
            Dumper=_CompactDumper,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )
    return path


# ---------------------------------------------------------------------------
# TypeScript fragment emitter for web/lib/corridors.ts
# ---------------------------------------------------------------------------


def _ts_country(country: str) -> str:
    return _COUNTRY_ISO.get(country, country[:2].upper())


def _ts_slug_to_id(slug: str) -> str:
    return slug.replace("-", "_")


def _emit_ts_corridor(corridor: dict[str, object]) -> str:
    """One TS Corridor const, matching the existing corridors.ts shape.

    Uses haversine × 1.25 to compute cumulative km. Approximate; the
    frontend uses km_from_start for map labels, not for planning math.
    """
    anchors: list[tuple] = corridor["anchors"]
    waypoints_ts: list[str] = []
    cum_km = 0.0
    prev = None
    for a in anchors:
        if prev is not None:
            cum_km += _haversine_km((prev[2], prev[3]), (a[2], a[3])) * 1.25
        name, country, lat, lon = a[0], a[1], a[2], a[3]
        is_ferry = "true" if (len(a) > 4 and a[4]) else "false"
        waypoints_ts.append(
            f'    {{ name: "{name}", country: "{_ts_country(country)}", '
            f'lat: {lat}, lon: {lon}, '
            f"is_ferry: {is_ferry}, km_from_start: {round(cum_km)} }}"
        )
        prev = a
    total_km = round(cum_km)
    est_days_100 = max(1, round(total_km / 100))

    var_id = _ts_slug_to_id(corridor["slug"])
    label = corridor["label"]
    aliases_ts = ", ".join(f'"{a}"' for a in corridor["aliases"])
    description = corridor["description"].replace("\n", " ").strip()
    if len(description) > 200:
        description = description[:197].rstrip() + "..."

    return (
        f"const {var_id}: Corridor = {{\n"
        f'  id: "{corridor["slug"]}",\n'
        f'  label: "{label}",\n'
        f'  description: "{description}",\n'
        f"  total_km: {total_km},\n"
        f"  estimated_days: {{ at_100km: {est_days_100} }},\n"
        f"  waypoints: [\n"
        + ",\n".join(waypoints_ts)
        + "\n  ],\n"
        f"  aliases: [{aliases_ts}],\n"
        f"}};\n"
    )


def main() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"emitting {len(_PHASE_2)} corridors to {_DATA_DIR.relative_to(Path.cwd())}/")

    ts_consts: list[str] = []
    const_names: list[str] = []
    id_literals: list[str] = []

    for corridor in _PHASE_2:
        path = _write_yaml(corridor)
        print(f"  wrote {path.name}")
        ts_consts.append(_emit_ts_corridor(corridor))
        const_names.append(_ts_slug_to_id(corridor["slug"]))
        id_literals.append(f'"{corridor["slug"]}"')

    # Emit the TS fragment to a side file.
    fragment = (
        "// === PHASE 2 corridors (generated by scripts/generate_phase2_corridors.py) ===\n\n"
        + "\n".join(ts_consts)
        + "\n// Add these to the CORRIDORS array:\n"
        + f"//   export const CORRIDORS: Corridor[] = [ams_cph, ldn_par, ldn_bri, {', '.join(const_names)}];\n"
        + "\n// And extend the CorridorId union (one literal per new corridor):\n"
        + f"//   export type CorridorId = \"ams-cph\" | \"ldn-par\" | \"ldn-bri\" | {' | '.join(id_literals)};\n"
    )
    _TS_OUT.write_text(fragment)
    print(f"\nTS fragment → {_TS_OUT.relative_to(Path.cwd())}")
    print(f"  ({len(ts_consts)} new Corridor consts + union literals)")


if __name__ == "__main__":
    main()
