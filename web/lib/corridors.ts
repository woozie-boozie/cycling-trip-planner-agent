/**
 * Hardcoded corridors for the route map — mirror of the backend's
 * `_CITY_COORDS` (in src/tools/weather.py) and `_KNOWN_ROUTES`
 * (in src/tools/route.py).
 *
 * Same data lives in two places, deliberately. The backend tool needs
 * lat/lon for Open-Meteo geocoding; the frontend needs it for map markers.
 * Trace events don't include tool-result content (kept payloads small),
 * so the frontend can't read waypoints from `/trace` — it ships its own
 * copy. When schemas drift, this file needs a manual update — keep it
 * tiny and obvious.
 *
 * If we ever expose `GET /routes` from the backend, this file deletes.
 */

export interface CorridorWaypoint {
  name: string;
  country: string;
  lat: number;
  lon: number;
  is_ferry: boolean;
  /** Cumulative distance from the corridor start, in km */
  km_from_start: number;
}

export type CorridorId =
  "ams-cph" | "ldn-par" | "ldn-bri" | "loire-a-velo" | "danube-passau-vienna" | "lf-kustroute" | "velodyssee" | "danube-vienna-budapest" | "lejog" | "c2c-whitehaven-tynemouth" | "hebridean-way" | "way-of-the-roses" | "venice-florence" | "sicily-loop" | "costa-brava" | "camino-del-norte" | "algarve-coast" | "berlin-copenhagen" | "prague-vienna" | "berlin-usedom" | "amsterdam-berlin" | "paris-lyon" | "eurovelo-15-rhine";

export interface Corridor {
  id: CorridorId;
  label: string;
  description: string;
  total_km: number;
  estimated_days: { at_100km: number };
  waypoints: CorridorWaypoint[];
  /** Set of normalised name aliases that signal this corridor in user prompts */
  aliases: string[];
}

const ams_cph: Corridor = {
  id: "ams-cph",
  label: "Amsterdam → Copenhagen",
  description: "EuroVelo 7/12, ~850 km, Rødby–Puttgarden ferry across the Fehmarn Belt.",
  total_km: 850,
  estimated_days: { at_100km: 9 },
  waypoints: [
    { name: "Amsterdam", country: "NL", lat: 52.3676, lon: 4.9041, is_ferry: false, km_from_start: 0 },
    { name: "Hoorn", country: "NL", lat: 52.6422, lon: 5.0594, is_ferry: false, km_from_start: 45 },
    { name: "Groningen", country: "NL", lat: 53.2194, lon: 6.5665, is_ferry: false, km_from_start: 230 },
    { name: "Bremen", country: "DE", lat: 53.0793, lon: 8.8017, is_ferry: false, km_from_start: 410 },
    { name: "Hamburg", country: "DE", lat: 53.5511, lon: 9.9937, is_ferry: false, km_from_start: 530 },
    { name: "Lübeck", country: "DE", lat: 53.8654, lon: 10.6866, is_ferry: false, km_from_start: 605 },
    { name: "Puttgarden", country: "DE", lat: 54.5092, lon: 11.2226, is_ferry: false, km_from_start: 690 },
    { name: "Rødby", country: "DK", lat: 54.6906, lon: 11.3539, is_ferry: true, km_from_start: 710 },
    { name: "Vordingborg", country: "DK", lat: 55.0084, lon: 11.9098, is_ferry: false, km_from_start: 770 },
    { name: "Copenhagen", country: "DK", lat: 55.6761, lon: 12.5683, is_ferry: false, km_from_start: 850 },
  ],
  aliases: ["amsterdam", "copenhagen", "ams-cph", "denmark", "netherlands"],
};

const ldn_par: Corridor = {
  id: "ldn-par",
  label: "London → Paris",
  // Distances reflect BRouter-computed V16a Beauvais variant (the agent's
  // default pick when no variant is named). Other variants — Oise/Chantilly
  // (~414 km) and Gisors (~374 km) — have their own totals reported in the
  // agent's response per turn; this static map shows the default's overview.
  description: "Avenue Verte V16a Beauvais, ~364 km, Newhaven–Dieppe ferry across the English Channel.",
  total_km: 364,
  estimated_days: { at_100km: 4 },
  waypoints: [
    { name: "London", country: "UK", lat: 51.5074, lon: -0.1278, is_ferry: false, km_from_start: 0 },
    { name: "East Grinstead", country: "UK", lat: 51.1267, lon: -0.0067, is_ferry: false, km_from_start: 83 },
    { name: "Lewes", country: "UK", lat: 50.8736, lon: 0.0097, is_ferry: false, km_from_start: 125 },
    { name: "Newhaven", country: "UK", lat: 50.7906, lon: 0.0533, is_ferry: false, km_from_start: 138 },
    { name: "Dieppe", country: "FR", lat: 49.9239, lon: 1.0775, is_ferry: true, km_from_start: 138 },
    { name: "Forges-les-Eaux", country: "FR", lat: 49.6173, lon: 1.546, is_ferry: false, km_from_start: 192 },
    { name: "Beauvais", country: "FR", lat: 49.4295, lon: 2.0808, is_ferry: false, km_from_start: 255 },
    { name: "Cergy-Pontoise", country: "FR", lat: 49.0398, lon: 2.0712, is_ferry: false, km_from_start: 326 },
    { name: "Paris", country: "FR", lat: 48.8566, lon: 2.3522, is_ferry: false, km_from_start: 364 },
  ],
  aliases: ["london", "paris", "ldn-par", "avenue verte", "newhaven", "dieppe"],
};

