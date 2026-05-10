"use client";

import { useMemo, useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Corridor } from "@/lib/corridors";
import { staticMapUrl } from "@/lib/mapbox";

interface RouteConfigFormProps {
  corridor: Corridor;
  onBack: () => void;
  onPlan: (prompt: string) => void;
}

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;
type Month = (typeof MONTHS)[number];

const MONTH_FULL: Record<Month, string> = {
  Jan: "January",
  Feb: "February",
  Mar: "March",
  Apr: "April",
  May: "May",
  Jun: "June",
  Jul: "July",
  Aug: "August",
  Sep: "September",
  Oct: "October",
  Nov: "November",
  Dec: "December",
};

const KM_OPTIONS = [60, 80, 100, 120, 150] as const;
type KmTarget = (typeof KM_OPTIONS)[number];

type Accom = "camping" | "hostel" | "hotel";
const ACCOM_OPTIONS: { value: Accom; label: string; emoji: string }[] = [
  { value: "camping", label: "Camping", emoji: "⛺️" },
  { value: "hostel", label: "Hostels", emoji: "🛏️" },
  { value: "hotel", label: "Hotels", emoji: "🏨" },
];

interface FormState {
  month: Month;
  kmPerDay: KmTarget;
  accommodations: Accom[];
  hostelEveryN: number | null;
}

