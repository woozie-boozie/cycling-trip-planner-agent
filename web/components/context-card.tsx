"use client";

import { Activity, MapPin, Sparkles } from "lucide-react";
import type { Corridor } from "@/lib/corridors";
import type { UserProfile } from "@/lib/types";

interface ContextCardProps {
  profile: UserProfile | null;
  /** True on empty state — affects which kind of context we show. */
  isEmpty: boolean;
  /** Corridor matched in the conversation, if any. */
  corridor: Corridor | null;
}

/**
 * Context companion card for the right rail. Sits below the dark
 * `LiveTracePanel` and uses the otherwise-empty space below it for
 * something productive:
 *
 *   - User profile summary (km/day comfort + priorities)
 *   - Real-data-source badges (BRouter, ECMWF, Google Places, Claude)
 *   - When a corridor is matched, a "currently planning" line
 *
 * Light/white card with quiet typography — visually balances the dark
 * trace panel above it without competing for attention.
 */
export function ContextCard({ profile, isEmpty, corridor }: ContextCardProps) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 shadow-paper">
      {/* Header row */}
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          Context · this session
        </span>
        <Sparkles className="h-3 w-3 text-primary" aria-hidden />
      </div>

      {/* Profile block */}
      {profile ? (
        <div className="mb-3 space-y-1.5 border-b border-border/60 pb-3">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[11px] text-muted-foreground">
              Daily comfort
            </span>
            <span
              className="font-heading text-lg italic leading-none text-foreground"
              style={{ fontFamily: "var(--font-heading)" }}
            >
              {profile.max_daily_km_comfort}
              <span className="ml-0.5 font-sans text-[11px] not-italic text-muted-foreground">
                km/day
              </span>
            </span>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-[11px] text-muted-foreground">Experience</span>
            <span className="font-mono text-[11px] capitalize text-foreground">
              {profile.experience}
            </span>
          </div>
          {profile.priorities && profile.priorities.length > 0 && (
            <div className="flex items-start justify-between gap-2 pt-1">
              <span className="shrink-0 text-[11px] text-muted-foreground">
                Priorities
              </span>
              <div className="flex flex-wrap justify-end gap-1">
                {profile.priorities.slice(0, 3).map((p) => (
                  <span
                    key={p}
                    className="rounded-full border border-border bg-muted px-1.5 py-0.5 font-mono text-[9.5px] text-foreground/85"
                  >
                    {p.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="mb-3 border-b border-border/60 pb-3 text-[11px] text-muted-foreground">
          Anonymous session — set up a profile from the header to enable
          personalised planning.
        </div>
      )}

      {/* Currently planning */}
      {corridor && (
        <div className="mb-3 flex items-start gap-2 border-b border-border/60 pb-3">
          <MapPin className="mt-0.5 h-3 w-3 shrink-0 text-primary" aria-hidden />
          <div className="min-w-0">
            <div className="font-mono text-[9.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
              Currently planning
            </div>
            <div
              className="mt-0.5 font-heading text-base italic leading-tight text-foreground"
              style={{ fontFamily: "var(--font-heading)" }}
            >
              {corridor.label}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
              {corridor.total_km} km · {corridor.waypoints.length} waypoints
            </div>
          </div>
        </div>
      )}

      {/* Real-data sources — replaces the previous big footer row */}
      <div>
        <div className="mb-2 flex items-center gap-1.5">
          <Activity className="h-3 w-3 text-primary" aria-hidden />
          <span className="font-mono text-[9.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            Real-data sources
          </span>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <SourceTag dot="#FF3D14" label="BRouter" sub="real bike routes" />
          <SourceTag dot="#5C9AC4" label="ECMWF ERA5" sub="climate norms" />
          <SourceTag dot="#18A957" label="Google Places" sub="POI + accom" />
          <SourceTag dot="#0A0A09" label="Anthropic" sub="claude-sonnet-4-5" />
        </div>
      </div>

      {/* Footer hint — only on empty state */}
      {isEmpty && (
        <div className="mt-3 border-t border-border/60 pt-3 text-[11px] leading-relaxed text-muted-foreground">
          Pick a route on the left, or describe your own. Multi-step reasoning
          + self-critique fires per turn.
        </div>
      )}
    </div>
  );
}

function SourceTag({
  dot,
  label,
  sub,
}: {
  dot: string;
  label: string;
  sub: string;
}) {
  return (
    <div className="flex items-start gap-1.5 rounded-md border border-border bg-bg-soft px-2 py-1.5">
      <span
        className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ background: dot }}
        aria-hidden
      />
      <div className="min-w-0">
        <div className="text-[11px] font-semibold leading-none text-foreground">
          {label}
        </div>
        <div className="mt-0.5 font-mono text-[9.5px] leading-none text-muted-foreground">
          {sub}
        </div>
      </div>
    </div>
  );
}