const ldn_bri: Corridor = {
  id: "ldn-bri",
  label: "London → Brighton",
  description: "South Downs classic, ~95 km, including Ditchling Beacon (steepest in southern England).",
  total_km: 95,
  estimated_days: { at_100km: 1 },
  waypoints: [
    { name: "London", country: "UK", lat: 51.5074, lon: -0.1278, is_ferry: false, km_from_start: 0 },
    { name: "Crystal Palace", country: "UK", lat: 51.4189, lon: -0.0735, is_ferry: false, km_from_start: 12 },
    { name: "Brighton", country: "UK", lat: 50.8225, lon: -0.1372, is_ferry: false, km_from_start: 95 },
  ],
  aliases: ["london", "brighton", "ldn-bri", "south downs", "ditchling"],
};

// === PHASE 2 corridors (generated by scripts/generate_phase2_corridors.py) ===

const loire_a_velo: Corridor = {
  id: "loire-a-velo",
  label: "Nevers → Saint-Brevin-les-Pins",
  description: "Loire à Vélo — the canonical signposted EuroVelo 6 western segment. ~800 km of mostly flat, dedicated cycle paths along France's longest river, through vineyards, châteaux country, and gentle Atlan...",
  total_km: 595,
  estimated_days: { at_100km: 6 },
  waypoints: [
    { name: "Nevers", country: "FR", lat: 47.0, lon: 3.16, is_ferry: false, km_from_start: 0 },
    { name: "Sancerre", country: "FR", lat: 47.33, lon: 2.84, is_ferry: false, km_from_start: 55 },
    { name: "Orléans", country: "FR", lat: 47.9, lon: 1.91, is_ferry: false, km_from_start: 173 },
    { name: "Blois", country: "FR", lat: 47.58, lon: 1.34, is_ferry: false, km_from_start: 242 },
    { name: "Tours", country: "FR", lat: 47.39, lon: 0.69, is_ferry: false, km_from_start: 309 },
    { name: "Saumur", country: "FR", lat: 47.26, lon: -0.07, is_ferry: false, km_from_start: 382 },
    { name: "Angers", country: "FR", lat: 47.47, lon: -0.55, is_ferry: false, km_from_start: 436 },
    { name: "Nantes", country: "FR", lat: 47.22, lon: -1.55, is_ferry: false, km_from_start: 537 },
    { name: "Saint-Brevin-les-Pins", country: "FR", lat: 47.25, lon: -2.17, is_ferry: false, km_from_start: 595 }
  ],
  aliases: ["loire", "loire a velo", "loire à vélo", "eurovelo 6 france", "nevers"],
};

const danube_passau_vienna: Corridor = {
  id: "danube-passau-vienna",
  label: "Passau → Vienna",
  description: "Donauradweg / EuroVelo 6 — the most popular long-distance cycling route in Europe. ~330 km along the Danube through Austria, with Linz, Melk's hilltop monastery, and the Wachau wine valley en route...",
  total_km: 293,
  estimated_days: { at_100km: 3 },
  waypoints: [
    { name: "Passau", country: "DE", lat: 48.57, lon: 13.46, is_ferry: false, km_from_start: 0 },
    { name: "Linz", country: "AT", lat: 48.31, lon: 14.29, is_ferry: false, km_from_start: 85 },
    { name: "Melk", country: "AT", lat: 48.23, lon: 15.33, is_ferry: false, km_from_start: 181 },
    { name: "Krems", country: "AT", lat: 48.41, lon: 15.61, is_ferry: false, km_from_start: 217 },
    { name: "Vienna", country: "AT", lat: 48.21, lon: 16.37, is_ferry: false, km_from_start: 293 }
  ],
  aliases: ["danube", "donauradweg", "eurovelo 6 austria", "passau", "vienna"],
};

