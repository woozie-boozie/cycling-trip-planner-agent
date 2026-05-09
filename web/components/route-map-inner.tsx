"use client";

/**
 * Inner Leaflet map — never imported directly, only loaded via `next/dynamic`
 * with `ssr: false` from route-map.tsx. Leaflet touches `window` and the DOM
 * on import, so it crashes on the server.
 */

import { useEffect, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

import type { Corridor, CorridorWaypoint } from "@/lib/corridors";
import { corridorBounds } from "@/lib/corridors";

interface RouteMapInnerProps {
  corridor: Corridor;
}

/**
 * Re-fits the map to the corridor bounds whenever it changes.
 * Lives inside MapContainer so it has access to the map instance.
 */
function FitBounds({ corridor }: { corridor: Corridor }) {
  const map = useMap();
  useEffect(() => {
    const bounds = corridorBounds(corridor);
    map.fitBounds(bounds, { padding: [24, 24] });
  }, [corridor, map]);
  return null;
}

export default function RouteMapInner({ corridor }: RouteMapInnerProps) {
  const polylinePoints = useMemo<[number, number][]>(
    () => corridor.waypoints.map((w) => [w.lat, w.lon]),
    [corridor],
  );

  // Initial center is roughly the midpoint of the first and last waypoint —
  // FitBounds re-frames immediately after mount.
  const center = useMemo<[number, number]>(() => {
    const wps = corridor.waypoints;
    return [
      (wps[0].lat + wps[wps.length - 1].lat) / 2,
      (wps[0].lon + wps[wps.length - 1].lon) / 2,
    ];
  }, [corridor]);

  return (
    <MapContainer
      center={center}
      zoom={6}
      scrollWheelZoom={false}
      className="h-full w-full rounded-md"
      attributionControl
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds corridor={corridor} />

      {/* The connecting line. amber to match our palette. */}
      <Polyline
        positions={polylinePoints}
        pathOptions={{
          color: "#E59C5A",
          weight: 3,
          opacity: 0.85,
          dashArray: "0",
        }}
      />

      {/* One marker per waypoint. Ferry stops get a different color. */}
      {corridor.waypoints.map((w: CorridorWaypoint, idx) => (
        <CircleMarker
          key={`${w.name}-${idx}`}
          center={[w.lat, w.lon]}
          radius={w.is_ferry ? 7 : 6}
          pathOptions={{
            color: w.is_ferry ? "#0284c7" : "#1F4030",
            fillColor: w.is_ferry ? "#38bdf8" : "#E59C5A",
            fillOpacity: 0.9,
            weight: 2,
          }}
        >
          <Tooltip direction="top" offset={[0, -8]} opacity={0.95} permanent={false}>
            <div className="text-[11px]">
              <div className="font-semibold">
                {w.name}
                <span className="ml-1 font-normal text-[10px] text-slate-500">
                  · {w.country}
                </span>
              </div>
              <div className="text-[10px] text-slate-600">
                {w.km_from_start} km from start
                {w.is_ferry ? " · ferry" : ""}
              </div>
            </div>
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
