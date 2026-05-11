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

export type CorridorId = "ams-cph" | "ldn-par" | "ldn-bri";

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

export const CORRIDORS: Corridor[] = [ams_cph, ldn_par, ldn_bri];

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