const lf_kustroute: Corridor = {
  id: "lf-kustroute",
  label: "Den Helder → Cadzand",
  description: "LF Kustroute — the entire Dutch North Sea coast in one signposted route. ~570 km of dunes, beaches, and seaside towns from Den Helder in the north to the Belgian border at Cadzand. Pure flat, occas...",
  total_km: 257,
  estimated_days: { at_100km: 3 },
  waypoints: [
    { name: "Den Helder", country: "NL", lat: 52.96, lon: 4.76, is_ferry: false, km_from_start: 0 },
    { name: "Egmond aan Zee", country: "NL", lat: 52.62, lon: 4.63, is_ferry: false, km_from_start: 49 },
    { name: "IJmuiden", country: "NL", lat: 52.46, lon: 4.61, is_ferry: false, km_from_start: 71 },
    { name: "Zandvoort", country: "NL", lat: 52.37, lon: 4.53, is_ferry: false, km_from_start: 85 },
    { name: "The Hague", country: "NL", lat: 52.07, lon: 4.3, is_ferry: false, km_from_start: 131 },
    { name: "Hoek van Holland", country: "NL", lat: 51.98, lon: 4.13, is_ferry: false, km_from_start: 150 },
    { name: "Vlissingen", country: "NL", lat: 51.45, lon: 3.57, is_ferry: false, km_from_start: 238 },
    { name: "Cadzand", country: "NL", lat: 51.37, lon: 3.4, is_ferry: false, km_from_start: 257 }
  ],
  aliases: ["lf kustroute", "nl coast", "dutch coast", "north sea cycle", "den helder", "cadzand"],
};

const velodyssee: Corridor = {
  id: "velodyssee",
  label: "Roscoff → Hendaye",
  description: "La Vélodyssée — France's longest signposted cycle route. ~1,200 km of Atlantic coast from Brittany to the Spanish border, EuroVelo 1's French segment. Pine forest paths, Bordeaux wine country detou...",
  total_km: 1000,
  estimated_days: { at_100km: 10 },
  waypoints: [
    { name: "Roscoff", country: "FR", lat: 48.72, lon: -3.99, is_ferry: false, km_from_start: 0 },
    { name: "Brest", country: "FR", lat: 48.39, lon: -4.49, is_ferry: false, km_from_start: 65 },
    { name: "Quimper", country: "FR", lat: 47.99, lon: -4.1, is_ferry: false, km_from_start: 131 },
    { name: "Nantes", country: "FR", lat: 47.22, lon: -1.55, is_ferry: false, km_from_start: 393 },
    { name: "La Rochelle", country: "FR", lat: 46.16, lon: -1.15, is_ferry: false, km_from_start: 545 },
    { name: "Royan", country: "FR", lat: 45.62, lon: -1.03, is_ferry: false, km_from_start: 621 },
    { name: "Bordeaux", country: "FR", lat: 44.84, lon: -0.58, is_ferry: false, km_from_start: 738 },
    { name: "Arcachon", country: "FR", lat: 44.66, lon: -1.17, is_ferry: false, km_from_start: 802 },
    { name: "Hossegor", country: "FR", lat: 43.66, lon: -1.39, is_ferry: false, km_from_start: 942 },
    { name: "Hendaye", country: "FR", lat: 43.36, lon: -1.78, is_ferry: false, km_from_start: 1000 }
  ],
  aliases: ["velodyssee", "vélodyssée", "atlantic france", "eurovelo 1", "roscoff", "hendaye"],
};

const danube_vienna_budapest: Corridor = {
  id: "danube-vienna-budapest",
  label: "Vienna → Budapest",
  description: "Donauradweg east — Vienna to Budapest via Bratislava and Győr. ~330 km, ~5 days, the natural continuation if you've already done Passau → Vienna. Three capital cities in one tour, mostly flat, sign...",
  total_km: 304,
  estimated_days: { at_100km: 3 },
  waypoints: [
    { name: "Vienna", country: "AT", lat: 48.21, lon: 16.37, is_ferry: false, km_from_start: 0 },
    { name: "Bratislava", country: "SK", lat: 48.15, lon: 17.11, is_ferry: false, km_from_start: 69 },
    { name: "Győr", country: "HU", lat: 47.68, lon: 17.64, is_ferry: false, km_from_start: 151 },
    { name: "Komárom", country: "HU", lat: 47.74, lon: 18.13, is_ferry: false, km_from_start: 198 },
    { name: "Esztergom", country: "HU", lat: 47.79, lon: 18.74, is_ferry: false, km_from_start: 255 },
    { name: "Budapest", country: "HU", lat: 47.5, lon: 19.04, is_ferry: false, km_from_start: 304 }
  ],
  aliases: ["danube east", "donauradweg east", "vienna to budapest", "eurovelo 6 hungary"],
};

const lejog: Corridor = {
  id: "lejog",
  label: "Land's End → John o' Groats",
  description: "LEJOG — the iconic UK end-to-end. ~1,600 km from Cornwall's south-westernmost point to the north-eastern Scottish tip. The most famous long-distance cycling challenge in Britain; every cyclist's bu...",
  total_km: 1422,
  estimated_days: { at_100km: 14 },
  waypoints: [
    { name: "Land's End", country: "UK", lat: 50.07, lon: -5.71, is_ferry: false, km_from_start: 0 },
    { name: "Exeter", country: "UK", lat: 50.72, lon: -3.53, is_ferry: false, km_from_start: 213 },
    { name: "Bristol", country: "UK", lat: 51.45, lon: -2.58, is_ferry: false, km_from_start: 344 },
    { name: "Birmingham", country: "UK", lat: 52.49, lon: -1.89, is_ferry: false, km_from_start: 500 },
    { name: "Manchester", country: "UK", lat: 53.48, lon: -2.24, is_ferry: false, km_from_start: 641 },
    { name: "Carlisle", country: "UK", lat: 54.89, lon: -2.94, is_ferry: false, km_from_start: 845 },
    { name: "Glasgow", country: "UK", lat: 55.86, lon: -4.25, is_ferry: false, km_from_start: 1015 },
    { name: "Inverness", country: "UK", lat: 57.48, lon: -4.22, is_ferry: false, km_from_start: 1240 },
    { name: "John o' Groats", country: "UK", lat: 58.64, lon: -3.07, is_ferry: false, km_from_start: 1422 }
  ],
  aliases: ["lejog", "lands end to john o groats", "lands end john o'groats", "end to end", "uk end-to-end"],
};

