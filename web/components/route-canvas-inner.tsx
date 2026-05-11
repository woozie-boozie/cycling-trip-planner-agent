"use client";

/**
 * Inner Leaflet map for the visual response. Never imported directly —
 * always loaded via `next/dynamic` with `ssr: false` from `route-canvas.tsx`.
 * Leaflet touches `window` on import and crashes on the server.
 *
 * Renders:
 *   - Mapbox Outdoors v12 raster tiles (real roads, terrain, place labels)
 *     with a graceful fallback to plain OSM when the Mapbox token is absent
 *   - Corridor polyline (halo + dashed top stroke, primary accent)
 *   - Waypoint markers — endpoints get a filled disc + permanent name label,
 *     intermediate stops get a small open ring, ferry stops get a blue ring
 *   - POI markers — coloured circle per LAYER_META, hover tooltip with the
 *     POI name, click fires `onSelectPoi` for the parent to open `PoiSheet`
 *   - `FitBounds` helper that reframes the map to encompass all waypoints
 *     and visible POIs whenever those change (variant switch / chip toggle)
 */

import L from "leaflet";
import {
  AlertTriangle,
  Bird,
  Camera,
  Cross,
  Droplet,
  Landmark,
  Ship,
  Tent,
  Utensils,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

import { mapboxTileUrl } from "@/lib/mapbox";
import { LAYER_META, type Poi, type PoiLayer } from "@/lib/pois";

// Render each Lucide layer icon to a static SVG string ONCE at module load.
// Embedded in Leaflet `divIcon` HTML — the SVG inherits `color: white` from
// the parent div so the stroke renders white against the coloured circle.
const POI_ICON_SVG: Record<PoiLayer, string> = {
  photo: renderToStaticMarkup(<Camera size={14} strokeWidth={2.5} />),
  wildlife: renderToStaticMarkup(<Bird size={14} strokeWidth={2.5} />),
  camp: renderToStaticMarkup(<Tent size={14} strokeWidth={2.5} />),
  food: renderToStaticMarkup(<Utensils size={14} strokeWidth={2.5} />),
  heritage: renderToStaticMarkup(<Landmark size={14} strokeWidth={2.5} />),
  repair: renderToStaticMarkup(<Wrench size={14} strokeWidth={2.5} />),
  water: renderToStaticMarkup(<Droplet size={14} strokeWidth={2.5} />),
  hospital: renderToStaticMarkup(<Cross size={14} strokeWidth={2.5} />),
  ferry: renderToStaticMarkup(<Ship size={14} strokeWidth={2.5} />),
  warning: renderToStaticMarkup(<AlertTriangle size={14} strokeWidth={2.5} />),
};

/** Build a Leaflet divIcon for a POI: coloured circle + centred Lucide icon. */
function poiDivIcon(layer: PoiLayer): L.DivIcon {
  const color = LAYER_META[layer].color;
  const html = `<div style="
    width:26px;height:26px;border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    color:white;background-color:${color};
    border:2px solid white;
    box-shadow:0 1px 3px rgba(20,19,15,0.35);
    cursor:pointer;
  ">${POI_ICON_SVG[layer]}</div>`;
  return L.divIcon({
    className: "",
    html,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

interface Waypoint {
  name: string;
  lat: number;
  lon: number;
  is_ferry?: boolean;
}

interface RouteCanvasInnerProps {
  waypoints: Waypoint[];
  pois: Poi[];
  onSelectPoi: (poi: Poi) => void;
}

function FitBounds({
  waypoints,
  pois,
}: {
  waypoints: Waypoint[];
  pois: Poi[];
}) {
  const map = useMap();
  useEffect(() => {
    const pts: L.LatLngTuple[] = [
      ...waypoints.map((w) => [w.lat, w.lon] as L.LatLngTuple),
      ...pois.map((p) => [p.lat, p.lon] as L.LatLngTuple),
    ];
    if (pts.length === 0) return;
    const bounds = L.latLngBounds(pts);
    map.fitBounds(bounds, { padding: [40, 40] });
  }, [waypoints, pois, map]);
  return null;
}

export default function RouteCanvasInner({
  waypoints,
  pois,
  onSelectPoi,
}: RouteCanvasInnerProps) {
  const tileUrl = mapboxTileUrl();

  const polylinePoints = useMemo<L.LatLngTuple[]>(
    () => waypoints.map((w) => [w.lat, w.lon]),
    [waypoints],
  );

  // Initial center — FitBounds reframes immediately after mount, but
  // MapContainer requires a starting center to render.
  const center = useMemo<L.LatLngTuple>(() => {
    if (waypoints.length === 0) return [50, 1];
    const first = waypoints[0];
    const last = waypoints[waypoints.length - 1];
    return [(first.lat + last.lat) / 2, (first.lon + last.lon) / 2];
  }, [waypoints]);

  return (
    <MapContainer
      center={center}
      zoom={6}
      scrollWheelZoom={false}
      className="h-full w-full"
      attributionControl
    >
      {tileUrl ? (
        <TileLayer
          attribution='&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url={tileUrl}
          tileSize={512}
          zoomOffset={-1}
          maxZoom={18}
        />
      ) : (
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
      )}

      <FitBounds waypoints={waypoints} pois={pois} />

      {/* Route polyline — soft halo + main stroke */}
      <Polyline
        positions={polylinePoints}
        pathOptions={{
          color: "#FF4A1C",
          weight: 10,
          opacity: 0.18,
        }}
      />
      <Polyline
        positions={polylinePoints}
        pathOptions={{
          color: "#FF4A1C",
          weight: 3,
          opacity: 0.95,
          dashArray: "6 6",
        }}
      />

      {/* Waypoint markers */}
      {waypoints.map((w, i) => {
        const isEndpoint = i === 0 || i === waypoints.length - 1;
        return (
          <CircleMarker
            key={`wp-${i}-${w.name}`}
            center={[w.lat, w.lon]}
            radius={isEndpoint ? 8 : w.is_ferry ? 6 : 4}
            pathOptions={{
              color: w.is_ferry && !isEndpoint ? "#0284c7" : "#14130F",
              fillColor: isEndpoint
                ? "#14130F"
                : w.is_ferry
                  ? "#38bdf8"
                  : "#FFFFFF",
              fillOpacity: 1,
              weight: isEndpoint ? 3 : 2,
            }}
          >
            <Tooltip direction="top" offset={[0, -10]} opacity={0.95}>
              <span className="text-[11px] font-semibold">{w.name}</span>
            </Tooltip>
          </CircleMarker>
        );
      })}

      {/* POI markers — Lucide icon inside a coloured circle */}
      {pois.map((p, i) => {
        const meta = LAYER_META[p.layer];
        return (
          <Marker
            key={`poi-${i}-${p.label}`}
            position={[p.lat, p.lon]}
            icon={poiDivIcon(p.layer)}
            eventHandlers={{
              click: () => onSelectPoi(p),
            }}
          >
            <Tooltip direction="top" offset={[0, -14]} opacity={0.95}>
              <div className="min-w-[120px]">
                <div
                  className="text-[9px] font-bold uppercase tracking-wider"
                  style={{ color: meta.color }}
                >
                  {meta.label}
                </div>
                <div className="text-[11px] font-semibold">{p.label}</div>
              </div>
            </Tooltip>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
