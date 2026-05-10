"use client";

import { useState } from "react";
import { ArrowRight, Check, Star, X } from "lucide-react";
import type { Corridor } from "@/lib/corridors";
import type { RouteVariantSummary } from "@/lib/route-variants";

interface RouteComparisonCardProps {
  corridor: Corridor;
  variants: RouteVariantSummary[];
  /** When set, highlights a recommended variant with a star + accent border */
  recommendedName?: string;
  /** Optional CTA fired when the user picks a variant */
  onPick?: (variant: RouteVariantSummary) => void;
  /**
   * Currently-selected variant (controlled). When omitted the card
   * manages its own selection state. When provided, the parent owns
   * the selection — this is how the RouteCanvas above the card
   * reflects which variant the user has clicked.
   */
  selectedName?: string;
  /** Fired on every selection change so the parent can sync the map */
  onSelect?: (variant: RouteVariantSummary) => void;
}

/**
 * Side-by-side route variants — the visual replacement for the agent's
 * "Option 1 / Option 2 / Option 3" markdown comparison block.
 *
 * Renders only when:
 *   - view_mode === "visual"
 *   - the conversation is about a known corridor with multiple variants
 *   - the agent's response heuristically looks like a multi-variant pitch
 *
 * If any of those don't hold, the visual response renderer falls through
 * to the markdown renderer — visual mode never blocks a response.
 */
export function RouteComparisonCard({
  corridor,
  variants,
  recommendedName,
  onPick,
  selectedName: controlledSelectedName,
  onSelect,
}: RouteComparisonCardProps) {
  const [internalSelectedName, setInternalSelectedName] = useState<string>(
    recommendedName ?? variants.find((v) => v.is_default)?.name ?? variants[0].name,
  );
  const selectedName = controlledSelectedName ?? internalSelectedName;
  const handleSelect = (variant: RouteVariantSummary) => {
    if (controlledSelectedName === undefined) {
      setInternalSelectedName(variant.name);
    }
    onSelect?.(variant);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Route variants · {variants.length} found
          </p>
          <h3
            className="font-heading mt-0.5 text-xl italic leading-tight text-foreground"
            style={{ fontFamily: "var(--font-heading)" }}
          >
            {corridor.label}
          </h3>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">
          compare_route_variants
        </span>
      </div>

      {/* Variant grid */}
      <div className="grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-3">
        {variants.map((v) => {
          const isSelected = selectedName === v.name;
          const isRecommended = recommendedName === v.name;
          return (
            <button
              key={v.name}
              type="button"
              onClick={() => handleSelect(v)}
              className={[
                "group relative flex flex-col gap-2 overflow-hidden rounded-lg border bg-card p-3 text-left transition-all",
                isSelected
                  ? "border-primary shadow-sm"
                  : "border-border hover:border-primary/40 hover:bg-card/80",
                isRecommended && !isSelected && "ring-1 ring-primary/30",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {/* Color swatch + name */}
              <div className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ background: v.color }}
                  aria-hidden
                />
                <span
                  className="font-heading text-base italic leading-tight text-foreground"
                  style={{ fontFamily: "var(--font-heading)" }}
                >
                  {v.title}
                </span>
                {isRecommended && (
                  <Star
                    className="ml-auto h-3.5 w-3.5 text-primary"
                    fill="currentColor"
                    aria-hidden
                  />
                )}
              </div>
              <p className="text-xs leading-snug text-muted-foreground">
                {v.tagline}
              </p>

              {/* Stats row */}
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-y border-border/60 py-2 font-mono text-[11px] tabular-nums text-muted-foreground">
                <span>
                  <strong className="font-semibold text-foreground">
                    {v.total_distance_km}
                  </strong>{" "}
                  km
                </span>
                <span>
                  <strong className="font-semibold text-foreground">
                    {v.estimated_days}
                  </strong>{" "}
                  d
                </span>
                {v.vibes && v.vibes.length > 0 && (
                  <span className="ml-auto truncate text-muted-foreground/80">
                    {v.vibes.slice(0, 2).join(" · ")}
                  </span>
                )}
              </div>

              {/* Pros */}
              <ul className="space-y-1">
                {v.distinguishing_features.slice(0, 3).map((f, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-1.5 text-xs leading-snug text-foreground/85"
                  >
                    <Check
                      className="mt-0.5 h-3 w-3 shrink-0 text-emerald-600"
                      aria-hidden
                    />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>

              {/* Cons */}
              {v.trade_offs.length > 0 && (
                <ul className="space-y-1">
                  {v.trade_offs.slice(0, 2).map((t, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-1.5 text-xs leading-snug text-muted-foreground"
                    >
                      <X
                        className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground/70"
                        aria-hidden
                      />
                      <span>{t}</span>
                    </li>
                  ))}
                </ul>
              )}

              {/* Best for */}
              <p className="mt-1 text-[11px] italic leading-snug text-muted-foreground">
                Best for: {v.best_for}
              </p>

              {onPick && isSelected && (
                <div className="mt-1 flex items-center gap-1 text-xs font-semibold text-primary">
                  Plan this variant
                  <ArrowRight
                    className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
                    aria-hidden
                  />
                </div>
              )}
            </button>
          );
        })}
      </div>

      {onPick && (
        <div className="flex items-center justify-end border-t border-border/60 bg-muted/40 px-3 py-2">
          <button
            type="button"
            onClick={() => {
              const variant = variants.find((v) => v.name === selectedName);
              if (variant) onPick(variant);
            }}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Plan {variants.find((v) => v.name === selectedName)?.title}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      )}
    </div>
  );
}