function buildPrompt(corridor: Corridor, state: FormState): string {
  const days = Math.max(1, Math.ceil(corridor.total_km / state.kmPerDay));
  const monthFull = MONTH_FULL[state.month];

  let accom: string;
  const list = state.accommodations;
  if (list.length === 0 || list.length === ACCOM_OPTIONS.length) {
    accom = "I'm flexible on accommodation — mix what makes sense";
  } else if (list.length === 1) {
    accom = `prefer ${list[0]} throughout`;
  } else {
    const labels = list.map((a) =>
      a === "camping" ? "camping" : a === "hostel" ? "hostels" : "hotels",
    );
    accom = `prefer ${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
  }

  const everyN =
    state.hostelEveryN && state.accommodations.includes("camping") && state.accommodations.includes("hostel")
      ? `, with a hostel every ${ordinal(state.hostelEveryN)} night`
      : "";

  return (
    `Plan a ${days}-day cycling trip ${corridor.label.toLowerCase()} ` +
    `(roughly ${corridor.total_km} km), ` +
    `${state.kmPerDay} km/day, ` +
    `${accom}${everyN}, traveling in ${monthFull}.`
  );
}

function ordinal(n: number): string {
  if (n === 1) return "1st";
  if (n === 2) return "2nd";
  if (n === 3) return "3rd";
  return `${n}th`;
}

export function RouteConfigForm({ corridor, onBack, onPlan }: RouteConfigFormProps) {
  const [state, setState] = useState<FormState>({
    month: "Jun",
    kmPerDay: 80,
    accommodations: ["camping", "hostel"],
    hostelEveryN: 3,
  });

  const thumb = staticMapUrl(corridor, { width: 800, height: 200 });
  const previewPrompt = useMemo(() => buildPrompt(corridor, state), [corridor, state]);

  const toggleAccom = (a: Accom) => {
    setState((prev) => {
      const has = prev.accommodations.includes(a);
      const next = has
        ? prev.accommodations.filter((x) => x !== a)
        : [...prev.accommodations, a];
      // Don't allow zero selected — fall back to camping if user clears all.
      return { ...prev, accommodations: next.length === 0 ? ["camping"] : next };
    });
  };

  const showHostelEveryN =
    state.accommodations.includes("camping") && state.accommodations.includes("hostel");

  return (
    <div className="mx-auto w-full max-w-2xl">
      {/* Header strip — back button + title + thumbnail */}
      <div className="mb-5 overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-center gap-2 border-b border-border/60 px-3 py-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onBack}
            className="-ml-1 text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden /> Back to routes
          </Button>
          <span className="ml-auto text-xs text-muted-foreground">
            {corridor.total_km} km
          </span>
        </div>
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb}
            alt={`${corridor.label} preview`}
            className="h-[120px] w-full object-cover"
          />
        ) : (
          <div className="flex h-[120px] w-full items-center justify-center bg-muted text-xs text-muted-foreground">
            map preview unavailable
          </div>
        )}
        <div className="px-4 py-3">
          <h2 className="text-lg font-semibold leading-tight tracking-tight text-foreground">
            {corridor.label}
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {corridor.description}
          </p>
        </div>
      </div>

      {/* When */}
      <FormBlock title="When are you riding?" hint="Pick your travel month — we'll pull historical climate norms.">
        <div className="flex flex-wrap gap-1.5">
          {MONTHS.map((m) => {
            const isOn = state.month === m;
            return (
              <button
                key={m}
                type="button"
                onClick={() => setState((s) => ({ ...s, month: m }))}
                className={chipClass(isOn)}
                aria-pressed={isOn}
              >
                {m}
              </button>
            );
          })}
        </div>
      </FormBlock>

      {/* Daily km */}
      <FormBlock
        title="Comfortable daily distance?"
        hint="The agent splits the route to match this — 80 km/day for casual, 120+ km/day for endurance riders."
      >
        <div className="flex flex-wrap gap-1.5">
          {KM_OPTIONS.map((k) => {
            const isOn = state.kmPerDay === k;
            return (
              <button
                key={k}
                type="button"
                onClick={() => setState((s) => ({ ...s, kmPerDay: k }))}
                className={chipClass(isOn)}
                aria-pressed={isOn}
              >
                {k} km/day
              </button>
            );
          })}
        </div>
      </FormBlock>

      {/* Accommodation */}
      <FormBlock title="Where will you sleep?" hint="Pick one or more — the agent honours the mix night-by-night.">
        <div className="flex flex-wrap gap-1.5">
          {ACCOM_OPTIONS.map((opt) => {
            const isOn = state.accommodations.includes(opt.value);
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => toggleAccom(opt.value)}
                className={chipClass(isOn)}
                aria-pressed={isOn}
              >
                <span className="mr-1" aria-hidden>{opt.emoji}</span>
                {opt.label}
              </button>
            );
          })}
        </div>

        {/* Hostel-every-N — appears only when camping + hostel are both selected */}
        {showHostelEveryN ? (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-muted/60 px-3 py-2 text-sm">
            <span className="text-muted-foreground">Hostel every</span>
            <div className="flex gap-1">
              {[2, 3, 4, 5].map((n) => {
                const isOn = state.hostelEveryN === n;
                return (
                  <button
                    key={n}
                    type="button"
                    onClick={() =>
                      setState((s) => ({ ...s, hostelEveryN: isOn ? null : n }))
                    }
                    className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium transition ${
                      isOn
                        ? "bg-primary text-primary-foreground"
                        : "bg-card text-foreground hover:bg-card/80"
                    }`}
                    aria-pressed={isOn}
                  >
                    {n}
                  </button>
                );
              })}
            </div>
            <span className="text-muted-foreground">
              {state.hostelEveryN ? `${ordinal(state.hostelEveryN)} night` : "off"}
            </span>
          </div>
        ) : null}
      </FormBlock>

      {/* Preview + submit */}
      <div className="mt-6 rounded-xl border border-border bg-card/60 p-4">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          The agent will plan
        </p>
        <p className="mt-1.5 text-sm leading-relaxed text-foreground">
          &ldquo;{previewPrompt}&rdquo;
        </p>
        <div className="mt-4 flex items-center justify-end gap-2">
          <Button
            type="button"
            onClick={() => onPlan(previewPrompt)}
            className="gap-1.5"
          >
            Plan it
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      </div>
    </div>
  );
}

function FormBlock({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-5">
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="mb-2.5 text-xs text-muted-foreground">{hint}</p>
      {children}
    </div>
  );
}

function chipClass(isOn: boolean): string {
  return [
    "rounded-full border px-3 py-1.5 text-xs font-medium transition",
    isOn
      ? "border-primary bg-primary text-primary-foreground"
      : "border-border bg-background text-foreground hover:border-primary/50 hover:bg-muted/60",
  ].join(" ");
}