const c2c_whitehaven_tynemouth: Corridor = {
  id: "c2c-whitehaven-tynemouth",
  label: "Whitehaven → Tynemouth",
  description: "Coast to Coast (C2C) — Britain's most-ridden multi-day challenge. ~225 km from the Irish Sea (Whitehaven) over the Pennines to the North Sea (Tynemouth). Doable in 3-5 days, signposted as NCN 7/14.",
  total_km: 192,
  estimated_days: { at_100km: 2 },
  waypoints: [
    { name: "Whitehaven", country: "UK", lat: 54.55, lon: -3.59, is_ferry: false, km_from_start: 0 },
    { name: "Keswick", country: "UK", lat: 54.6, lon: -3.13, is_ferry: false, km_from_start: 38 },
    { name: "Penrith", country: "UK", lat: 54.66, lon: -2.75, is_ferry: false, km_from_start: 69 },
    { name: "Alston", country: "UK", lat: 54.81, lon: -2.44, is_ferry: false, km_from_start: 102 },
    { name: "Consett", country: "UK", lat: 54.85, lon: -1.83, is_ferry: false, km_from_start: 151 },
    { name: "Newcastle upon Tyne", country: "UK", lat: 54.97, lon: -1.61, is_ferry: false, km_from_start: 175 },
    { name: "Tynemouth", country: "UK", lat: 55.02, lon: -1.42, is_ferry: false, km_from_start: 192 }
  ],
  aliases: ["coast to coast", "c2c", "ncn 7", "ncn 14", "whitehaven", "tynemouth", "lake district coast to coast"],
};

const hebridean_way: Corridor = {
  id: "hebridean-way",
  label: "Vatersay → Stornoway",
  description: "Hebridean Way — the Outer Hebrides traverse. ~300 km of single-track machair-edge roads, ferry crossings between islands, Atlantic-edge isolation. Often described as Britain's most beautiful long c...",
  total_km: 235,
  estimated_days: { at_100km: 2 },
  waypoints: [
    { name: "Vatersay", country: "UK", lat: 56.92, lon: -7.55, is_ferry: false, km_from_start: 0 },
    { name: "Castlebay", country: "UK", lat: 56.96, lon: -7.49, is_ferry: false, km_from_start: 7 },
    { name: "Eriskay", country: "UK", lat: 57.07, lon: -7.3, is_ferry: true, km_from_start: 28 },
    { name: "Lochboisdale", country: "UK", lat: 57.15, lon: -7.31, is_ferry: false, km_from_start: 39 },
    { name: "Berneray", country: "UK", lat: 57.71, lon: -7.18, is_ferry: true, km_from_start: 118 },
    { name: "Lochmaddy", country: "UK", lat: 57.6, lon: -7.16, is_ferry: false, km_from_start: 133 },
    { name: "Tarbert", country: "UK", lat: 57.9, lon: -6.79, is_ferry: true, km_from_start: 183 },
    { name: "Stornoway", country: "UK", lat: 58.21, lon: -6.39, is_ferry: false, km_from_start: 235 }
  ],
  aliases: ["hebridean way", "outer hebrides", "western isles", "vatersay", "stornoway"],
};

const way_of_the_roses: Corridor = {
  id: "way-of-the-roses",
  label: "Morecambe → Bridlington",
  description: "Way of the Roses — the 170-mile sea-to-sea across northern England's two historic rose counties (Lancashire's red, Yorkshire's white). ~270 km, signposted as NCN 69 + variants, 3-4 days at intermed...",
  total_km: 231,
  estimated_days: { at_100km: 2 },
  waypoints: [
    { name: "Morecambe", country: "UK", lat: 54.07, lon: -2.86, is_ferry: false, km_from_start: 0 },
    { name: "Settle", country: "UK", lat: 54.07, lon: -2.28, is_ferry: false, km_from_start: 47 },
    { name: "Pateley Bridge", country: "UK", lat: 54.09, lon: -1.77, is_ferry: false, km_from_start: 89 },
    { name: "Ripon", country: "UK", lat: 54.14, lon: -1.52, is_ferry: false, km_from_start: 111 },
    { name: "York", country: "UK", lat: 53.96, lon: -1.08, is_ferry: false, km_from_start: 154 },
    { name: "Pocklington", country: "UK", lat: 53.93, lon: -0.78, is_ferry: false, km_from_start: 179 },
    { name: "Bridlington", country: "UK", lat: 54.08, lon: -0.2, is_ferry: false, km_from_start: 231 }
  ],
  aliases: ["way of the roses", "morecambe", "bridlington", "lancashire to yorkshire", "sea to sea north", "ncn 69"],
};

