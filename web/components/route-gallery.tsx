"use client";

import { useState } from "react";
import { Bike, Compass, Globe, MapPin } from "lucide-react";
import { CORRIDORS, type Corridor } from "@/lib/corridors";
import { RouteCard } from "@/components/route-card";
import { RouteConfigForm } from "@/components/route-config-form";
import type { UserProfile } from "@/lib/types";

interface PromptCard {
  header: string;
  text: string;
  Icon: typeof Bike;
}

const SAMPLE_PROMPTS: PromptCard[] = [
  {
    header: "Multi-day · charity",
    text: "Plan London → Paris on the Avenue Verte, 4 days at 100 km/day, June, camping mostly.",
    Icon: MapPin,
  },
  {
    header: "Weekend · scenic",
    text: "Best 2-day loop from Bristol with hilly climbs and pub stops.",
    Icon: Bike,
  },
  {
    header: "International · flat",
    text: "Amsterdam to Copenhagen, 8 days, prefer hostels, July.",
    Icon: Globe,
  },
  {
    header: "UK · classic",
    text: "London to Brighton this Saturday — what's the safest route at my 80 km/day pace?",
    Icon: Compass,
  },
];

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

  // Featured corridor = London → Paris (the headline corridor for the
  // brief; most-tested, full multi-variant data, recommended state).
  const featuredId: Corridor["id"] = "ldn-par";
  const featured = CORRIDORS.find((c) => c.id === featuredId);
  const others = CORRIDORS.filter((c) => c.id !== featuredId);

  return (
    <div className="w-full">
      <Hero profile={profile} />

      {/* Section header — left-aligned, modern */}
      <div className="mb-6 flex items-baseline justify-between gap-4">
        <h2 className="text-2xl font-bold tracking-tight text-foreground">
          Pick a route{" "}
          <span
            className="font-normal italic text-muted-foreground"
            style={{ fontFamily: "var(--font-heading)" }}
          >
            matched to your profile
          </span>
        </h2>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
          3 corridors · seeded data
        </span>
      </div>

      {/* Featured card spans the full main column; the two other corridors
          sit side-by-side below it. Less wasted vertical space + better
          visual rhythm than a single-column stack. */}
      <div className="space-y-4">
        {featured && (
          <RouteCard
            key={featured.id}
            corridor={featured}
            onSelect={setSelected}
            featured
          />
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          {others.map((c) => (
            <RouteCard key={c.id} corridor={c} onSelect={setSelected} compact />
          ))}
        </div>
      </div>

      {/* "Or describe your own" — section break */}
      <div className="mt-16 mb-6 flex items-center justify-center gap-4">
        <span className="h-px max-w-[80px] flex-1 bg-border" aria-hidden />
        <span className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          or describe your own
        </span>
        <span className="h-px max-w-[80px] flex-1 bg-border" aria-hidden />
      </div>

      <div className="mb-6 text-center">
        <h3 className="text-[28px] font-extrabold leading-tight tracking-[-0.025em] text-foreground sm:text-[32px]">
          Tell the agent{" "}
          <span
            className="font-normal italic text-primary"
            style={{ fontFamily: "var(--font-heading)" }}
          >
            where you&apos;d like
          </span>
          <br className="hidden sm:block" />
          to ride.
        </h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Arbitrary corridors are handled with seed-data fallback. Try one of these:
        </p>
      </div>

      <div className="mx-auto grid max-w-3xl gap-2.5 sm:grid-cols-2">
        {SAMPLE_PROMPTS.map((p, i) => (
          <PromptCardComponent
            key={i}
            prompt={p}
            onClick={() => onCustomPrompt()}
          />
        ))}
      </div>
    </div>
  );
}

function PromptCardComponent({
  prompt,
  onClick,
}: {
  prompt: PromptCard;
  onClick: () => void;
}) {
  const { Icon } = prompt;
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex items-start gap-3 rounded-xl border border-border bg-card p-4 text-left transition-all hover:-translate-y-0.5 hover:border-primary/50 hover:bg-primary/[0.04] hover:shadow-md"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/80 transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-mono text-[9.5px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
          {prompt.header}
        </span>
        <span className="mt-0.5 block text-[13px] font-medium leading-snug text-foreground">
          {prompt.text}
        </span>
      </span>
    </button>
  );
}

function Hero({ profile }: { profile: UserProfile | null }) {
  const isReturning = Boolean(profile);
  const km = profile?.max_daily_km_comfort ?? 80;

  return (
    <div className="mb-10">
      {/* Status pill — top-aligned, hot */}
      <div className="mb-5 inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/[0.06] px-3 py-1 font-mono text-[10.5px] font-semibold uppercase tracking-[0.12em] text-primary">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inset-0 animate-ping rounded-full bg-primary opacity-75" />
          <span className="relative h-1.5 w-1.5 rounded-full bg-primary" />
        </span>
        {isReturning ? `welcome back, akhil` : "live · production system"}
      </div>

      {/* Headline — bold sans + italic-serif accent flourishes */}
      <h1 className="text-[40px] font-extrabold leading-[0.95] tracking-[-0.035em] text-foreground sm:text-[52px] md:text-[60px]">
        {isReturning ? (
          <>
            The agent&apos;s{" "}
            <span
              className="font-normal italic text-foreground"
              style={{ fontFamily: "var(--font-heading)" }}
            >
              read
            </span>
            <br />
            your saved preferences.{" "}
            <span
              className="font-normal italic text-primary"
              style={{ fontFamily: "var(--font-heading)" }}
            >
              Now pick a route.
            </span>
          </>
        ) : (
          <>
            Plan a{" "}
            <span
              className="font-normal italic text-foreground"
              style={{ fontFamily: "var(--font-heading)" }}
            >
              real
            </span>{" "}
            multi-day cycling trip.{" "}
            <span
              className="font-normal italic text-primary"
              style={{ fontFamily: "var(--font-heading)" }}
            >
              In one chat.
            </span>
          </>
        )}
      </h1>

      <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-muted-foreground sm:text-[16px]">
        {isReturning
          ? `${km} km/day comfort zone. Camping over hotels. Real BRouter distances, ECMWF climate norms, curated accommodation — and a self-critique loop that catches its own mistakes before you do.`
          : `Real BRouter distances, ECMWF climate norms, curated accommodation — and a self-critique loop that catches its own mistakes before you do.`}
      </p>

      {/* Provenance tags */}
      <div className="mt-6 flex flex-wrap gap-1.5">
        <ProvenanceTag dot="#FF3D14" label="BRouter routes" />
        <ProvenanceTag dot="#5C9AC4" label="ECMWF ERA5 climate" />
        <ProvenanceTag dot="#18A957" label="Google Places POI" />
        <ProvenanceTag dot="#0A0A09" label="Anthropic Claude" />
      </div>
    </div>
  );
}

function ProvenanceTag({ dot, label }: { dot: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 font-mono text-[10.5px] font-medium text-foreground/85">
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: dot }}
        aria-hidden
      />
      {label}
    </span>
  );
}
