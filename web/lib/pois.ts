/**
 * POIs per corridor — visual-map data layer.
 *
 * This data is the visual map's view of each corridor; it does NOT drive
 * the agent's reasoning. The agent uses Google Places live (`USE_REAL_PLACES=true`)
 * for accommodation and `find_pois` lookups.
 *
 * Two sources merged together:
 *
 *   1. **Hand-curated narrative anchors** — declared inline below. Rich:
 *      they carry `rating`, `price`, `species`, `hours`, `km_from_start`,
 *      and a hand-written `description`. These are the "story" POIs that
 *      tell you why a corridor is interesting (Beauvais Cathedral, Pays
 *      de Bray cheese country, Ditchling Beacon climb).
 *
 *   2. **OSM scatter** — fetched at build time via
 *      `scripts/fetch_corridor_pois.py` from OpenStreetMap's Overpass API,
 *      committed to `web/lib/data/pois-{corridor}.json`. ~100-150 POIs
 *      per corridor, real cycling-relevant data (`shop=bicycle`,
 *      `tourism=camp_site`, `amenity=drinking_water`, etc.). Filtered to
 *      within 8 km of the route polyline, capped per category.
 *
 * Merge rule: curated POIs win on collision (case-insensitive name +
 * coordinate rounded to 2 d.p.). Re-run `make pois` or
 * `python scripts/fetch_corridor_pois.py` to refresh the OSM tier.
 *
 * 10 layers (matches Velocycle mockup):
 *   photo · wildlife · camp · food · heritage · repair · water ·
 *   hospital · ferry · warning
 */

import type { CorridorId } from "@/lib/corridors";
import OSM_LDN_PAR from "@/lib/data/pois-ldn-par.json";
import OSM_AMS_CPH from "@/lib/data/pois-ams-cph.json";
import OSM_LDN_BRI from "@/lib/data/pois-ldn-bri.json";

export type PoiLayer =
  | "photo"
  | "wildlife"
  | "camp"
  | "food"
  | "heritage"
  | "repair"
  | "water"
  | "hospital"
  | "ferry"
  | "warning";

export interface Poi {
  /** Real-world coordinates — used by the SVG map's lat/lon → x/y projector */
  lat: number;
  lon: number;
  layer: PoiLayer;
  label: string;
  description: string;
  /** Cumulative km from corridor start, when known */
  km_from_start?: number;
  /** Optional metadata that surfaces in the bottom sheet */
  price?: string;
  rating?: number;
  species?: string;
  hours?: string;
}

/** Display metadata per layer — used by the LayerChips component */
export const LAYER_META: Record<
  PoiLayer,
  { label: string; color: string; icon: string }
> = {
  photo: { label: "Photo spots", color: "#9B5DA8", icon: "camera" },
  wildlife: { label: "Wildlife", color: "#2D8C5A", icon: "wildlife" },
  camp: { label: "Campsites", color: "#D4942A", icon: "tent" },
  food: { label: "Food", color: "#FF4A1C", icon: "fork" },
  heritage: { label: "Heritage", color: "#856547", icon: "castle" },
  repair: { label: "Repair", color: "#3D3B36", icon: "wrench" },
  water: { label: "Water", color: "#5C9AC4", icon: "drop" },
  hospital: { label: "Hospital", color: "#C93838", icon: "cross" },
  ferry: { label: "Ferry", color: "#5C9AC4", icon: "ferry" },
  warning: { label: "Hazards", color: "#D4942A", icon: "warning" },
};

/** Order in which the layer chips render in the toolbar */
export const LAYER_ORDER: PoiLayer[] = [
  "photo",
  "wildlife",
  "camp",
  "food",
  "heritage",
  "repair",
  "water",
  "hospital",
  "ferry",
  "warning",
];

// ---------------------------------------------------------------------------
// Curated POIs — the narrative anchors per corridor
// ---------------------------------------------------------------------------