const venice_florence: Corridor = {
  id: "venice-florence",
  label: "Venice → Florence",
  description: "Venice → Florence — Italy's most heritage-dense corridor. ~370 km via the Po valley flatlands and Apennine foothills. Padua, Ferrara, Bologna and Pistoia as overnight stops, each a major UNESCO or...",
  total_km: 311,
  estimated_days: { at_100km: 3 },
  waypoints: [
    { name: "Venice", country: "IT", lat: 45.44, lon: 12.32, is_ferry: false, km_from_start: 0 },
    { name: "Padua", country: "IT", lat: 45.41, lon: 11.88, is_ferry: false, km_from_start: 43 },
    { name: "Ferrara", country: "IT", lat: 44.84, lon: 11.62, is_ferry: false, km_from_start: 126 },
    { name: "Bologna", country: "IT", lat: 44.49, lon: 11.34, is_ferry: false, km_from_start: 182 },
    { name: "Pistoia", country: "IT", lat: 43.93, lon: 10.92, is_ferry: false, km_from_start: 271 },
    { name: "Florence", country: "IT", lat: 43.77, lon: 11.25, is_ferry: false, km_from_start: 311 }
  ],
  aliases: ["venice to florence", "venezia firenze", "italy classic", "po valley to tuscany"],
};

const sicily_loop: Corridor = {
  id: "sicily-loop",
  label: "Palermo → Catania → Palermo",
  description: "Sicily coastal loop — the full island circumnavigation by bike. ~750 km via Cefalù, Messina, Taormina, Catania, Syracuse, Ragusa, Agrigento and Trapani back to Palermo. Mt Etna views, Greek temples...",
  total_km: 865,
  estimated_days: { at_100km: 9 },
  waypoints: [
    { name: "Palermo", country: "IT", lat: 38.12, lon: 13.36, is_ferry: false, km_from_start: 0 },
    { name: "Cefalù", country: "IT", lat: 38.04, lon: 14.02, is_ferry: false, km_from_start: 73 },
    { name: "Messina", country: "IT", lat: 38.19, lon: 15.55, is_ferry: false, km_from_start: 242 },
    { name: "Taormina", country: "IT", lat: 37.85, lon: 15.29, is_ferry: false, km_from_start: 297 },
    { name: "Catania", country: "IT", lat: 37.51, lon: 15.09, is_ferry: false, km_from_start: 349 },
    { name: "Syracuse", country: "IT", lat: 37.07, lon: 15.29, is_ferry: false, km_from_start: 414 },
    { name: "Ragusa", country: "IT", lat: 36.93, lon: 14.73, is_ferry: false, km_from_start: 479 },
    { name: "Agrigento", country: "IT", lat: 37.31, lon: 13.59, is_ferry: false, km_from_start: 616 },
    { name: "Trapani", country: "IT", lat: 38.02, lon: 12.51, is_ferry: false, km_from_start: 771 },
    { name: "Palermo", country: "IT", lat: 38.12, lon: 13.36, is_ferry: false, km_from_start: 865 }
  ],
  aliases: ["sicily", "sicilia", "palermo loop", "sicilian coast", "palermo catania"],
};

const costa_brava: Corridor = {
  id: "costa-brava",
  label: "Barcelona → Cap de Creus",
  description: "Costa Brava — Catalonia's wild coast. ~280 km from Barcelona north along the Mediterranean via Tossa de Mar, Palamós and Cadaqués to the rocky finale at Cap de Creus. Mix of beach towns and Dalí co...",
  total_km: 191,
  estimated_days: { at_100km: 2 },
  waypoints: [
    { name: "Barcelona", country: "ES", lat: 41.39, lon: 2.17, is_ferry: false, km_from_start: 0 },
    { name: "Mataró", country: "ES", lat: 41.54, lon: 2.44, is_ferry: false, km_from_start: 35 },
    { name: "Blanes", country: "ES", lat: 41.67, lon: 2.79, is_ferry: false, km_from_start: 76 },
    { name: "Tossa de Mar", country: "ES", lat: 41.72, lon: 2.93, is_ferry: false, km_from_start: 92 },
    { name: "Palamós", country: "ES", lat: 41.85, lon: 3.13, is_ferry: false, km_from_start: 119 },
    { name: "L'Escala", country: "ES", lat: 42.12, lon: 3.13, is_ferry: false, km_from_start: 157 },
    { name: "Cadaqués", country: "ES", lat: 42.29, lon: 3.28, is_ferry: false, km_from_start: 185 },
    { name: "Cap de Creus", country: "ES", lat: 42.32, lon: 3.32, is_ferry: false, km_from_start: 191 }
  ],
  aliases: ["costa brava", "barcelona to cap de creus", "catalan coast", "girona coast"],
};

