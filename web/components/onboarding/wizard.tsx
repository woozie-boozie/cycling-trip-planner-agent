"use client";

/**
 * Onboarding wizard — 5 cards, skippable, posts to /profile, returns the id.
 *
 * Driven by the May 2026 cyclist user research ("don't set them up for
 * failure — build their profile first"). Skippable: not every user wants
 * 5 questions before chatting; the brief's example flow still works for
 * skippers.
 *
 * State lives entirely in this component. Parent only learns about a
 * profile via `onComplete(profileId)` (or that the user dismissed via
 * `onDismiss()`). Both paths close the modal.
 */

import { useCallback, useState } from "react";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, postProfile } from "@/lib/api";
import type {
  DietaryRestriction,
  ExperienceLevel,
  Priority,
  TripStyle,
} from "@/lib/types";

interface WizardProps {
  onComplete: (profileId: string) => void;
  onDismiss: () => void;
}

const STEP_LABELS = ["Experience", "Style", "Priorities", "Dietary", "Notes"];

interface ExperienceOption {
  value: ExperienceLevel;
  label: string;
  hint: string;
  km: string;
}
const EXPERIENCE_OPTIONS: ExperienceOption[] = [
  { value: "beginner", label: "Beginner", hint: "30–50 km is plenty", km: "≤ 50 km/day" },
  { value: "casual", label: "Casual", hint: "Weekends, occasional touring", km: "≤ 80 km/day" },
  { value: "intermediate", label: "Intermediate", hint: "Comfortable on multi-day rides", km: "≤ 100 km/day" },
  { value: "experienced", label: "Experienced", hint: "Regular long rides, hills don't faze me", km: "≤ 130 km/day" },
  { value: "racer", label: "Racer / endurance", hint: "Audax, ultra, randonneuring", km: "150+ km/day" },
];

interface OptionTile<T extends string> {
  value: T;
  label: string;
  hint?: string;
}
const TRIP_STYLE_OPTIONS: OptionTile<TripStyle>[] = [
  { value: "weekend", label: "Weekend", hint: "1–3 day getaway" },
  { value: "touring", label: "Touring", hint: "Multi-day with luggage" },
  { value: "commute", label: "Commute", hint: "Daily ride to work" },
  { value: "charity", label: "Charity", hint: "Fundraising ride" },
  { value: "special", label: "Special", hint: "Honeymoon, milestone trip" },
  { value: "solo", label: "Solo", hint: "Unsupported, just me" },
];

const PRIORITY_OPTIONS: OptionTile<Priority>[] = [
  { value: "scenery", label: "Scenery" },
  { value: "distance", label: "Covering distance" },
  { value: "food_drink", label: "Food & drink" },
  { value: "wild_camping", label: "Wild camping" },
  { value: "quiet_roads", label: "Quiet roads" },
  { value: "pubs_culture", label: "Pubs & culture" },
  { value: "cheap", label: "Keeping it cheap" },
  { value: "iconic", label: "Iconic routes" },
  { value: "photography", label: "Photography stops" },
];

const DIETARY_OPTIONS: OptionTile<DietaryRestriction>[] = [
  { value: "vegetarian", label: "Vegetarian" },
  { value: "vegan", label: "Vegan" },
  { value: "gluten_free", label: "Gluten-free" },
  { value: "halal", label: "Halal" },
  { value: "kosher", label: "Kosher" },
  { value: "lactose_free", label: "Lactose-free" },
  { value: "none", label: "None" },
];

function toggleInArray<T>(arr: T[], value: T, max?: number): T[] {
  if (arr.includes(value)) return arr.filter((v) => v !== value);
  if (max !== undefined && arr.length >= max) return arr;
  return [...arr, value];
}

