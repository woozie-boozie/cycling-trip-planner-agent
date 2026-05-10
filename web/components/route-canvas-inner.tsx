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
import { useEffect, useMemo } from "react";
import {
  CircleMarker,
  MapContainer,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

import { mapboxTileUrl } from "@/lib/mapbox";
import { LAYER_META, type Poi } from "@/lib/pois";

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

      {/* POI markers */}
      {pois.map((p, i) => {
        const meta = LAYER_META[p.layer];
        return (
          <CircleMarker
            key={`poi-${i}-${p.label}`}
            center={[p.lat, p.lon]}
            radius={7}
            pathOptions={{
              color: meta.color,
              fillColor: "#FFFFFF",
              fillOpacity: 1,
              weight: 2.5,
            }}
            eventHandlers={{
              click: () => onSelectPoi(p),
            }}
          >
            <Tooltip direction="top" offset={[0, -8]} opacity={0.95}>
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
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