const camino_del_norte: Corridor = {
  id: "camino-del-norte",
  label: "Irún → Santiago de Compostela",
  description: "Camino del Norte — the northern Camino de Santiago, rideable as a cycle pilgrimage. ~825 km along Spain's Atlantic coast through Basque country, Cantabria, Asturias and Galicia. The greener, hillie...",
  total_km: 714,
  estimated_days: { at_100km: 7 },
  waypoints: [
    { name: "Irún", country: "ES", lat: 43.34, lon: -1.79, is_ferry: false, km_from_start: 0 },
    { name: "San Sebastián", country: "ES", lat: 43.32, lon: -1.98, is_ferry: false, km_from_start: 19 },
    { name: "Bilbao", country: "ES", lat: 43.26, lon: -2.92, is_ferry: false, km_from_start: 115 },
    { name: "Santander", country: "ES", lat: 43.46, lon: -3.81, is_ferry: false, km_from_start: 209 },
    { name: "Llanes", country: "ES", lat: 43.42, lon: -4.75, is_ferry: false, km_from_start: 304 },
    { name: "Gijón", country: "ES", lat: 43.54, lon: -5.66, is_ferry: false, km_from_start: 397 },
    { name: "Mondoñedo", country: "ES", lat: 43.43, lon: -7.36, is_ferry: false, km_from_start: 569 },
    { name: "Sobrado", country: "ES", lat: 43.04, lon: -8.03, is_ferry: false, km_from_start: 656 },
    { name: "Santiago de Compostela", country: "ES", lat: 42.88, lon: -8.55, is_ferry: false, km_from_start: 714 }
  ],
  aliases: ["camino del norte", "northern way", "north camino", "irun to santiago", "basque coast", "asturias coast"],
};

const algarve_coast: Corridor = {
  id: "algarve-coast",
  label: "Lagos → Tavira",
  description: "Algarve coast — Portugal's southern coast end-to-end by bike. ~100 km of mostly flat coastal cycling from Lagos in the west to Tavira near the Spanish border. Short trip, big winter-sun appeal.",
  total_km: 120,
  estimated_days: { at_100km: 1 },
  waypoints: [
    { name: "Lagos", country: "PT", lat: 37.1, lon: -8.67, is_ferry: false, km_from_start: 0 },
    { name: "Portimão", country: "PT", lat: 37.14, lon: -8.54, is_ferry: false, km_from_start: 15 },
    { name: "Albufeira", country: "PT", lat: 37.09, lon: -8.25, is_ferry: false, km_from_start: 48 },
    { name: "Faro", country: "PT", lat: 37.02, lon: -7.93, is_ferry: false, km_from_start: 85 },
    { name: "Olhão", country: "PT", lat: 37.03, lon: -7.84, is_ferry: false, km_from_start: 95 },
    { name: "Tavira", country: "PT", lat: 37.13, lon: -7.65, is_ferry: false, km_from_start: 120 }
  ],
  aliases: ["algarve", "portugal coast", "lagos to tavira", "south portugal"],
};

const berlin_copenhagen: Corridor = {
  id: "berlin-copenhagen",
  label: "Berlin → Copenhagen",
  description: "Berlin → Copenhagen — EuroVelo 7's northern German + Danish segment. ~700 km via Rostock and the Warnemünde-Gedser ferry. Flat throughout, both ends being two of Europe's most cyclist-friendly capi...",
  total_km: 487,
  estimated_days: { at_100km: 5 },
  waypoints: [
    { name: "Berlin", country: "DE", lat: 52.52, lon: 13.4, is_ferry: false, km_from_start: 0 },
    { name: "Wittstock", country: "DE", lat: 53.16, lon: 12.49, is_ferry: false, km_from_start: 117 },
    { name: "Rostock", country: "DE", lat: 54.09, lon: 12.13, is_ferry: false, km_from_start: 250 },
    { name: "Warnemünde", country: "DE", lat: 54.18, lon: 12.08, is_ferry: false, km_from_start: 263 },
    { name: "Gedser", country: "DK", lat: 54.57, lon: 11.93, is_ferry: true, km_from_start: 319 },
    { name: "Vordingborg", country: "DK", lat: 55.01, lon: 11.91, is_ferry: false, km_from_start: 380 },
    { name: "Copenhagen", country: "DK", lat: 55.68, lon: 12.57, is_ferry: false, km_from_start: 487 }
  ],
  aliases: ["berlin to copenhagen", "eurovelo 7 north", "rostock to copenhagen", "berlin copenhagen"],
};

