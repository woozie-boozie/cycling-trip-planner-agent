"use client";

import dynamic from "next/dynamic";
import { Map as MapIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import type { Corridor } from "@/lib/corridors";

interface RouteMapProps {
  corridor: Corridor | null;
  className?: string;
}

/*
 * Leaflet imports break on the server (touches window/document at module
 * level). Loading the inner component via next/dynamic with ssr:false keeps
 * the map purely client-side and avoids hydration mismatches.
 */
const RouteMapInner = dynamic(() => import("@/components/route-map-inner"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-md" />,
});

export function RouteMap({ corridor, className }: RouteMapProps) {
  return (
    <div className={`flex flex-col gap-2 ${className ?? ""}`}>
      <div className="flex items-center justify-between">
        <h4 className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Route map
        </h4>
        {corridor ? (
          <span className="font-mono text-[10px] tabular-nums text-muted-foreground/70">
            {corridor.total_km} km · {corridor.waypoints.length} waypoints
          </span>
        ) : null}
      </div>

      <div className="relative h-[260px] overflow-hidden rounded-md border border-border/40 bg-card">
        {corridor ? (
          <RouteMapInner corridor={corridor} />
        ) : (
          <EmptyMap />
        )}
      </div>

      {corridor ? (
        <p className="text-[10px] leading-relaxed text-muted-foreground/70">{corridor.description}</p>
      ) : null}
    </div>
  );
}

function EmptyMap() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
      <MapIcon className="h-5 w-5 text-muted-foreground/40" aria-hidden />
      <p className="max-w-[180px] text-[11px] leading-relaxed text-muted-foreground/70">
        The map appears once you mention a corridor — try London → Paris, Brighton, or Amsterdam → Copenhagen.
      </p>
    </div>
  );
}
