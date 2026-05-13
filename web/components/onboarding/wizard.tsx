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
import { ArrowLeft, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, postProfile } from "@/lib/api";
import type {
  DietaryRestriction,
  ExperienceLevel,
  Priority,
  TripStyle,
  UserProfile,
} from "@/lib/types";

interface WizardProps {
  onComplete: (profileId: string) => void;
  onDismiss: () => void;
  /** When provided, the wizard pre-populates with the user's saved answers
   *  and upserts back to the same profile_id. */
  existing?: UserProfile | null;
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

export function OnboardingWizard({ onComplete, onDismiss, existing }: WizardProps) {
  const isEditing = Boolean(existing);
  const [step, setStep] = useState(0);
  const [experience, setExperience] = useState<ExperienceLevel | null>(
    existing?.experience ?? null,
  );
  const [tripStyles, setTripStyles] = useState<TripStyle[]>(existing?.trip_styles ?? []);
  const [priorities, setPriorities] = useState<Priority[]>(existing?.priorities ?? []);
  const [dietary, setDietary] = useState<DietaryRestriction[]>(existing?.dietary ?? []);
  const [notes, setNotes] = useState(existing?.additional_notes ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const existingProfileId = existing?.profile_id;
  const handleSubmit = useCallback(async () => {
    if (!experience) return;
    setError(null);
    setSubmitting(true);
    try {
      // If the user picked "none" alongside other options, drop "none" — it's
      // an explicit opt-out, not a constraint.
      const cleanedDietary =
        dietary.length > 1 ? dietary.filter((d) => d !== "none") : dietary;

      // Pass existing profile_id so the server upserts in place — the
      // user's saved answers are updated, not duplicated.
      const profile = await postProfile({
        profile_id: existingProfileId,
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
  }, [experience, tripStyles, priorities, dietary, notes, onComplete, existingProfileId]);

  const isLast = step === STEP_LABELS.length - 1;
  const canAdvance = step === 0 ? experience !== null : true;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="wizard-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/85 px-4 py-6 backdrop-blur-sm"
    >
      <div className="relative w-full max-w-2xl overflow-hidden rounded-2xl bg-card shadow-2xl">
        {/* Top bar: Skip (left), step counter + close (right) */}
        <div className="flex items-center justify-between px-10 pt-8">
          <button
            type="button"
            onClick={onDismiss}
            disabled={submitting}
            className="text-sm text-muted-foreground transition hover:text-foreground disabled:opacity-40"
          >
            {isEditing ? "Cancel" : "Skip"}
          </button>
          <div className="flex items-center gap-4">
            <span
              className="font-mono text-xs tracking-wide text-muted-foreground"
              aria-label={`Step ${step + 1} of ${STEP_LABELS.length}: ${STEP_LABELS[step]}`}
            >
              {step + 1} / {STEP_LABELS.length}
            </span>
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Close"
              className="rounded-md p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>

        {/* Step body — generous padding */}
        <div className="px-10 pb-6 pt-10 lg:px-14 lg:pt-14">
          {/* Visually-hidden title for aria-labelledby */}
          <h2 id="wizard-title" className="sr-only">
            {isEditing ? "Edit your profile" : "Tell me about your riding"}
          </h2>

          {step === 0 && (
            <div className="space-y-8">
              <div className="space-y-3">
                <h3 className="text-2xl font-medium tracking-tight text-foreground">
                  Your experience level
                </h3>
                <p className="text-base text-muted-foreground">
                  Sets your max comfortable daily distance — I won&apos;t plan past it
                  without checking with you first.
                </p>
              </div>
              <div className="space-y-3">
                {EXPERIENCE_OPTIONS.map((opt) => {
                  const isSelected = experience === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setExperience(opt.value)}
                      className={`flex w-full items-center justify-between gap-4 rounded-xl border px-5 py-4 text-left transition ${
                        isSelected
                          ? "border-primary bg-primary/10 ring-1 ring-primary/40"
                          : "border-border bg-background hover:border-primary/40 hover:bg-muted/40"
                      }`}
                    >
                      <div>
                        <div className="text-base font-medium text-foreground">{opt.label}</div>
                        <div className="mt-0.5 text-sm text-muted-foreground">{opt.hint}</div>
                      </div>
                      <div className="font-mono text-xs text-muted-foreground">{opt.km}</div>
                    </button>
                  );
                })}
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
              title="What matters most?"
              hint="I'll bias the route and stops toward these."
              options={PRIORITY_OPTIONS}
              selected={priorities}
              onToggle={(v) => setPriorities((prev) => toggleInArray(prev, v))}
            />
          )}

          {step === 3 && (
            <ChipPickerStep
              title="Any dietary needs?"
              hint="I'll match cafés, pubs, and supermarket suggestions."
              options={DIETARY_OPTIONS}
              selected={dietary}
              onToggle={(v) => setDietary((prev) => toggleInArray(prev, v))}
            />
          )}

          {step === 4 && (
            <div className="space-y-6">
              <div className="space-y-3">
                <h3 className="text-2xl font-medium tracking-tight text-foreground">
                  Anything else?
                </h3>
                <p className="text-base text-muted-foreground">
                  Free text. Examples: cycling for charity, asthma, want only quiet roads,
                  this is my honeymoon.
                </p>
              </div>
              <div className="space-y-2">
                <Textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Optional — leave blank if nothing comes to mind."
                  rows={5}
                  maxLength={500}
                  className="resize-none text-base"
                />
                <div className="text-left text-xs text-muted-foreground">
                  {notes.length}/500
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="mt-6 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
        </div>

        {/* Footer — minimal: back arrow left (from step 2+), single primary action right */}
        <div className="flex items-center justify-between px-10 pb-8 pt-2 lg:px-14">
          <button
            type="button"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0 || submitting}
            aria-label="Back"
            className={`rounded-md p-2 text-muted-foreground transition hover:bg-muted hover:text-foreground disabled:pointer-events-none ${
              step === 0 ? "opacity-0" : "opacity-100"
            }`}
          >
            <ArrowLeft className="h-5 w-5" aria-hidden />
          </button>
          {isLast ? (
            <Button
              size="lg"
              onClick={handleSubmit}
              disabled={!experience || submitting}
              className="min-w-[10rem]"
            >
              {submitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
                  Saving
                </>
              ) : isEditing ? (
                "Save changes"
              ) : (
                "Save & continue"
              )}
            </Button>
          ) : (
            <Button
              size="lg"
              onClick={() => setStep((s) => s + 1)}
              disabled={!canAdvance}
              className="min-w-[10rem]"
            >
              Continue
            </Button>
          )}
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
    <div className="space-y-8">
      <div className="space-y-3">
        <h3 className="text-2xl font-medium tracking-tight text-foreground">{title}</h3>
        <p className="text-base text-muted-foreground">{hint}</p>
      </div>
      <div className="flex flex-wrap gap-3">
        {options.map((opt) => {
          const isSelected = selected.includes(opt.value);
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onToggle(opt.value)}
              className={`rounded-full border px-5 py-2.5 text-sm font-medium transition ${
                isSelected
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background text-foreground hover:border-primary/40 hover:bg-muted/40"
              }`}
              title={opt.hint}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      {maxNote && (
        <p className="text-xs text-muted-foreground">{maxNote}</p>
      )}
    </div>
  );
}
