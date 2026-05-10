"use client";

import { useMemo, useState } from "react";
import { LayerChips } from "@/components/layer-chips";
import { PoiSheet } from "@/components/poi-sheet";
import type { Corridor } from "@/lib/corridors";
import {
  LAYER_META,
  POIS_BY_CORRIDOR,
  type Poi,
  type PoiLayer,
} from "@/lib/pois";

interface RouteCanvasProps {
  corridor: Corridor;
  /** When false, renders without the layer-chip toolbar (for inline embedding) */
  showLayers?: boolean;
}

const VIEW_W = 720;
const VIEW_H = 360;
const PADDING = 36;

// Default-on layers when the map first appears. Heritage + wildlife +
// camp gives the user a cycling-product feel from the off without
// over-cluttering. They can toggle others via the chips.
const DEFAULT_ACTIVE: PoiLayer[] = ["heritage", "wildlife", "camp"];

/**
 * Big SVG map for the visual response. Renders:
 *   - Corridor polyline (smoothed) with start/end pins
 *   - Through-waypoints as small dots with names
 *   - POI pins by category with hover tooltip + click-to-open sheet
 *   - LayerChips toolbar to toggle category visibility
 *
 * Pure SVG — no Leaflet, no JS map runtime. Lat/lon → SVG coords via
 * a per-corridor equirectangular projection (small-scale Mercator
 * approximation; aspect-ratio-corrected by cos(centerLat)).
 *
 * Visible only in visual mode. The Leaflet-based RouteMap stays in
 * the right-rail trace panel — different surface, different purpose.
 */
