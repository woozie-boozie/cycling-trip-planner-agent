"use client";

import { useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Calendar,
  Check,
  Compass,
  Hotel,
  Tent,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Corridor } from "@/lib/corridors";
import { staticMapUrl } from "@/lib/mapbox";
import { ROUTE_DETAILS } from "@/lib/route-details";

interface RouteConfigFormProps {
  corridor: Corridor;
  /** The rider's stated comfortable daily distance, captured at onboarding
   *  via `UserProfile.max_daily_km_comfort`. Anchors the three relative
   *  pace options (Easy / Achievable / Challenging). Falls back to 80 km
   *  when no profile exists yet. */
  anchorKm: number;
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

const SEASON_HINT: Record<Month, { tone: string; tag: string }> = {
  Dec: { tone: "winter", tag: "cold · short days" },
  Jan: { tone: "winter", tag: "cold · short days" },
  Feb: { tone: "winter", tag: "cold · short days" },
  Mar: { tone: "spring", tag: "mild · changeable" },
  Apr: { tone: "spring", tag: "mild · changeable" },
  May: { tone: "spring", tag: "mild · long days" },
  Jun: { tone: "summer", tag: "warm · prime season" },
  Jul: { tone: "summer", tag: "warm · prime season" },
  Aug: { tone: "summer", tag: "warm · prime season" },
  Sep: { tone: "autumn", tag: "cool · golden light" },
  Oct: { tone: "autumn", tag: "cool · wet possible" },
  Nov: { tone: "autumn", tag: "cool · wet · short days" },
};

/**
 * Relative pace bands anchored on the rider's stated daily distance.
 *
 * The previous design offered five fixed chips (60/80/100/120/150 km) which
 * (a) asked the user to re-state their pace after onboarding had already
 * captured it, and (b) frequently presented options that resolved to the
 * same day count for the route at hand (e.g. 100 vs 120 km/day on a 364 km
 * trip — both 4 days). Real cyclists called this out as noise. Anchoring
 * on `max_daily_km_comfort` and showing the resulting day count inline
 * makes the trade-off visible before commit.
 */
const PACE_CHOICES = ["easy", "achievable", "challenging"] as const;
type PaceChoice = (typeof PACE_CHOICES)[number];

const PACE_MULTIPLIER: Record<PaceChoice, number> = {
  easy: 0.7,
  achievable: 1.0,
  challenging: 1.25,
};

const PACE_LABEL: Record<PaceChoice, string> = {
  easy: "Easy",
  achievable: "Achievable",
  challenging: "Challenging",
};

const PACE_HINT: Record<PaceChoice, string> = {
  easy: "comfortably under your stated pace · more rest",
  achievable: "your stated pace",
  challenging: "a notch above · fewer days, real effort",
};

function paceKm(choice: PaceChoice, anchorKm: number): number {
  // Floor at 20 km/day so an anchor of, say, 25 km doesn't produce a 17 km
  // "easy" band that splits short corridors into too many tiny days.
  return Math.max(20, Math.round(anchorKm * PACE_MULTIPLIER[choice]));
}

function paceDays(choice: PaceChoice, anchorKm: number, totalKm: number): number {
  return Math.max(1, Math.ceil(totalKm / paceKm(choice, anchorKm)));
}

type Accom = "camping" | "hostel" | "hotel";
interface AccomOption {
  value: Accom;
  label: string;
  hint: string;
  Icon: typeof Tent;
}
const ACCOM_OPTIONS: AccomOption[] = [
  {
    value: "camping",
    label: "Camping",
    hint: "Lightweight · cheapest · self-sufficient",
    Icon: Tent,
  },
  {
    value: "hostel",
    label: "Hostels",
    hint: "Beds & showers · social · mid-budget",
    Icon: Users,
  },
  {
    value: "hotel",
    label: "Hotels",
    hint: "Comfort · breakfast · higher cost",
    Icon: Hotel,
  },
];

interface FormState {
  month: Month;
  paceChoice: PaceChoice;
  accommodations: Accom[];
}

const STEPS = ["When", "Distance", "Stay"] as const;

function buildPrompt(corridor: Corridor, state: FormState, anchorKm: number): string {
  const kmPerDay = paceKm(state.paceChoice, anchorKm);
  const days = Math.max(1, Math.ceil(corridor.total_km / kmPerDay));
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

  return (
    `Plan a ${days}-day cycling trip ${corridor.label.toLowerCase()} ` +
    `(roughly ${corridor.total_km} km), ` +
    `${kmPerDay} km/day, ` +
    `${accom}, traveling in ${monthFull}.`
  );
}

export function RouteConfigForm({ corridor, anchorKm, onBack, onPlan }: RouteConfigFormProps) {
  const [step, setStep] = useState(0);
  const [state, setState] = useState<FormState>({
    month: "Jun",
    paceChoice: "achievable",
    accommodations: ["camping", "hostel"],
  });

  const kmPerDay = paceKm(state.paceChoice, anchorKm);
  const days = Math.max(1, Math.ceil(corridor.total_km / kmPerDay));
  const previewPrompt = useMemo(
    () => buildPrompt(corridor, state, anchorKm),
    [corridor, state, anchorKm],
  );

  const toggleAccom = (a: Accom) => {
    setState((prev) => {
      const has = prev.accommodations.includes(a);
      const next = has
        ? prev.accommodations.filter((x) => x !== a)
        : [...prev.accommodations, a];
      return { ...prev, accommodations: next.length === 0 ? ["camping"] : next };
    });
  };

  const isLast = step === STEPS.length - 1;
  const isFirst = step === 0;

  return (
    <div className="mx-auto w-full max-w-3xl">
      {/* Back bar */}
      <button
        type="button"
        onClick={onBack}
        className="mb-5 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-3 w-3" aria-hidden /> Back to routes
      </button>

      {/* Hero — map + title */}
      <RouteHero corridor={corridor} />

      {/* Progress strip */}
      <ProgressBar step={step} total={STEPS.length} labels={STEPS} />

      {/* Step content — keyed remount for fade/slide animation */}
      <div
        key={step}
        className="animate-in fade-in slide-in-from-bottom-2 duration-400"
      >
        {step === 0 && (
          <WhenStep
            value={state.month}
            onChange={(m) => setState((s) => ({ ...s, month: m }))}
          />
        )}
        {step === 1 && (
          <DistanceStep
            value={state.paceChoice}
            anchorKm={anchorKm}
            totalKm={corridor.total_km}
            onChange={(c) => setState((s) => ({ ...s, paceChoice: c }))}
          />
        )}
        {step === 2 && (
          <SleepStep
            selected={state.accommodations}
            onToggle={toggleAccom}
          />
        )}
      </div>

      {/* Live prompt preview — exactly what the agent receives, updating
          as the user picks. Replaces a duplicated step-summary strip. */}
      <PromptPreview
        corridor={corridor}
        state={state}
        days={days}
        kmPerDay={kmPerDay}
      />

      {/* Footer nav */}
      <div className="mt-6 flex items-center justify-between">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={isFirst}
          className="text-muted-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Back
        </Button>

        {isLast ? (
          <Button
            type="button"
            onClick={() => onPlan(previewPrompt)}
            className="gap-1.5 px-5"
            size="lg"
          >
            <Compass className="h-4 w-4" aria-hidden />
            Plan this trip
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        ) : (
          <Button
            type="button"
            onClick={() => setStep((s) => s + 1)}
            className="gap-1.5"
          >
            Next <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hero — compact map + corridor headline
// ---------------------------------------------------------------------------

function RouteHero({ corridor }: { corridor: Corridor }) {
  const thumb = staticMapUrl(corridor, { width: 1200, height: 220 });
  const details = ROUTE_DETAILS[corridor.id];

  return (
    <div className="mb-8 overflow-hidden rounded-2xl border border-border/80 bg-card shadow-paper">
      <div className="relative h-[140px] w-full overflow-hidden bg-muted">
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb}
            alt={`${corridor.label} preview`}
            className="h-full w-full object-cover"
          />
        ) : null}
        <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent" />
      </div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-[22px] font-bold leading-tight tracking-[-0.02em] text-foreground">
            {corridor.label.split("→").map((p, i, arr) => (
              <span key={i}>
                {p.trim()}
                {i < arr.length - 1 && (
                  <span className="mx-1.5 font-normal text-primary">→</span>
                )}
              </span>
            ))}
          </h2>
          <p className="mt-0.5 text-[12.5px] leading-snug text-muted-foreground">
            {corridor.description}
          </p>
        </div>
        <div className="flex shrink-0 items-baseline gap-3 font-mono text-[11px] tabular-nums text-muted-foreground">
          <span>
            <strong className="font-semibold text-foreground">{corridor.total_km}</strong> km
          </span>
          <span>·</span>
          <span>
            ↑<strong className="font-semibold text-foreground">{details.total_climb_m.toLocaleString()}</strong> m
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Progress bar — animated dots + labels
// ---------------------------------------------------------------------------

function ProgressBar({
  step,
  total,
  labels,
}: {
  step: number;
  total: number;
  labels: readonly string[];
}) {
  return (
    <div className="mb-8 flex items-center gap-3">
      {labels.map((label, i) => {
        const isActive = i === step;
        const isDone = i < step;
        return (
          <div key={label} className="flex flex-1 items-center gap-2">
            <div
              className={[
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold tabular-nums transition-all duration-300",
                isActive
                  ? "scale-110 border-primary bg-primary text-primary-foreground shadow-[0_4px_12px_-2px_rgba(255,61,20,0.4)]"
                  : isDone
                    ? "border-primary bg-primary/[0.12] text-primary"
                    : "border-border bg-card text-muted-foreground",
              ].join(" ")}
            >
              {isDone ? <Check className="h-3.5 w-3.5" aria-hidden /> : i + 1}
            </div>
            <span
              className={[
                "font-mono text-[11px] uppercase tracking-[0.1em] transition-colors duration-300",
                isActive
                  ? "text-foreground"
                  : isDone
                    ? "text-foreground/70"
                    : "text-muted-foreground/60",
              ].join(" ")}
            >
              {label}
            </span>
            {i < total - 1 && (
              <div
                className={[
                  "ml-auto h-px flex-1 transition-colors duration-300",
                  isDone ? "bg-primary/40" : "bg-border",
                ].join(" ")}
                aria-hidden
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1 — When
// ---------------------------------------------------------------------------

function WhenStep({
  value,
  onChange,
}: {
  value: Month;
  onChange: (m: Month) => void;
}) {
  return (
    <Step icon={Calendar} title="When are you riding?" hint="We'll pull historical climate norms for your travel month.">
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 sm:gap-3">
        {MONTHS.map((m) => {
          const isOn = value === m;
          const hint = SEASON_HINT[m];
          return (
            <button
              key={m}
              type="button"
              onClick={() => onChange(m)}
              className={[
                "group flex flex-col items-start gap-1 rounded-xl border px-4 py-3 text-left transition-all duration-200",
                isOn
                  ? "scale-[1.02] border-primary bg-primary text-primary-foreground shadow-[0_4px_16px_-4px_rgba(255,61,20,0.4)]"
                  : "border-border bg-card text-foreground hover:-translate-y-0.5 hover:border-foreground/30 hover:shadow-paper",
              ].join(" ")}
              aria-pressed={isOn}
            >
              <span className="text-[15px] font-semibold leading-none">{m}</span>
              <span
                className={[
                  "text-[10px] leading-tight",
                  isOn ? "text-primary-foreground/80" : "text-muted-foreground/80",
                ].join(" ")}
              >
                {hint.tag}
              </span>
            </button>
          );
        })}
      </div>
    </Step>
  );
}

// ---------------------------------------------------------------------------
// Step 2 — Distance
// ---------------------------------------------------------------------------

function DistanceStep({
  value,
  anchorKm,
  totalKm,
  onChange,
}: {
  value: PaceChoice;
  anchorKm: number;
  totalKm: number;
  onChange: (c: PaceChoice) => void;
}) {
  const options = PACE_CHOICES.map((choice) => ({
    choice,
    km: paceKm(choice, anchorKm),
    days: paceDays(choice, anchorKm, totalKm),
  }));

  const selected = options.find((o) => o.choice === value) ?? options[1];
  const allSameDays = options.every((o) => o.days === options[0].days);

  return (
    <Step
      icon={Compass}
      title="How far each day?"
      hint={`Anchored on your stated ${anchorKm} km/day — three honest framings around that pace.`}
    >
      {/* Big live readout — same shape as before, but populated from the
          derived option rather than a hardcoded chip value. */}
      <div className="mb-5 flex items-baseline gap-2 rounded-xl border border-border/60 bg-bg-soft/80 px-5 py-4">
        <div>
          <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Splits into
          </div>
          <div className="mt-1 text-[36px] font-bold leading-none tracking-[-0.025em] tabular-nums text-foreground">
            {selected.days}
            <span className="ml-1 text-[16px] font-medium text-muted-foreground">
              {selected.days === 1 ? "day" : "days"}
            </span>
          </div>
        </div>
        <div className="ml-auto text-right">
          <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            Pace
          </div>
          <div className="mt-1 text-[18px] font-bold tabular-nums text-foreground">
            {selected.km}{" "}
            <span className="text-[12px] font-medium text-muted-foreground">
              km/day
            </span>
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
            over {totalKm} km
          </div>
        </div>
      </div>

      {allSameDays ? (
        // Degenerate route — every band fits in the same number of days, so
        // there's no meaningful trade-off to surface. Tell the rider that
        // honestly instead of presenting three chips that look like a choice.
        <div className="rounded-xl border border-dashed border-border/70 bg-card px-5 py-4 text-[13px] leading-snug text-muted-foreground">
          This corridor fits in{" "}
          <strong className="text-foreground">{options[0].days}</strong>{" "}
          {options[0].days === 1 ? "day" : "days"} at any reasonable pace —
          we&rsquo;ll plan it at your stated{" "}
          <strong className="text-foreground">{anchorKm} km/day</strong>.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {options.map(({ choice, km, days }) => {
            const isOn = value === choice;
            return (
              <button
                key={choice}
                type="button"
                onClick={() => onChange(choice)}
                className={[
                  "flex flex-col items-start gap-1 rounded-xl border px-4 py-3 text-left transition-all duration-200",
                  isOn
                    ? "scale-[1.02] border-primary bg-primary text-primary-foreground shadow-[0_4px_16px_-4px_rgba(255,61,20,0.4)]"
                    : "border-border bg-card text-foreground hover:-translate-y-0.5 hover:border-foreground/30 hover:shadow-paper",
                ].join(" ")}
                aria-pressed={isOn}
              >
                <span className="text-[15px] font-bold leading-none tracking-[-0.01em]">
                  {PACE_LABEL[choice]}
                </span>
                <span
                  className={[
                    "font-mono text-[12px] tabular-nums",
                    isOn ? "text-primary-foreground" : "text-foreground/85",
                  ].join(" ")}
                >
                  {km} km/day · {days} {days === 1 ? "day" : "days"}
                </span>
                <span
                  className={[
                    "text-[11px] leading-tight",
                    isOn
                      ? "text-primary-foreground/80"
                      : "text-muted-foreground/80",
                  ].join(" ")}
                >
                  {PACE_HINT[choice]}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </Step>
  );
}

// ---------------------------------------------------------------------------
// Step 3 — Sleep
// ---------------------------------------------------------------------------

function SleepStep({
  selected,
  onToggle,
}: {
  selected: Accom[];
  onToggle: (a: Accom) => void;
}) {
  return (
    <Step
      icon={Tent}
      title="Where will you sleep?"
      hint="Pick one or more — the agent honours the mix night-by-night."
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {ACCOM_OPTIONS.map((opt) => {
          const isOn = selected.includes(opt.value);
          const Icon = opt.Icon;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onToggle(opt.value)}
              className={[
                "group relative flex flex-col gap-2 rounded-2xl border p-4 text-left transition-all duration-200",
                isOn
                  ? "scale-[1.02] border-primary bg-primary/[0.06] shadow-[0_4px_20px_-6px_rgba(255,61,20,0.3)]"
                  : "border-border bg-card hover:-translate-y-0.5 hover:border-foreground/30 hover:shadow-paper",
              ].join(" ")}
              aria-pressed={isOn}
            >
              {/* Selection indicator */}
              <div
                className={[
                  "absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full border transition-all duration-200",
                  isOn
                    ? "scale-100 border-primary bg-primary text-primary-foreground"
                    : "scale-90 border-border bg-card text-transparent",
                ].join(" ")}
              >
                <Check className="h-3 w-3" aria-hidden />
              </div>

              {/* Icon */}
              <div
                className={[
                  "flex h-10 w-10 items-center justify-center rounded-xl transition-colors",
                  isOn ? "bg-primary text-primary-foreground" : "bg-muted text-foreground/70",
                ].join(" ")}
              >
                <Icon className="h-5 w-5" aria-hidden />
              </div>

              <div>
                <div className="text-[15px] font-bold leading-none tracking-[-0.01em] text-foreground">
                  {opt.label}
                </div>
                <div className="mt-1 text-[11.5px] leading-snug text-muted-foreground">
                  {opt.hint}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </Step>
  );
}

// ---------------------------------------------------------------------------
// Shared step wrapper + summary
// ---------------------------------------------------------------------------

function Step({
  icon: Icon,
  title,
  hint,
  children,
}: {
  icon: typeof Calendar;
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-5 flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/[0.08] text-primary">
          <Icon className="h-4 w-4" aria-hidden />
        </div>
        <div>
          <h3 className="text-[22px] font-bold leading-tight tracking-[-0.02em] text-foreground">
            {title}
          </h3>
          <p className="mt-1 text-[13px] leading-snug text-muted-foreground">{hint}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

/**
 * Live preview of the prompt the agent will receive. The user's current
 * picks render as highlighted "tags" inline in the sentence — so the
 * preview reads naturally and updates with a subtle pop on every change.
 *
 * Replaces the old per-step summary strip, which duplicated the labels of
 * the questions still being asked above.
 */
function PromptPreview({
  corridor,
  state,
  days,
  kmPerDay,
}: {
  corridor: Corridor;
  state: FormState;
  days: number;
  kmPerDay: number;
}) {
  const monthFull = MONTH_FULL[state.month];

  // Accommodation phrase mirrors `buildPrompt` exactly — one word in
  // <Pick> so it animates as a single tag rather than as a noisy
  // multi-word substring.
  let accomPhrase: string;
  const list = state.accommodations;
  if (list.length === 0 || list.length === ACCOM_OPTIONS.length) {
    accomPhrase = "any accommodation mix";
  } else if (list.length === 1) {
    accomPhrase = `${list[0]} throughout`;
  } else {
    const labels = list.map((a) =>
      a === "camping" ? "camping" : a === "hostel" ? "hostels" : "hotels",
    );
    accomPhrase = `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
  }

  return (
    <div className="mt-8 rounded-2xl border border-border/80 bg-card p-5 shadow-paper">
      <div className="mb-3 flex items-center gap-2">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inset-0 animate-ping rounded-full bg-primary opacity-60" />
          <span className="relative h-1.5 w-1.5 rounded-full bg-primary" />
        </span>
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          The agent will plan
        </span>
      </div>
      <p className="text-[14.5px] leading-[1.65] text-foreground/90">
        Plan a <Pick value={`${days}d`}>{days}-day</Pick> cycling trip{" "}
        <span className="font-semibold text-foreground">{corridor.label.toLowerCase()}</span>{" "}
        (roughly {corridor.total_km} km), at{" "}
        <Pick value={`${kmPerDay}km`}>{kmPerDay} km/day</Pick>, prefer{" "}
        <Pick value={accomPhrase}>{accomPhrase}</Pick>, traveling in{" "}
        <Pick value={monthFull}>{monthFull}</Pick>.
      </p>
    </div>
  );
}

/**
 * Inline highlighted "pick" tag — the user's current selection rendered
 * inside the prompt preview. `value` keys the element so React remounts
 * it on change, triggering the fade/zoom-in animation.
 */
function Pick({ value, children }: { value: string; children: React.ReactNode }) {
  return (
    <span
      key={value}
      className="inline-flex items-baseline rounded-md bg-primary/[0.10] px-1.5 py-0.5 font-semibold text-primary animate-in fade-in zoom-in-95 duration-300"
    >
      {children}
    </span>
  );
}
