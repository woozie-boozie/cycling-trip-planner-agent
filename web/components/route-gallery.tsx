"use client";

import { useState } from "react";
import { CORRIDORS, type Corridor } from "@/lib/corridors";
import { RouteCard } from "@/components/route-card";
import { RouteConfigForm } from "@/components/route-config-form";
import type { UserProfile } from "@/lib/types";

interface RouteGalleryProps {
  profile: UserProfile | null;
  /** Called with the assembled prompt string when the user clicks "Plan it". */
  onPlan: (prompt: string) => void;
}

/**
 * The empty-state hero. Two modes:
 *   1. Gallery — three Mapbox-thumbnail route cards in a responsive grid
 *   2. Configure — clicked-card expands to an inline form (month, daily km,
 *      accommodation), then submits a single curated prompt.
 *
 * The "type your own trip" path is handled by the chat input at the bottom
 * of the page — no redundant prompt section here.
 */
export function RouteGallery({ profile, onPlan }: RouteGalleryProps) {
  const [selected, setSelected] = useState<Corridor | null>(null);

  if (selected) {
    return (
      <div className="px-2 py-6">
        <RouteConfigForm
          corridor={selected}
          onBack={() => setSelected(null)}
          onPlan={(prompt) => {
            setSelected(null);
            onPlan(prompt);
          }}
        />
      </div>
    );
  }

  // Featured corridor = London → Paris (the headline corridor for the
  // brief; most-tested, full multi-variant data, recommended state).
  const featuredId: Corridor["id"] = "ldn-par";
  const featured = CORRIDORS.find((c) => c.id === featuredId);
  const others = CORRIDORS.filter((c) => c.id !== featuredId);

  return (
    <div className="w-full">
      <Hero profile={profile} />

      {/* Section header — quiet, more breathing room */}
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-[26px] font-bold leading-none tracking-[-0.025em] text-foreground sm:text-[28px]">
            Curated routes
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Three corridors seeded with real data. Pick one — or describe your own below.
          </p>
        </div>
        <span className="hidden font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70 sm:inline">
          3 corridors
        </span>
      </div>

      {/* Three-up: featured wider, two compact beside it at xl. At sm: stacked. */}
      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr_1fr]">
        {featured && (
          <RouteCard
            key={featured.id}
            corridor={featured}
            onSelect={setSelected}
            featured
          />
        )}
        <div className="grid gap-4 sm:grid-cols-2 xl:contents">
          {others.map((c) => (
            <RouteCard key={c.id} corridor={c} onSelect={setSelected} compact />
          ))}
        </div>
      </div>
    </div>
  );
}

function Hero({ profile }: { profile: UserProfile | null }) {
  const isReturning = Boolean(profile);
  const km = profile?.max_daily_km_comfort ?? 80;
  const experience = profile?.experience ?? null;
  const priorities = profile?.priorities ?? [];

  return (
    <div className="mb-12">
      {/* Profile snapshot — clean structured row above the headline.
          Replaces the right-rail ContextCard for everyday info. */}
      <div className="mb-7 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px]">
        <span className="inline-flex items-center gap-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
          {isReturning ? "profile loaded" : "system ready"}
        </span>

        {isReturning ? (
          <>
            <Meta label="Daily">
              <span className="font-semibold tabular-nums text-foreground">{km}</span>
              <span className="ml-0.5 text-muted-foreground">km</span>
            </Meta>
            {experience && (
              <Meta label="Experience">
                <span className="capitalize text-foreground">{experience}</span>
              </Meta>
            )}
            {priorities.length > 0 && (
              <Meta label="Priorities">
                <span className="flex flex-wrap items-center gap-1">
                  {priorities.slice(0, 3).map((p) => (
                    <span
                      key={p}
                      className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[10px] text-foreground/80"
                    >
                      {p.replace(/_/g, " ")}
                    </span>
                  ))}
                </span>
              </Meta>
            )}
          </>
        ) : (
          <Meta label="Sources">
            <span className="text-foreground">BRouter · ECMWF · Google Places · Anthropic</span>
          </Meta>
        )}
      </div>

      {/* Headline — one bold heading with a single coloured accent
          word. No italics anywhere — purely typographic weight + colour. */}
      <h1 className="max-w-[20ch] text-[44px] font-bold leading-[1.02] tracking-[-0.035em] text-foreground sm:text-[60px] md:text-[72px]">
        {isReturning ? (
          <>
            Pick your <span className="text-primary">next ride</span>.
          </>
        ) : (
          <>
            Plan a <span className="text-primary">real</span> multi-day cycling trip.
          </>
        )}
      </h1>

      <p className="mt-6 max-w-[52ch] text-[15px] leading-[1.6] text-muted-foreground sm:text-[17px]">
        {isReturning
          ? "BRouter distances. ECMWF climate norms. Curated overnight stops. A self-critique loop catches the agent's own mistakes before you do."
          : "Real BRouter distances, ECMWF climate norms, curated accommodation — and a self-critique loop that catches its own mistakes before you do."}
      </p>

      {/* Data-source dots — quiet provenance row below the paragraph */}
      {isReturning && (
        <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-muted-foreground">
          <span className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground/80">
            Real data
          </span>
          <Source dot="#FF3D14" label="BRouter" />
          <Source dot="#5C9AC4" label="ECMWF ERA5" />
          <Source dot="#18A957" label="Google Places" />
          <Source dot="#0A0A09" label="Anthropic" />
        </div>
      )}
    </div>
  );
}

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
        {label}
      </span>
      <span className="inline-flex items-center gap-1 text-[13px] text-foreground/90">
        {children}
      </span>
    </span>
  );
}

function Source({ dot, label }: { dot: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-foreground/80">
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: dot }}
        aria-hidden
      />
      {label}
    </span>
  );
}
