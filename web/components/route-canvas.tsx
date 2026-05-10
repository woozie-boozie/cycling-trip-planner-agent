"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { LayerChips } from "@/components/layer-chips";
import { PoiSheet } from "@/components/poi-sheet";
import { Skeleton } from "@/components/ui/skeleton";
import type { Corridor } from "@/lib/corridors";
import { POIS_BY_CORRIDOR, type Poi, type PoiLayer } from "@/lib/pois";

interface RouteCanvasProps {
  corridor: Corridor;
  /** When false, renders without the layer-chip toolbar (for inline embedding) */
  showLayers?: boolean;
  /**
   * Optional override for the route polyline + waypoints. When provided
   * (e.g. user selected a specific variant in the comparison card), the
   * map traces these instead of the corridor's default waypoints.
   */
  variantWaypoints?: Array<{
    name: string;
    lat: number;
    lon: number;
    is_ferry?: boolean;
  }>;
  /** Optional title override for the header (e.g. "London → Paris · V16a Beauvais") */
  title?: string;
  /** Optional subtitle override (e.g. "364 km · 4 days") */
  subtitle?: string;
}

// Default-on layers when the map first appears. Heritage + wildlife +
// camp gives a cycling-product feel without over-cluttering.
const DEFAULT_ACTIVE: PoiLayer[] = ["heritage", "wildlife", "camp"];

const RouteCanvasInner = dynamic(
  () => import("@/components/route-canvas-inner"),
  {
    ssr: false,
    loading: () => <Skeleton className="h-full w-full" />,
  },
);

/**
 * Big interactive map for the visual response. Renders a real Mapbox
 * Outdoors basemap (roads, terrain, place labels) with the corridor
 * polyline + waypoint pins + POI markers layered on top.
 *
 * The Leaflet runtime is loaded via `next/dynamic` with `ssr: false` —
 * Leaflet touches `window` on import and crashes on the server. The
 * card chrome (header, layer chips, POI sheet) stays in this file;
 * only the geo renderer is split out into `route-canvas-inner.tsx`.
 */
export function RouteCanvas({
  corridor,
  showLayers = true,
  variantWaypoints,
  title,
  subtitle,
}: RouteCanvasProps) {
  const [active, setActive] = useState<Set<PoiLayer>>(
    () => new Set(DEFAULT_ACTIVE),
  );
  const [selectedPoi, setSelectedPoi] = useState<Poi | null>(null);

  // Use variant waypoints when provided (selection from RouteComparisonCard);
  // fall back to corridor's default waypoint set otherwise.
  const activeWaypoints = useMemo(
    () =>
      variantWaypoints && variantWaypoints.length > 0
        ? variantWaypoints
        : corridor.waypoints,
    [variantWaypoints, corridor.waypoints],
  );

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

  const visiblePois = useMemo(
    () => corridorPois.filter((p) => active.has(p.layer)),
    [corridorPois, active],
  );

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
              Route map ·{" "}
              {subtitle ?? `${corridor.total_km} km · ${activeWaypoints.length} waypoints`}
            </p>
            <h3 className="mt-0.5 text-xl font-bold leading-tight tracking-[-0.02em] text-foreground">
              {title ?? corridor.label}
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
      <div className="relative h-[440px]">
        <RouteCanvasInner
          waypoints={activeWaypoints}
          pois={visiblePois}
          onSelectPoi={setSelectedPoi}
        />

        {selectedPoi && (
          <PoiSheet poi={selectedPoi} onClose={() => setSelectedPoi(null)} />
        )}

        {visiblePois.length === 0 && active.size === 0 && (
          <div className="pointer-events-none absolute bottom-3 right-3 z-[1000] rounded-md border border-border bg-card/95 px-2.5 py-1 text-[11px] text-muted-foreground backdrop-blur-sm">
            Toggle a layer to see POIs
          </div>
        )}
      </div>
    </div>
  );
}
