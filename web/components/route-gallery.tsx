"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowRight, ChevronDown } from "lucide-react";
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
  const [fromCity, setFromCity] = useState<string | null>(null);
  const [toCity, setToCity] = useState<string | null>(null);

  // --- Filter options derived from the catalog -----------------------------
  // "From" options = every city that appears as an endpoint in any corridor.
  // Catalog is bidirectional (the agent handles both directions), so a city
  // that's the END of one corridor is a valid START for the user's intent.
  const fromOptions = useMemo(() => endpointCities(CORRIDORS), []);

  // "To" options narrow when "From" is picked — only show reachable
  // destinations so the user can't construct an invalid pair via the UI.
  const toOptions = useMemo(() => {
    if (!fromCity) return fromOptions;
    return reachableFrom(CORRIDORS, fromCity);
  }, [fromCity, fromOptions]);

  // If "From" changes and the current "To" is no longer reachable from the
  // new "From", reset it so the UI stays self-consistent.
  useEffect(() => {
    if (toCity && !toOptions.includes(toCity)) {
      setToCity(null);
    }
  }, [toCity, toOptions]);

  // --- Filtered corridor list ---------------------------------------------
  const filtered = useMemo(() => {
    if (!fromCity && !toCity) return CORRIDORS;
    return CORRIDORS.filter((c) => {
      const start = c.waypoints[0]?.name;
      const end = c.waypoints[c.waypoints.length - 1]?.name;
      if (!start || !end) return false;
      const endpoints = new Set([start, end]);
      if (fromCity && !endpoints.has(fromCity)) return false;
      if (toCity && !endpoints.has(toCity)) return false;
      return true;
    });
  }, [fromCity, toCity]);

  if (selected) {
    return (
      <div className="px-2 py-6">
        <RouteConfigForm
          corridor={selected}
          anchorKm={profile?.max_daily_km_comfort ?? 80}
          onBack={() => setSelected(null)}
          onPlan={(prompt) => {
            setSelected(null);
            onPlan(prompt);
          }}
        />
      </div>
    );
  }

  // Featured corridor — London → Paris when no filter; otherwise the first
  // matching corridor in the filtered set (avoids "no featured card" gap).
  const featuredId: Corridor["id"] = "ldn-par";
  const featured = filtered.find((c) => c.id === featuredId) ?? filtered[0];
  const others = filtered.filter((c) => c.id !== featured?.id);

  const isFiltering = fromCity != null || toCity != null;
  const noMatch = fromCity != null && toCity != null && filtered.length === 0;

  return (
    <div className="w-full">
      <Hero profile={profile} />

      {/* Section header */}
      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-[26px] font-bold leading-none tracking-[-0.025em] text-foreground sm:text-[28px]">
            Curated routes
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {CORRIDORS.length} signposted corridors with real data. Pick one — or describe your own below.
          </p>
        </div>
        <span className="hidden font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70 sm:inline">
          {isFiltering ? `${filtered.length} of ${CORRIDORS.length}` : `${CORRIDORS.length} corridors`}
        </span>
      </div>

      {/* Filters row — From + To dropdowns + hint */}
      <RouteFilters
        fromCity={fromCity}
        toCity={toCity}
        fromOptions={fromOptions}
        toOptions={toOptions}
        onFromChange={setFromCity}
        onToChange={setToCity}
      />

      {/* Cards grid OR no-match empty state */}
      {noMatch ? (
        <NoMatchCallToChat
          fromCity={fromCity!}
          toCity={toCity!}
          onAsk={() => {
            const km = profile?.max_daily_km_comfort ?? 80;
            const prompt = `Plan a cycling trip from ${fromCity} to ${toCity}, ${km} km/day. Pick the most realistic month if you don't know my preference.`;
            onPlan(prompt);
          }}
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {featured && (
            <RouteCard
              key={featured.id}
              corridor={featured}
              onSelect={setSelected}
              featured
            />
          )}
          {others.map((c) => (
            <RouteCard key={c.id} corridor={c} onSelect={setSelected} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Filter helpers
// ---------------------------------------------------------------------------

/** All unique endpoint city names across the catalog, alphabetised. */
function endpointCities(corridors: Corridor[]): string[] {
  const set = new Set<string>();
  for (const c of corridors) {
    if (c.waypoints.length === 0) continue;
    set.add(c.waypoints[0].name);
    set.add(c.waypoints[c.waypoints.length - 1].name);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

/** Cities reachable from `fromCity` via any catalog corridor (either direction). */
function reachableFrom(corridors: Corridor[], fromCity: string): string[] {
  const set = new Set<string>();
  for (const c of corridors) {
    const start = c.waypoints[0]?.name;
    const end = c.waypoints[c.waypoints.length - 1]?.name;
    if (!start || !end) continue;
    if (start === fromCity) set.add(end);
    if (end === fromCity) set.add(start);
    // Loop corridor (same start + end) — let the user pick it explicitly.
    if (start === fromCity && end === fromCity) set.add(start);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface RouteFiltersProps {
  fromCity: string | null;
  toCity: string | null;
  fromOptions: string[];
  toOptions: string[];
  onFromChange: (city: string | null) => void;
  onToChange: (city: string | null) => void;
}

function RouteFilters({
  fromCity,
  toCity,
  fromOptions,
  toOptions,
  onFromChange,
  onToChange,
}: RouteFiltersProps) {
  const hasFilter = fromCity != null || toCity != null;
  return (
    <div className="mb-6 flex flex-wrap items-center gap-3">
      <FilterSelect
        label="From"
        value={fromCity}
        options={fromOptions}
        onChange={onFromChange}
      />
      <span className="text-foreground/40">→</span>
      <FilterSelect
        label="To"
        value={toCity}
        options={toOptions}
        onChange={onToChange}
      />

      {hasFilter && (
        <button
          type="button"
          onClick={() => {
            onFromChange(null);
            onToChange(null);
          }}
          className="text-[12px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        >
          clear
        </button>
      )}

      <span className="ml-auto inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
        Don&apos;t see your route?{" "}
        <span className="text-foreground/80">Type it in the chat below ↓</span>
      </span>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string | null;
  options: string[];
  onChange: (city: string | null) => void;
}) {
  return (
    <label className="group inline-flex items-center gap-2 rounded-full border border-border bg-card pl-3.5 pr-2 text-[13px] font-medium text-foreground transition-colors focus-within:border-foreground/40 hover:border-foreground/30">
      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
        {label}
      </span>
      <span className="relative inline-flex items-center">
        <select
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value || null)}
          className="appearance-none bg-transparent py-1.5 pr-6 text-foreground focus:outline-none"
        >
          <option value="">Any</option>
          {options.map((city) => (
            <option key={city} value={city}>
              {city}
            </option>
          ))}
        </select>
        <ChevronDown
          className="pointer-events-none absolute right-1 h-3.5 w-3.5 text-muted-foreground/70"
          aria-hidden
        />
      </span>
    </label>
  );
}

interface NoMatchProps {
  fromCity: string;
  toCity: string;
  onAsk: () => void;
}

function NoMatchCallToChat({ fromCity, toCity, onAsk }: NoMatchProps) {
  return (
    <div className="rounded-2xl border border-dashed border-border/80 bg-card px-8 py-12 text-center">
      <p className="text-[15px] font-semibold text-foreground">
        No curated route from {fromCity} to {toCity}.
      </p>
      <p className="mx-auto mt-2 max-w-[52ch] text-[13px] leading-[1.55] text-muted-foreground">
        Not a problem — the agent can plan ANY corridor from scratch using real BRouter
        distances and live accommodation data. Catalog routes just save a few tool calls
        and add a richer map; the planning is the same either way.
      </p>
      <button
        type="button"
        onClick={onAsk}
        className="mt-6 inline-flex items-center gap-2 rounded-full bg-foreground px-5 py-2.5 text-[13px] font-semibold text-background transition-colors hover:bg-foreground/85"
      >
        Ask the agent to plan {fromCity} → {toCity}
        <ArrowRight className="h-3.5 w-3.5" aria-hidden />
      </button>
      <p className="mt-3 text-[11px] text-muted-foreground/80">
        Or type your own prompt in the chat input below to refine the brief.
      </p>
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