const CURATED_LDN_PAR: Poi[] = [
  // London end
  { lat: 51.461, lon: -0.115, layer: "repair", label: "Brixton Cycles", description: "Co-op bike shop, last-chance service before the Avenue Verte.", km_from_start: 5, hours: "10–18 Mon-Sat" },
  { lat: 51.508, lon: -0.128, layer: "water", label: "Embankment drinking fountains", description: "Refill London fountains along Victoria Embankment.", km_from_start: 1 },
  { lat: 51.5249, lon: -0.1340, layer: "warning", label: "A23 traffic squeeze", description: "1.4 km of A-road shoulder near East Grinstead. Daylight-only.", km_from_start: 24 },
  // Sussex
  { lat: 50.873, lon: 0.008, layer: "food", label: "Lewes Friday Market", description: "Sussex produce, cheeses, breads — fri only.", km_from_start: 75 },
  { lat: 50.873, lon: 0.008, layer: "photo", label: "Lewes Castle viewpoint", description: "Views across the Ouse valley to the South Downs.", km_from_start: 75 },
  // Newhaven / ferry
  { lat: 50.793, lon: 0.054, layer: "repair", label: "Newhaven Cycle Centre", description: "Last UK service before the ferry. Quick spannering + tubes.", km_from_start: 90 },
  { lat: 50.793, lon: 0.057, layer: "ferry", label: "Newhaven–Dieppe ferry", description: "DFDS, ~4 h crossing. Bikes free above the foot-passenger fare.", km_from_start: 95, price: "£33–55" },
  // Dieppe arrival
  { lat: 49.924, lon: 1.078, layer: "photo", label: "Dieppe cliffs", description: "Best from the ferry deck on approach, golden hour.", km_from_start: 100 },
  { lat: 49.924, lon: 1.078, layer: "food", label: "Café des Tribunaux", description: "Atmospheric old-Dieppe café — coffee + Norman crêpes.", km_from_start: 100 },
  { lat: 49.924, lon: 1.078, layer: "heritage", label: "Dieppe old port", description: "Cobbled quays + 17th-century mansions. 30 min wander.", km_from_start: 100 },
  // Pays de Bray
  { lat: 49.617, lon: 1.546, layer: "wildlife", label: "Pays de Bray buzzards", description: "Common buzzards above the dairy fields, dawn especially.", km_from_start: 145, species: "Common buzzard" },
  { lat: 49.617, lon: 1.546, layer: "food", label: "Pays de Bray cheese", description: "Neufchâtel AOC dairy — heart-shaped cheese tasting.", km_from_start: 175, price: "€8" },
  { lat: 49.617, lon: 1.546, layer: "camp", label: "Camping de Forges", description: "Riverside, hot showers, cyclist-friendly.", km_from_start: 175, price: "€12/night", rating: 4.4 },
  { lat: 49.617, lon: 1.546, layer: "water", label: "Forges fountain", description: "Free public fountain by the church.", km_from_start: 175 },
  // Beauvais
  { lat: 49.430, lon: 2.081, layer: "heritage", label: "Beauvais Cathedral", description: "Tallest Gothic vault in the world. 30 min climb the tower.", km_from_start: 240 },
  { lat: 49.430, lon: 2.081, layer: "photo", label: "Cathedral spires", description: "Wide-angle from Place Saint-Pierre, late afternoon.", km_from_start: 240 },
  { lat: 49.430, lon: 2.081, layer: "camp", label: "Camping Beauvais", description: "10 min from cathedral; basic.", km_from_start: 240, price: "€10/night", rating: 4.1 },
  { lat: 49.430, lon: 2.081, layer: "repair", label: "Vélo Beauvais", description: "Walk-in, e-bike compatible.", km_from_start: 240 },
  { lat: 49.430, lon: 2.081, layer: "hospital", label: "CHGM Beauvais", description: "24 h emergency, 1 km from centre.", km_from_start: 240 },
  // Paris
  { lat: 48.857, lon: 2.352, layer: "heritage", label: "Notre-Dame", description: "Finish line. Bike racks at the south parvis.", km_from_start: 364 },
  { lat: 48.857, lon: 2.352, layer: "food", label: "Le Bouillon Pigalle", description: "Affordable French classics; queue-friendly post-ride.", km_from_start: 364 },
];