const prague_vienna: Corridor = {
  id: "prague-vienna",
  label: "Prague → Vienna",
  description: "Prague → Vienna Greenways — the signposted Czech/Austrian cycle corridor. ~400 km via Český Krumlov UNESCO town and the Moravian wine region. 5-6 days at intermediate pace.",
  total_km: 506,
  estimated_days: { at_100km: 5 },
  waypoints: [
    { name: "Prague", country: "CZ", lat: 50.08, lon: 14.43, is_ferry: false, km_from_start: 0 },
    { name: "České Budějovice", country: "CZ", lat: 48.97, lon: 14.47, is_ferry: false, km_from_start: 154 },
    { name: "Český Krumlov", country: "CZ", lat: 48.81, lon: 14.32, is_ferry: false, km_from_start: 180 },
    { name: "Mikulov", country: "CZ", lat: 48.81, lon: 16.64, is_ferry: false, km_from_start: 393 },
    { name: "Břeclav", country: "CZ", lat: 48.76, lon: 16.88, is_ferry: false, km_from_start: 416 },
    { name: "Vienna", country: "AT", lat: 48.21, lon: 16.37, is_ferry: false, km_from_start: 506 }
  ],
  aliases: ["prague to vienna", "greenways prague vienna", "czech vienna", "prague vienna"],
};

const berlin_usedom: Corridor = {
  id: "berlin-usedom",
  label: "Berlin → Usedom",
  description: "Berlin-Usedom-Radweg — the signposted Berlin-to-Baltic ride. ~290 km via Prenzlau and Anklam to the island of Usedom and the seaside town of Heringsdorf. Mostly flat, lake-and-canal scenery on the...",
  total_km: 270,
  estimated_days: { at_100km: 3 },
  waypoints: [
    { name: "Berlin", country: "DE", lat: 52.52, lon: 13.4, is_ferry: false, km_from_start: 0 },
    { name: "Eberswalde", country: "DE", lat: 52.83, lon: 13.83, is_ferry: false, km_from_start: 56 },
    { name: "Prenzlau", country: "DE", lat: 53.32, lon: 13.86, is_ferry: false, km_from_start: 124 },
    { name: "Pasewalk", country: "DE", lat: 53.51, lon: 13.99, is_ferry: false, km_from_start: 153 },
    { name: "Anklam", country: "DE", lat: 53.85, lon: 13.69, is_ferry: false, km_from_start: 206 },
    { name: "Wolgast", country: "DE", lat: 54.05, lon: 13.77, is_ferry: false, km_from_start: 235 },
    { name: "Heringsdorf", country: "DE", lat: 53.95, lon: 14.16, is_ferry: false, km_from_start: 270 }
  ],
  aliases: ["berlin to usedom", "berlin baltic", "usedom", "heringsdorf", "berlin-usedom-radweg"],
};

const amsterdam_berlin: Corridor = {
  id: "amsterdam-berlin",
  label: "Amsterdam → Berlin",
  description: "Amsterdam → Berlin — the European capital-to-capital ride. ~580 km via Utrecht, Münster, Hannover and Magdeburg. Mostly flat, mix of Dutch LF paths and German Radwege. 6-8 days at intermediate pace.",
  total_km: 785,
  estimated_days: { at_100km: 8 },
  waypoints: [
    { name: "Amsterdam", country: "NL", lat: 52.37, lon: 4.9, is_ferry: false, km_from_start: 0 },
    { name: "Utrecht", country: "NL", lat: 52.09, lon: 5.12, is_ferry: false, km_from_start: 43 },
    { name: "Arnhem", country: "NL", lat: 51.98, lon: 5.91, is_ferry: false, km_from_start: 112 },
    { name: "Münster", country: "DE", lat: 51.96, lon: 7.63, is_ferry: false, km_from_start: 260 },
    { name: "Osnabrück", country: "DE", lat: 52.28, lon: 8.05, is_ferry: false, km_from_start: 317 },
    { name: "Hannover", country: "DE", lat: 52.37, lon: 9.74, is_ferry: false, km_from_start: 461 },
    { name: "Magdeburg", country: "DE", lat: 52.13, lon: 11.63, is_ferry: false, km_from_start: 625 },
    { name: "Berlin", country: "DE", lat: 52.52, lon: 13.4, is_ferry: false, km_from_start: 785 }
  ],
  aliases: ["amsterdam to berlin", "europaradweg", "eurovelo 4 north", "amsterdam berlin"],
};

const paris_lyon: Corridor = {
  id: "paris-lyon",
  label: "Paris → Lyon",
  description: "Paris → Lyon via the Burgundy canals — France's other headline corridor. ~500 km via Sens, Auxerre, Dijon and Beaune. Burgundy wine country, canal towpaths, châteaux, and gastronomic legend en route.",
  total_km: 562,
  estimated_days: { at_100km: 6 },
  waypoints: [
    { name: "Paris", country: "FR", lat: 48.86, lon: 2.35, is_ferry: false, km_from_start: 0 },
    { name: "Sens", country: "FR", lat: 48.2, lon: 3.28, is_ferry: false, km_from_start: 125 },
    { name: "Auxerre", country: "FR", lat: 47.8, lon: 3.57, is_ferry: false, km_from_start: 187 },
    { name: "Dijon", country: "FR", lat: 47.32, lon: 5.04, is_ferry: false, km_from_start: 340 },
    { name: "Beaune", country: "FR", lat: 47.02, lon: 4.83, is_ferry: false, km_from_start: 387 },
    { name: "Mâcon", country: "FR", lat: 46.31, lon: 4.83, is_ferry: false, km_from_start: 485 },
    { name: "Lyon", country: "FR", lat: 45.76, lon: 4.84, is_ferry: false, km_from_start: 562 }
  ],
  aliases: ["paris to lyon", "bourgogne canal", "via fluvia", "paris lyon", "burgundy bike"],
};