export function OnboardingWizard({ onComplete, onDismiss }: WizardProps) {
  const [step, setStep] = useState(0);
  const [experience, setExperience] = useState<ExperienceLevel | null>(null);
  const [tripStyles, setTripStyles] = useState<TripStyle[]>([]);
  const [priorities, setPriorities] = useState<Priority[]>([]);
  const [dietary, setDietary] = useState<DietaryRestriction[]>([]);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    if (!experience) return;
    setError(null);
    setSubmitting(true);
    try {
      // If the user picked "none" alongside other options, drop "none" — it's
      // an explicit opt-out, not a constraint.
      const cleanedDietary =
        dietary.length > 1 ? dietary.filter((d) => d !== "none") : dietary;

      const profile = await postProfile({
        experience,
        trip_styles: tripStyles,
        priorities,
        dietary: cleanedDietary,
        additional_notes: notes.trim() || null,
      });
      onComplete(profile.profile_id);
    } catch (err) {
      const fallback = "Couldn't save your profile. Try again?";
      if (err instanceof ApiError) {
        setError(`${fallback} (${err.status})`);
      } else {
        setError(fallback);
      }
      setSubmitting(false);
    }
  }, [experience, tripStyles, priorities, dietary, notes, onComplete]);

  const isLast = step === STEP_LABELS.length - 1;
  const canAdvance = step === 0 ? experience !== null : true;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="wizard-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/85 px-4 py-6 backdrop-blur-sm"
    >
      <div className="relative w-full max-w-xl overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
        {/* Skip button — top-right, always visible */}
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Skip onboarding"
          className="absolute right-3 top-3 rounded-md p-1.5 text-muted-foreground transition hover:bg-muted hover:text-foreground"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>

        {/* Header */}
        <div className="border-b border-border/60 px-6 pb-4 pt-5">
          <h2 id="wizard-title" className="text-base font-semibold tracking-tight text-foreground">
            Tell me about your riding
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Five quick questions — I&apos;ll tailor the plan to you. Skip any time.
          </p>
          <ProgressDots step={step} total={STEP_LABELS.length} labels={STEP_LABELS} />
        </div>

        {/* Step body */}
        <div className="px-6 py-5">
          {step === 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-foreground">Your experience level</p>
              <p className="mb-3 text-xs text-muted-foreground">
                Used to set your max comfortable daily distance — I won&apos;t plan past it without
                checking with you first.
              </p>
              <div className="space-y-2">
                {EXPERIENCE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setExperience(opt.value)}
                    className={`flex w-full items-center justify-between gap-3 rounded-lg border px-4 py-3 text-left transition ${
                      experience === opt.value
                        ? "border-primary bg-primary/10 text-foreground ring-1 ring-primary/40"
                        : "border-border bg-background hover:border-primary/50 hover:bg-muted/50"
                    }`}
                  >
                    <div>
                      <div className="text-sm font-medium">{opt.label}</div>
                      <div className="text-xs text-muted-foreground">{opt.hint}</div>
                    </div>
                    <div className="font-mono text-[11px] text-muted-foreground">{opt.km}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 1 && (
            <ChipPickerStep
              title="What kind of trips?"
              hint="Pick any that apply — helps me match the vibe."
              options={TRIP_STYLE_OPTIONS}
              selected={tripStyles}
              onToggle={(v) => setTripStyles((prev) => toggleInArray(prev, v))}
            />
          )}

          {step === 2 && (
            <ChipPickerStep
              title="What matters most? (max 3)"
              hint="Forces a real ranking. I&apos;ll bias route + accommodation toward these."
              options={PRIORITY_OPTIONS}
              selected={priorities}
              onToggle={(v) =>
                setPriorities((prev) => toggleInArray(prev, v, 3))
              }
              maxNote={priorities.length >= 3 ? "Three's the cap — deselect to swap." : undefined}
            />
          )}

          {step === 3 && (
            <ChipPickerStep
              title="Any dietary needs?"
              hint="I'll match cafes, pubs, and supermarket recommendations."
              options={DIETARY_OPTIONS}
              selected={dietary}
              onToggle={(v) => setDietary((prev) => toggleInArray(prev, v))}
            />
          )}

          {step === 4 && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-foreground">Anything else?</p>
              <p className="text-xs text-muted-foreground">
                Free text. Examples: <em>cycling for charity, have asthma, want only quiet
                roads, this is my honeymoon</em>.
              </p>
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Optional — leave blank if nothing comes to mind."
                rows={4}
                maxLength={500}
                className="resize-none"
              />
              <div className="text-right text-[10px] text-muted-foreground">
                {notes.length}/500
              </div>
            </div>
          )}

          {error && (
            <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-border/60 bg-card/50 px-6 py-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={onDismiss}
            disabled={submitting}
            className="text-xs text-muted-foreground"
          >
            Skip for now
          </Button>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0 || submitting}
            >
              Back
            </Button>
            {isLast ? (
              <Button size="sm" onClick={handleSubmit} disabled={!experience || submitting}>
                {submitting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                    Saving
                  </>
                ) : (
                  "Save & continue"
                )}
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={() => setStep((s) => s + 1)}
                disabled={!canAdvance}
              >
                Next
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface ChipPickerStepProps<T extends string> {
  title: string;
  hint: string;
  options: OptionTile<T>[];
  selected: T[];
  onToggle: (value: T) => void;
  maxNote?: string;
}

function ChipPickerStep<T extends string>({
  title,
  hint,
  options,
  selected,
  onToggle,
  maxNote,
}: ChipPickerStepProps<T>) {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => {
          const isSelected = selected.includes(opt.value);
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onToggle(opt.value)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                isSelected
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background text-foreground hover:border-primary/50 hover:bg-muted/60"
              }`}
              title={opt.hint}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      {maxNote && (
        <p className="text-[11px] italic text-muted-foreground">{maxNote}</p>
      )}
    </div>
  );
}

function ProgressDots({
  step,
  total,
  labels,
}: {
  step: number;
  total: number;
  labels: string[];
}) {
  return (
    <div className="mt-4 flex items-center gap-2">
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className={`h-1.5 flex-1 rounded-full transition ${
            i < step
              ? "bg-primary/70"
              : i === step
                ? "bg-primary"
                : "bg-muted"
          }`}
          aria-label={`Step ${i + 1}: ${labels[i]}`}
        />
      ))}
    </div>
  );
}
