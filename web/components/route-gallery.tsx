"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";
import { CORRIDORS, type Corridor } from "@/lib/corridors";
import { RouteCard } from "@/components/route-card";
import { RouteConfigForm } from "@/components/route-config-form";
import type { UserProfile } from "@/lib/types";

interface RouteGalleryProps {
  profile: UserProfile | null;
  /** Called with the assembled prompt string when the user clicks "Plan it". */
  onPlan: (prompt: string) => void;
  /** Called when the user wants to type a free-form prompt instead. */
  onCustomPrompt: () => void;
}

/**
 * The empty-state hero. Two modes:
 *   1. Gallery — three Mapbox-thumbnail route cards in a responsive grid
 *   2. Configure — clicked-card expands to an inline form (month, daily km,
 *      accommodation), then submits a single curated prompt.
 *
 * The "type your own trip" path remains via a slim link below the gallery —
 * the chat input still accepts arbitrary text the moment the user starts
 * typing. The gallery is an *aid*, not a gate.
 */
export function RouteGallery({ profile, onPlan, onCustomPrompt }: RouteGalleryProps) {
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

  return (
    <div
      className="relative mx-auto w-full max-w-6xl px-3 py-10 sm:py-14"
      style={{
        backgroundImage:
          "radial-gradient(ellipse 80% 50% at 50% 0%, color-mix(in oklab, var(--primary) 8%, transparent) 0%, transparent 60%)",
      }}
    >
      <Hero profile={profile} />

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {CORRIDORS.map((c) => (
          <RouteCard key={c.id} corridor={c} onSelect={setSelected} />
        ))}
      </div>

      <div className="mt-10 flex flex-col items-center gap-3 text-center">
        <div className="flex items-center gap-3 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          <span className="h-px w-12 bg-border/70" aria-hidden />
          or
          <span className="h-px w-12 bg-border/70" aria-hidden />
        </div>
        <button
          type="button"
          onClick={onCustomPrompt}
          className="font-heading text-base italic text-foreground/85 transition-colors hover:text-primary"
          style={{ fontFamily: "var(--font-heading)" }}
        >
          describe your own trip ↓
        </button>
        <p className="text-[11px] text-muted-foreground">
          The agent handles arbitrary corridors with seed-data fallback.
        </p>
      </div>
    </div>
  );
}

function Hero({ profile }: { profile: UserProfile | null }) {
  const isReturning = Boolean(profile);

  return (
    <div className="mx-auto mb-9 flex max-w-3xl flex-col items-center text-center">
      <div className="mb-5 inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-primary">
        <Sparkles className="h-3 w-3" aria-hidden />
        Real route data · live weather · curated accommodation
      </div>
      <h1
        className="font-heading text-4xl font-normal leading-[1.05] tracking-tight text-foreground sm:text-5xl md:text-6xl"
        style={{ fontFamily: "var(--font-heading)" }}
      >
        {isReturning ? (
          <>
            <span className="italic">Welcome back.</span>{" "}
            <span className="italic text-primary">Pick a route.</span>
          </>
        ) : (
          <>
            <span className="italic">Tell me where you&apos;d like to</span>{" "}
            <span className="italic text-primary">ride.</span>
          </>
        )}
      </h1>
      <p className="mt-4 max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
        {isReturning
          ? `${profile!.max_daily_km_comfort} km/day comfort zone · the agent honours your saved preferences.`
          : `Pick one of the three signposted corridors below — or describe your own. The agent fans out 15+ tool calls per turn to plan it real.`}
      </p>
      {/* Provenance bar — shows the system's depth without screaming */}
      <div className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground/80">
        <span>BRouter routes</span>
        <span aria-hidden>·</span>
        <span>ECMWF ERA5 climate</span>
        <span aria-hidden>·</span>
        <span>Google Places</span>
        <span aria-hidden>·</span>
        <span>Anthropic Claude</span>
      </div>
    </div>
  );
}