const CURATED_AMS_CPH: Poi[] = [
  // Amsterdam
  { lat: 52.368, lon: 4.904, layer: "repair", label: "Cycles Roberto", description: "Independent shop, popular with locals + tourers.", km_from_start: 0 },
  { lat: 52.368, lon: 4.904, layer: "water", label: "Vondelpark fountains", description: "Multiple refill points in Amsterdam's biggest park.", km_from_start: 0 },
  { lat: 52.368, lon: 4.904, layer: "food", label: "Albert Cuyp Markt", description: "Famous open-air market — food + bric-a-brac.", km_from_start: 2 },
  // Inland route
  { lat: 53.219, lon: 6.567, layer: "food", label: "Groningen veggie scene", description: "University city; excellent vegetarian choice.", km_from_start: 230 },
  { lat: 53.079, lon: 8.802, layer: "heritage", label: "Bremen Altstadt", description: "UNESCO old town — Stadtmusikanten statue obligatory.", km_from_start: 410 },
  { lat: 53.079, lon: 8.802, layer: "food", label: "Schüttinger Brauhaus", description: "Historic Bremen brewpub — locally brewed Pils.", km_from_start: 410 },
  { lat: 53.551, lon: 9.994, layer: "photo", label: "Speicherstadt warehouses", description: "UNESCO Hamburg warehouse district — bike-friendly Elbe path.", km_from_start: 530 },
  { lat: 53.551, lon: 9.994, layer: "food", label: "Altes Mädchen", description: "Hamburg craft beer + veggie burgers (Schanze district).", km_from_start: 530 },
  { lat: 53.865, lon: 10.687, layer: "heritage", label: "Lübeck Holstentor", description: "Iconic UNESCO Hanseatic gateway. Marzipan capital.", km_from_start: 605 },
  { lat: 53.865, lon: 10.687, layer: "food", label: "Brauberger Lübeck", description: "Craft brewery, good salads after the long day.", km_from_start: 605 },
  // Coastal stretches
  { lat: 53.55, lon: 7.0, layer: "wildlife", label: "Wadden Sea seals", description: "Common seals haul out on sandbanks at low tide.", km_from_start: 480, species: "Harbour seal" },
  { lat: 53.55, lon: 7.0, layer: "wildlife", label: "Migratory wading birds", description: "Oystercatchers, dunlin, avocets — UNESCO Wadden coast.", km_from_start: 480, species: "Mixed waders" },
  { lat: 53.55, lon: 7.0, layer: "warning", label: "North Sea westerlies", description: "Prevailing headwinds in June — bank an hour per day.", km_from_start: 460 },
  // Ferry
  { lat: 54.509, lon: 11.223, layer: "ferry", label: "Puttgarden–Rødby ferry", description: "Scandlines · ~45 min crossing · bikes free or nominal.", km_from_start: 690, price: "~€5" },
  { lat: 54.509, lon: 11.223, layer: "camp", label: "Camping Wulfener Hals", description: "Short ride to the ferry terminal.", km_from_start: 685, price: "€26/night" },
  // Denmark
  { lat: 55.008, lon: 11.910, layer: "camp", label: "Vordingborg Camping", description: "Flat Lolland/Falster islands; basic riverside pitch.", km_from_start: 770, price: "€22/night" },
  { lat: 55.676, lon: 12.568, layer: "heritage", label: "The Round Tower", description: "17th-century Copenhagen tower — panoramic city view.", km_from_start: 850 },
  { lat: 55.676, lon: 12.568, layer: "food", label: "Mikkeller Bar", description: "Famous Danish craft brewery's flagship — cyclist-friendly.", km_from_start: 850 },
  { lat: 55.676, lon: 12.568, layer: "hospital", label: "Rigshospitalet", description: "Denmark's largest hospital, 24 h A&E.", km_from_start: 850 },
  { lat: 55.676, lon: 12.568, layer: "camp", label: "Camping Charlottenlund Fort", description: "Seafront pitches, direct cycle path into the city.", km_from_start: 850, price: "€30/night" },
];

