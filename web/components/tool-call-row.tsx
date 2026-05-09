"use client";

import {
  Bike,
  CloudRain,
  Hotel,
  Map,
  MountainSnow,
  CheckCircle2,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface ToolCallRowProps {
  name: string;
  isError: boolean;
  latencyMs?: number;
  iteration?: number;
}

// Icon per tool name — visual recognition for the trace.
const ICONS: Record<string, LucideIcon> = {
  get_route: Map,
  get_elevation_profile: MountainSnow,
  get_weather: CloudRain,
  find_accommodation: Hotel,
  critique_trip_plan: CheckCircle2,
};

const FRIENDLY_NAMES: Record<string, string> = {
  get_route: "Route",
  get_elevation_profile: "Elevation",
  get_weather: "Weather",
  find_accommodation: "Accommodation",
  critique_trip_plan: "Self-critique",
};

export function ToolCallRow({ name, isError, latencyMs, iteration }: ToolCallRowProps) {
  const Icon = ICONS[name] ?? Bike;
  const label = FRIENDLY_NAMES[name] ?? name;

  return (
    <div className="flex items-center gap-2 rounded-md border border-border/30 bg-background/40 px-2 py-1.5 text-xs">
      <Icon
        className={
          isError ? "h-3.5 w-3.5 shrink-0 text-destructive" : "h-3.5 w-3.5 shrink-0 text-primary"
        }
        aria-hidden
      />
      <span className="font-medium text-foreground">{label}</span>
      <code className="ml-auto font-mono text-[10px] text-muted-foreground/80">{name}</code>
      {iteration !== undefined ? (
        <Badge variant="secondary" className="font-mono text-[9px]">
          iter {iteration}
        </Badge>
      ) : null}
      {latencyMs !== undefined ? (
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground/70">
          {latencyMs}ms
        </span>
      ) : null}
      {isError ? <XCircle className="h-3 w-3 shrink-0 text-destructive" aria-hidden /> : null}
    </div>
  );
}
