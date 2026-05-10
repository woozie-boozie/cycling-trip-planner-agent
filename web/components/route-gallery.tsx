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
    <div className="mx-auto w-full max-w-5xl px-2 py-6">
      <Hero profile={profile} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {CORRIDORS.map((c) => (
          <RouteCard key={c.id} corridor={c} onSelect={setSelected} />
        ))}
      </div>

      <div className="mt-6 text-center">
        <button
          type="button"
          onClick={onCustomPrompt}
          className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          or describe your own trip
        </button>
      </div>
    </div>
  );
}

function Hero({ profile }: { profile: UserProfile | null }) {
  const isReturning = Boolean(profile);

  return (
    <div className="mx-auto mb-7 flex max-w-2xl flex-col items-center text-center">
      <div className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-[11px] font-medium text-primary">
        <Sparkles className="h-3 w-3" aria-hidden />
        Real route data · live weather · curated accommodation
      </div>
      <h1
        className="font-heading text-3xl font-normal italic leading-[1.1] tracking-tight text-foreground sm:text-4xl"
        style={{ fontFamily: "var(--font-heading)" }}
      >
        {isReturning ? (
          <>
            Welcome back. <span className="text-primary">Pick a route.</span>
          </>
        ) : (
          <>
            Tell me where you&apos;d like to{" "}
            <span className="text-primary">ride.</span>
          </>
        )}
      </h1>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
        {isReturning
          ? `${profile!.max_daily_km_comfort} km/day comfort zone · agent honours your saved preferences.`
          : `Pick a route to start, then tell us when you're riding and how you like to sleep.`}
      </p>
    </div>
  );
}