const CURATED_LDN_BRI: Poi[] = [
  // London
  { lat: 51.461, lon: -0.115, layer: "repair", label: "Brixton Cycles", description: "Co-op bike shop, repairs while you wait.", km_from_start: 5 },
  { lat: 51.508, lon: -0.128, layer: "water", label: "Embankment fountains", description: "Refill London fountains along Victoria Embankment.", km_from_start: 1 },
  { lat: 51.508, lon: -0.128, layer: "food", label: "Borough Market", description: "London's flagship food market — local produce + snacks.", km_from_start: 2 },
  // Mid-route
  { lat: 51.4189, lon: -0.0735, layer: "photo", label: "Crystal Palace viewpoint", description: "Panorama of central London skyline at sunrise.", km_from_start: 12 },
  // Sussex / South Downs
  { lat: 50.91, lon: -0.10, layer: "warning", label: "Ditchling Beacon climb", description: "Steepest in southern England. Granny gear ready.", km_from_start: 75 },
  { lat: 50.91, lon: -0.10, layer: "wildlife", label: "South Downs sky larks", description: "Listen — rising over the chalk grassland, May–July.", km_from_start: 70, species: "Skylark" },
  { lat: 50.91, lon: -0.21, layer: "photo", label: "Devil's Dyke viewpoint", description: "South Downs ridge with views to the sea — short detour.", km_from_start: 80 },
  { lat: 50.873, lon: 0.008, layer: "heritage", label: "Lewes Castle", description: "Norman keep + Sussex history. 1 hr stop.", km_from_start: 60 },
  // Brighton
  { lat: 50.822, lon: -0.137, layer: "heritage", label: "Brighton Pier", description: "1899 Victorian pier — finish-line photo.", km_from_start: 95 },
  { lat: 50.822, lon: -0.137, layer: "food", label: "Brighton fish & chips", description: "Reward at the seafront. Multiple options.", km_from_start: 95 },
  { lat: 50.822, lon: -0.137, layer: "repair", label: "Mickle Bicycle Repair", description: "Indie repair specialist; great post-Ditchling adjustments.", km_from_start: 95 },
  { lat: 50.822, lon: -0.137, layer: "water", label: "Brighton Pier fountain", description: "Refill point at the pier entrance.", km_from_start: 95 },
  { lat: 50.822, lon: -0.137, layer: "hospital", label: "Royal Sussex County", description: "Brighton's main hospital with 24 h A&E.", km_from_start: 94 },
  { lat: 50.822, lon: -0.137, layer: "camp", label: "Sheepcote Valley Caravan Park", description: "Brighton's main campsite, 4 km from the seafront.", km_from_start: 99, price: "£28/night" },
];

// ---------------------------------------------------------------------------
// Merge: curated narrative anchors + OSM scatter
// ---------------------------------------------------------------------------

/** Coarse dedupe key — case-insensitive label + lat/lon rounded to 2 d.p. */
function dedupeKey(poi: Poi): string {
  return `${poi.label.trim().toLowerCase()}|${poi.lat.toFixed(2)}|${poi.lon.toFixed(2)}`;
}

function mergePois(curated: Poi[], osm: Poi[]): Poi[] {
  const seen = new Set(curated.map(dedupeKey));
  const out = [...curated];
  for (const p of osm) {
    const k = dedupeKey(p);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(p);
  }
  return out;
}

// JSON files arrive as `unknown` types; runtime data is guaranteed by the
// build-time script to match the Poi shape.
const OSM_POIS: Record<CorridorId, Poi[]> = {
  "ldn-par": OSM_LDN_PAR as unknown as Poi[],
  "ams-cph": OSM_AMS_CPH as unknown as Poi[],
  "ldn-bri": OSM_LDN_BRI as unknown as Poi[],
};

export const POIS_BY_CORRIDOR: Record<CorridorId, Poi[]> = {
  "ldn-par": mergePois(CURATED_LDN_PAR, OSM_POIS["ldn-par"]),
  "ams-cph": mergePois(CURATED_AMS_CPH, OSM_POIS["ams-cph"]),
  "ldn-bri": mergePois(CURATED_LDN_BRI, OSM_POIS["ldn-bri"]),
};
