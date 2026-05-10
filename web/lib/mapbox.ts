/**
 * Mapbox Static Images URL builder.
 *
 * One pure function per public-facing helper — no Mapbox JS SDK, no client
 * runtime. The URL goes straight into an <img src> tag and the browser
 * fetches the rendered PNG directly.
 *
 * Why Mapbox Static Images and not the interactive `react-leaflet` map for
 * thumbnails:
 *   - <img>-tag rendering is one network request, no JS parse, no Leaflet
 *     bootstrap, no tile-layer flash. Comfortably retina-sharp on 600x280.
 *   - The `outdoors-v12` style ships contour lines, terrain shading, and
 *     route-relevant detail (passes, ferries, paths) — far better-suited to
 *     cycling-route preview than Google Maps' flatter aesthetic.
 *   - Path overlays use Mapbox's path-encoding syntax with the standard
 *     polyline algorithm — same algorithm Google Maps uses, so the encoder
 *     is small and well-known.
 *
 * Token: read from NEXT_PUBLIC_MAPBOX_TOKEN at module load. If absent,
 * builders return null so callers can gracefully degrade to a placeholder.
 */

import type { Corridor } from "./corridors";

const STYLE = "outdoors-v12";
const PATH_STROKE_WIDTH = 4;
const PATH_HEX = "f97316"; // amber-orange — matches the app's primary accent
const PATH_OPACITY = 0.85;
const PADDING = 30; // px around the rendered overlay

const TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN ?? "";

/**
 * Encode a coordinate sequence as a Google polyline string (the standard
 * format Mapbox accepts in `path-...(<polyline>)` overlays).
 *
 * Reference algorithm: https://developers.google.com/maps/documentation/utilities/polylinealgorithm
 */
function encodePolyline(coords: [number, number][]): string {
  let lastLat = 0;
  let lastLng = 0;
  let result = "";

  for (const [lat, lng] of coords) {
    const intLat = Math.round(lat * 1e5);
    const intLng = Math.round(lng * 1e5);
    result += encodeNumber(intLat - lastLat);
    result += encodeNumber(intLng - lastLng);
    lastLat = intLat;
    lastLng = intLng;
  }

  return result;
}

function encodeNumber(num: number): string {
  let n = num < 0 ? ~(num << 1) : num << 1;
  let result = "";
  while (n >= 0x20) {
    result += String.fromCharCode((0x20 | (n & 0x1f)) + 63);
    n >>= 5;
  }
  result += String.fromCharCode(n + 63);
  return result;
}

interface StaticMapOptions {
  width?: number;
  height?: number;
  retina?: boolean;
  /** When true, also draws labelled start (A) and end (B) pins. */
  withPins?: boolean;
}

/**
 * Build the URL for a static Mapbox image showing the corridor's polyline.
 *
 * Returns `null` if the token isn't set so callers can render a fallback.
 */
export function staticMapUrl(
  corridor: Corridor,
  opts: StaticMapOptions = {},
): string | null {
  if (!TOKEN) return null;

  const { width = 600, height = 280, retina = true, withPins = true } = opts;

  const coords: [number, number][] = corridor.waypoints.map((w) => [
    w.lat,
    w.lon,
  ]);
  const polyline = encodePolyline(coords);

  const overlays: string[] = [
    `path-${PATH_STROKE_WIDTH}+${PATH_HEX}-${PATH_OPACITY}(${encodeURIComponent(polyline)})`,
  ];

  if (withPins) {
    const start = corridor.waypoints[0];
    const end = corridor.waypoints[corridor.waypoints.length - 1];
    // pin-s-{label}+{hex} renders a small labelled pin. Letters render in white.
    overlays.push(`pin-s-a+${PATH_HEX}(${start.lon},${start.lat})`);
    overlays.push(`pin-s-b+${PATH_HEX}(${end.lon},${end.lat})`);
  }

  const dpi = retina ? "@2x" : "";
  const overlayPart = overlays.join(",");

  // `auto` lets Mapbox compute the bbox from the overlay extents — exactly
  // what we want so each corridor frames itself nicely without us computing
  // bounds client-side.
  return (
    `https://api.mapbox.com/styles/v1/mapbox/${STYLE}/static/` +
    `${overlayPart}/auto/${width}x${height}${dpi}` +
    `?access_token=${TOKEN}&padding=${PADDING}`
  );
}

export function hasMapboxToken(): boolean {
  return TOKEN.length > 0;
}