export function RouteCanvas({ corridor, showLayers = true }: RouteCanvasProps) {
  const [active, setActive] = useState<Set<PoiLayer>>(
    () => new Set(DEFAULT_ACTIVE),
  );
  const [hoverPoi, setHoverPoi] = useState<Poi | null>(null);
  const [selectedPoi, setSelectedPoi] = useState<Poi | null>(null);

  const corridorPois = useMemo(
    () => POIS_BY_CORRIDOR[corridor.id] ?? [],
    [corridor.id],
  );

  // Counts per layer (for the chip badges)
  const counts = useMemo(() => {
    const out: Partial<Record<PoiLayer, number>> = {};
    for (const p of corridorPois) {
      out[p.layer] = (out[p.layer] ?? 0) + 1;
    }
    return out;
  }, [corridorPois]);

  // Project all corridor lat/lon + POI lat/lon → SVG coords.
  const projected = useMemo(() => {
    const allLats = [
      ...corridor.waypoints.map((w) => w.lat),
      ...corridorPois.map((p) => p.lat),
    ];
    const allLons = [
      ...corridor.waypoints.map((w) => w.lon),
      ...corridorPois.map((p) => p.lon),
    ];
    const minLat = Math.min(...allLats);
    const maxLat = Math.max(...allLats);
    const minLon = Math.min(...allLons);
    const maxLon = Math.max(...allLons);

    // Equirectangular with cos(centerLat) correction so the route
    // doesn't look squished horizontally at northern latitudes.
    const centerLat = (minLat + maxLat) / 2;
    const lonScale = Math.cos((centerLat * Math.PI) / 180);

    const lonSpan = (maxLon - minLon) * lonScale || 1;
    const latSpan = maxLat - minLat || 1;

    // Fit-to-bounds with PADDING; keep aspect by shrinking the wider
    // axis so the map fills the viewBox without distorting.
    const usableW = VIEW_W - PADDING * 2;
    const usableH = VIEW_H - PADDING * 2;
    const scaleX = usableW / lonSpan;
    const scaleY = usableH / latSpan;
    const scale = Math.min(scaleX, scaleY);

    const projW = lonSpan * scale;
    const projH = latSpan * scale;
    const offsetX = (VIEW_W - projW) / 2;
    const offsetY = (VIEW_H - projH) / 2;

    const project = (lat: number, lon: number) => {
      const x = offsetX + (lon - minLon) * lonScale * scale;
      const y = offsetY + (maxLat - lat) * scale; // y flipped: north is up
      return { x, y };
    };

    return {
      project,
      waypoints: corridor.waypoints.map((w) => ({
        ...w,
        ...project(w.lat, w.lon),
      })),
      pois: corridorPois.map((p) => ({ ...p, ...project(p.lat, p.lon) })),
    };
  }, [corridor, corridorPois]);

  // Smoothed polyline through waypoints
  const polylinePath = useMemo(() => {
    const pts = projected.waypoints;
    if (pts.length < 2) return "";
    let d = `M ${pts[0].x.toFixed(2)} ${pts[0].y.toFixed(2)}`;
    for (let i = 1; i < pts.length; i++) {
      const prev = pts[i - 1];
      const curr = pts[i];
      const mx = (prev.x + curr.x) / 2;
      const my = (prev.y + curr.y) / 2;
      d += ` Q ${mx.toFixed(2)} ${my.toFixed(2)} ${curr.x.toFixed(2)} ${curr.y.toFixed(2)}`;
    }
    return d;
  }, [projected.waypoints]);

  const visiblePois = projected.pois.filter((p) => active.has(p.layer));

  const toggleLayer = (k: PoiLayer) => {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  };

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      {/* Header */}
      <div className="flex flex-col gap-3 border-b border-border/60 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Route map · {corridor.total_km} km · {corridor.waypoints.length}{" "}
              waypoints
            </p>
            <h3
              className="font-heading mt-0.5 text-xl italic leading-tight text-foreground"
              style={{ fontFamily: "var(--font-heading)" }}
            >
              {corridor.label}
            </h3>
          </div>
          <span className="font-mono text-[11px] text-muted-foreground">
            visual
          </span>
        </div>
        {showLayers && (
          <LayerChips active={active} counts={counts} onToggle={toggleLayer} />
        )}
      </div>

      {/* Map */}
      <div className="relative bg-[#F6F4EE]">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="block w-full"
          preserveAspectRatio="xMidYMid meet"
          style={{ maxHeight: 420 }}
          onClick={() => setSelectedPoi(null)}
        >
          <defs>
            <pattern
              id="map-grain"
              width="3"
              height="3"
              patternUnits="userSpaceOnUse"
            >
              <circle cx="1" cy="1" r="0.3" fill="rgba(20,19,15,0.05)" />
            </pattern>
          </defs>
          <rect width={VIEW_W} height={VIEW_H} fill="url(#map-grain)" />

          {/* Polyline — soft halo + main line */}
          <path
            d={polylinePath}
            fill="none"
            stroke="var(--primary)"
            strokeWidth="9"
            strokeLinecap="round"
            opacity="0.16"
          />
          <path
            d={polylinePath}
            fill="none"
            stroke="var(--primary)"
            strokeWidth="2.6"
            strokeLinecap="round"
            strokeDasharray="6 4"
          />

          {/* Through-waypoints (small dots) */}
          {projected.waypoints.map((w, i) => {
            const isFirst = i === 0;
            const isLast = i === projected.waypoints.length - 1;
            if (isFirst || isLast) return null;
            return (
              <g key={`wp-${i}`}>
                <circle
                  cx={w.x}
                  cy={w.y}
                  r={3.2}
                  fill="white"
                  stroke="var(--foreground)"
                  strokeWidth="1.3"
                />
                {w.is_ferry && (
                  <circle
                    cx={w.x}
                    cy={w.y}
                    r={6}
                    fill="none"
                    stroke="var(--primary)"
                    strokeWidth="1"
                    strokeDasharray="2 2"
                    opacity="0.6"
                  />
                )}
                <text
                  x={w.x + 7}
                  y={w.y + 3.5}
                  fontSize="10"
                  fontFamily="var(--font-sans)"
                  fontWeight="500"
                  fill="var(--foreground)"
                  opacity="0.75"
                >
                  {w.name}
                </text>
              </g>
            );
          })}

          {/* POI pins */}
          {visiblePois.map((p, i) => {
            const meta = LAYER_META[p.layer];
            const isHovered = hoverPoi === p;
            const isSelected = selectedPoi === p;
            const r = isHovered || isSelected ? 8 : 6;
            return (
              <g
                key={`poi-${i}`}
                transform={`translate(${p.x}, ${p.y})`}
                style={{ cursor: "pointer" }}
                onMouseEnter={() => setHoverPoi(p)}
                onMouseLeave={() => setHoverPoi(null)}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedPoi(p);
                }}
              >
                {(isHovered || isSelected) && (
                  <circle
                    r={r + 4}
                    fill={meta.color}
                    opacity="0.18"
                  />
                )}
                <circle
                  r={r}
                  fill="white"
                  stroke={meta.color}
                  strokeWidth="1.6"
                />
                <circle r={r * 0.45} fill={meta.color} />
              </g>
            );
          })}

          {/* Start/end pins (drawn on top) */}
          {projected.waypoints.map((w, i) => {
            const isFirst = i === 0;
            const isLast = i === projected.waypoints.length - 1;
            if (!isFirst && !isLast) return null;
            return (
              <g key={`endpoint-${i}`}>
                <circle
                  cx={w.x}
                  cy={w.y}
                  r={11}
                  fill="var(--foreground)"
                  opacity="0.14"
                />
                <circle
                  cx={w.x}
                  cy={w.y}
                  r={8}
                  fill="var(--foreground)"
                  stroke="white"
                  strokeWidth="2"
                />
                <text
                  x={w.x}
                  y={w.y + 3}
                  textAnchor="middle"
                  fontSize="10"
                  fontFamily="var(--font-mono)"
                  fontWeight="700"
                  fill="white"
                >
                  {isFirst ? "A" : "B"}
                </text>
                <text
                  x={isFirst ? w.x - 14 : w.x + 14}
                  y={w.y + 4}
                  textAnchor={isFirst ? "end" : "start"}
                  fontSize="11"
                  fontFamily="var(--font-sans)"
                  fontWeight="700"
                  fill="var(--foreground)"
                >
                  {w.name}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Hover tooltip (DOM-based, positioned over the map) */}
        {hoverPoi && !selectedPoi && (
          <PoiHoverTip poi={hoverPoi} projected={projected.pois.find((q) => q === hoverPoi)} />
        )}

        {/* Click-to-open detail sheet */}
        {selectedPoi && (
          <PoiSheet poi={selectedPoi} onClose={() => setSelectedPoi(null)} />
        )}

        {/* Empty-state hint */}
        {visiblePois.length === 0 && active.size === 0 && (
          <div className="absolute bottom-3 right-3 rounded-md border border-border bg-card/95 px-2.5 py-1 text-[11px] text-muted-foreground backdrop-blur-sm">
            Toggle a layer to see POIs
          </div>
        )}
      </div>
    </div>
  );
}

interface ProjectedPoint {
  x: number;
  y: number;
}

function PoiHoverTip({
  poi,
  projected,
}: {
  poi: Poi;
  projected: ProjectedPoint | undefined;
}) {
  if (!projected) return null;
  const meta = LAYER_META[poi.layer];
  const xPct = (projected.x / VIEW_W) * 100;
  const yPct = (projected.y / VIEW_H) * 100;
  return (
    <div
      className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-[calc(100%+10px)] rounded-md bg-foreground px-2.5 py-1.5 text-xs text-background shadow-lg"
      style={{ left: `${xPct}%`, top: `${yPct}%`, maxWidth: 200 }}
    >
      <div
        className="text-[9px] font-bold uppercase tracking-wider"
        style={{ color: meta.color }}
      >
        {meta.label}
      </div>
      <div className="font-semibold">{poi.label}</div>
      <div className="mt-0.5 line-clamp-2 text-[11px] opacity-80">
        {poi.description}
      </div>
    </div>
  );
}