const eurovelo_15_rhine: Corridor = {
  id: "eurovelo-15-rhine",
  label: "Andermatt → Hook of Holland",
  description: "EuroVelo 15 — the full Rhine from the Swiss source town of Andermatt to the North Sea at Hook of Holland. ~1,230 km through Switzerland, France, Germany and the Netherlands. One of EuroVelo's signa...",
  total_km: 1154,
  estimated_days: { at_100km: 12 },
  waypoints: [
    { name: "Andermatt", country: "CH", lat: 46.64, lon: 8.59, is_ferry: false, km_from_start: 0 },
    { name: "Chur", country: "CH", lat: 46.85, lon: 9.53, is_ferry: false, km_from_start: 94 },
    { name: "Basel", country: "CH", lat: 47.56, lon: 7.59, is_ferry: false, km_from_start: 302 },
    { name: "Strasbourg", country: "FR", lat: 48.58, lon: 7.75, is_ferry: false, km_from_start: 445 },
    { name: "Karlsruhe", country: "DE", lat: 49.0, lon: 8.4, is_ferry: false, km_from_start: 528 },
    { name: "Mainz", country: "DE", lat: 50.0, lon: 8.27, is_ferry: false, km_from_start: 668 },
    { name: "Koblenz", country: "DE", lat: 50.35, lon: 7.59, is_ferry: false, km_from_start: 745 },
    { name: "Cologne", country: "DE", lat: 50.94, lon: 6.96, is_ferry: false, km_from_start: 844 },
    { name: "Düsseldorf", country: "DE", lat: 51.23, lon: 6.78, is_ferry: false, km_from_start: 888 },
    { name: "Nijmegen", country: "NL", lat: 51.84, lon: 5.86, is_ferry: false, km_from_start: 1004 },
    { name: "Rotterdam", country: "NL", lat: 51.92, lon: 4.48, is_ferry: false, km_from_start: 1123 },
    { name: "Hook of Holland", country: "NL", lat: 51.98, lon: 4.13, is_ferry: false, km_from_start: 1154 }
  ],
  aliases: ["eurovelo 15", "rhine cycle route", "rheinradweg", "rhine bike", "andermatt hook of holland"],
};


export const CORRIDORS: Corridor[] = [ams_cph, ldn_par, ldn_bri, loire_a_velo, danube_passau_vienna, lf_kustroute, velodyssee, danube_vienna_budapest, lejog, c2c_whitehaven_tynemouth, hebridean_way, way_of_the_roses, venice_florence, sicily_loop, costa_brava, camino_del_norte, algarve_coast, berlin_copenhagen, prague_vienna, berlin_usedom, amsterdam_berlin, paris_lyon, eurovelo_15_rhine];

/**
 * Pick the corridor that best matches a user message — but only when
 * the message references BOTH endpoints (start AND end city).
 *
 * Previous behaviour matched on ANY single alias hit, which caused a
 * "London → Edinburgh" request to fuzzy-match `ldn-par` (because "London"
 * alone hit one alias) and render the wrong map. The fix: require both
 * endpoint city names to appear before claiming this is a catalog corridor.
 *
 * For out-of-catalog corridors (e.g. London → Edinburgh, Bordeaux → Geneva),
 * `matchCorridor` correctly returns `null` and the visual layer falls
 * through to markdown rendering without a misleading corridor map.
 *
 * Multi-corridor mentions (e.g. "compare London → Paris vs London → Brighton")
 * tie-break in favour of the corridor with the most alias hits *beyond*
 * the endpoint check — gives heritage / route-name signals like
 * "avenue verte" or "south downs" a chance to disambiguate.
 */
export function matchCorridor(text: string): Corridor | null {
  const lower = text.toLowerCase();
  let best: { corridor: Corridor; score: number } | null = null;
  for (const c of CORRIDORS) {
    const start = c.waypoints[0].name.toLowerCase();
    const end = c.waypoints[c.waypoints.length - 1].name.toLowerCase();
    // Gate: BOTH endpoints must appear. This is the headline fix —
    // single-endpoint matches were the bug.
    if (!lower.includes(start) || !lower.includes(end)) continue;
    // Tie-break score = count of additional alias hits (route names,
    // signature features) that point to this corridor specifically.
    let score = 2; // both endpoints
    for (const alias of c.aliases) {
      if (alias === start || alias === end) continue;
      if (lower.includes(alias)) score += 1;
    }
    if (!best || score > best.score) best = { corridor: c, score };
  }
  return best?.corridor ?? null;
}

/**
 * Bounding box [southWest, northEast] for a corridor, used to fit a Leaflet
 * map view to its waypoints.
 */
export function corridorBounds(c: Corridor): [[number, number], [number, number]] {
  const lats = c.waypoints.map((w) => w.lat);
  const lons = c.waypoints.map((w) => w.lon);
  return [
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)],
  ];
}
