"use client";

import { useMemo, useState } from "react";
import { GpxDownloadStrip } from "@/components/gpx-download-strip";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { RouteCanvas } from "@/components/route-canvas";
import { RouteComparisonCard } from "@/components/route-comparison-card";
import { matchCorridor, type Corridor } from "@/lib/corridors";
import {
  parseItinerary,
  parseRouteHeader,
  type DayRow,
} from "@/lib/parse-itinerary";
import {
  getVariants,
  ROUTE_VARIANTS,
  type RouteVariantSummary,
} from "@/lib/route-variants";

interface VisualResponseProps {
  /** The assistant message body (markdown) */
  content: string;
  /**
   * The most recently-detected corridor in the conversation, used to scope
   * variant detection. Pass-through from `page.tsx`'s `useMemo` over
   * `messages`.
   */
  corridor: Corridor | null;
  /** Fired when the user picks a variant from the comparison card */
  onPickVariant?: (variant: RouteVariantSummary) => void;
}

/**
 * Visual mode renderer. Inspects the assistant's markdown for structural
 * patterns (multi-variant comparison, multi-day plan) and renders the
 * matching card. Falls through to markdown for everything else.
 *
 * Detection is heuristic — visual mode never *blocks* a response. If the
 * pattern doesn't match cleanly, the user sees the markdown rendering
 * (same as text mode), and the toggle in the header is a one-click
 * escape hatch.
 *
 * Phase A handles:
 *   - multi-variant comparison → RouteComparisonCard
 *
 * Phase B will add:
 *   - multi-day plan → ItineraryCard
 *   - corridor route map → RouteCanvas with POI overlay
 */
export function VisualResponse({ content, corridor, onPickVariant }: VisualResponseProps) {
  const detection = useMemo(() => detectResponseShape(content, corridor), [
    content,
    corridor,
  ]);

  switch (detection.kind) {
    case "comparison":
      return (
        <ComparisonResponse
          detection={detection}
          onPickVariant={onPickVariant}
        />
      );
    case "single-route":
      return (
        <div className="space-y-3">
          <RouteCanvas corridor={detection.corridor} />
          <div className="prose prose-sm max-w-none text-sm leading-relaxed text-foreground">
            <MarkdownRenderer content={content} />
          </div>
        </div>
      );
    case "itinerary":
      // The agent's day-by-day markdown is rich and reliably well-formatted —
      // and the per-day parser was repeatedly mis-shaping it (parenthetical
      // date suffixes leaking into city names, missing km columns, fake totals).
      // We keep the map at the top for visual orientation and let the agent's
      // markdown be the source of truth for the day list itself. Same rendering
      // path as text mode, framed by the corridor map.
      //
      // GPX download strip renders alongside the markdown — same parsed days
      // we use elsewhere drive the per-day download buttons. Sits between
      // the canvas and the markdown so cyclists see the artifact-they-ride-with
      // before the day breakdown.
      return (
        <div className="space-y-3">
          {detection.corridor && <RouteCanvas corridor={detection.corridor} />}
          {detection.corridor && detection.days.length > 0 && (
            <GpxDownloadStrip
              start={detection.routeStart}
              end={detection.routeEnd}
              variantName={detection.variantName}
              days={detection.days}
              label={detection.corridor.label}
            />
          )}
          <div className="prose prose-sm max-w-none text-sm leading-relaxed text-foreground">
            <MarkdownRenderer content={content} />
          </div>
        </div>
      );
    case "markdown":
    default:
      return <MarkdownRenderer content={content} />;
  }
}

// ---------------------------------------------------------------------------
// Comparison sub-component — owns the selected variant so the map redraws
// when the user clicks a different card.
// ---------------------------------------------------------------------------

function ComparisonResponse({
  detection,
  onPickVariant,
}: {
  detection: Extract<Detection, { kind: "comparison" }>;
  onPickVariant?: (v: RouteVariantSummary) => void;
}) {
  const initial =
    detection.recommendedName ??
    detection.variants.find((v) => v.is_default)?.name ??
    detection.variants[0].name;
  const [selectedName, setSelectedName] = useState<string>(initial);
  const selected = detection.variants.find((v) => v.name === selectedName) ?? detection.variants[0];

  // Cards-only render. The variant cards already convey every fact in the
  // agent's bullet block (title, tagline, km, days, 3 pros, 2 cons, best-for) —
  // duplicating it as markdown below is noise. The agent's closing question
  // / recommendation lives in text mode for users who want the prose.
  return (
    <div className="space-y-3">
      <RouteCanvas
        corridor={detection.corridor}
        variantWaypoints={selected.waypoints}
        title={`${detection.corridor.label} · ${selected.title}`}
        subtitle={`${selected.total_distance_km} km · ${selected.estimated_days} d · ${selected.tagline}`}
      />
      <RouteComparisonCard
        corridor={detection.corridor}
        variants={detection.variants}
        recommendedName={detection.recommendedName}
        onPick={onPickVariant}
        selectedName={selectedName}
        onSelect={(v) => setSelectedName(v.name)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detection
// ---------------------------------------------------------------------------

type Detection =
  | {
      kind: "comparison";
      corridor: Corridor;
      variants: RouteVariantSummary[];
      /** Variant the agent recommended, if we can extract it */
      recommendedName?: string;
    }
  | {
      /** Corridor matched but no multi-variant comparison block */
      kind: "single-route";
      corridor: Corridor;
    }
  | {
      /** Multi-day plan detected — render the map + the agent's markdown body */
      kind: "itinerary";
      /** Corridor inferred from the conversation (if any) — drives the map */
      corridor: Corridor | null;
      /** Parsed day rows — drive the per-day GPX download buttons */
      days: DayRow[];
      /** Origin city extracted from the agent's header for the GPX endpoint */
      routeStart: string;
      /** Destination city extracted from the agent's header for the GPX endpoint */
      routeEnd: string;
      /** Variant identifier matched against ROUTE_VARIANTS, or null */
      variantName: string | null;
    }
  | { kind: "markdown" };

/**
 * Returns "comparison" when:
 *   1. We have a corridor matched from conversation context (or message)
 *   2. The corridor has 2+ known variants in route-variants.ts
 *   3. EITHER 2+ variant titles appear in the message (case-insensitive),
 *      OR 2+ "Option N" markers appear (legacy pattern).
 *
 * Otherwise returns "markdown".
 */
function detectResponseShape(content: string, corridor: Corridor | null): Detection {
  if (!corridor) {
    // No corridor in conversation context yet. Try the message itself.
    const fromMessage = matchCorridor(content);
    if (!fromMessage) return { kind: "markdown" };
    corridor = fromMessage;
  }

  const variants = getVariants(corridor.id);
  const lowered = content.toLowerCase();

  // Multi-variant comparison detection (only when the corridor has 2+ variants
  // AND the message references multiple of them).
  if (variants) {
    const titleHits = variants.filter((v) =>
      lowered.includes(v.title.toLowerCase()),
    ).length;
    const optionMarkerRegex = /\bOption\s+\d+\b/gi;
    const optionHits = (content.match(optionMarkerRegex) ?? []).length;
    const isComparison = titleHits >= 2 || optionHits >= 2;

    if (isComparison) {
      const recommendedName = inferRecommended(content, variants);
      return {
        kind: "comparison",
        corridor,
        variants,
        recommendedName,
      };
    }
  }

  // Multi-day itinerary detection — used as a signal that the response IS a
  // day-by-day plan (so the map renders above the markdown body) AND to feed
  // the GpxDownloadStrip with parsed day rows for the per-day download
  // buttons. The markdown body itself is still rendered by MarkdownRenderer.
  const days = parseItinerary(content);
  if (days && days.length >= 3) {
    const allVariants = Object.values(ROUTE_VARIANTS).flat();
    const header = parseRouteHeader(content, allVariants);
    return {
      kind: "itinerary",
      corridor,
      days,
      routeStart: header?.start ?? corridor.label.split("→")[0]?.trim() ?? "",
      routeEnd: header?.end ?? corridor.label.split("→")[1]?.trim() ?? "",
      variantName: header?.variantName ?? null,
    };
  }

  // No multi-variant comparison + no multi-day plan. If the corridor has
  // been mentioned with at least 2 specific waypoints, show the map for
  // geographic context.
  const corridorRefHits = corridor.waypoints.filter((w) =>
    lowered.includes(w.name.toLowerCase()),
  ).length;
  if (corridorRefHits >= 2) {
    return { kind: "single-route", corridor };
  }

  return { kind: "markdown" };
}

// ---------------------------------------------------------------------------
// Recommendation extraction (used inside detectResponseShape only)
// ---------------------------------------------------------------------------

/**
 * Best-effort recommendation extraction. Returns the variant.name the
 * agent appears to be recommending, or undefined.
 *
 * Tiered: stronger signals override weaker ones. Within a tier, the
 * first variant matching wins. The variant signature word is derived
 * from `title.split(' ')[0]` (e.g. "Inland EV7/12 hybrid" → "inland",
 * "Coastal EV12 North Sea" → "coastal").
 */
function inferRecommended(
  content: string,
  variants: RouteVariantSummary[],
): string | undefined {
  const lower = content.toLowerCase();

  // Helper: signature word for a variant (lowercase, ≥4 chars).
  const sigOf = (v: RouteVariantSummary): string | null => {
    const w = v.title.split(/\s+/)[0]?.toLowerCase();
    return w && w.length >= 4 ? w : null;
  };

  // ── Tier 1 · "is/feels more aligned" / "matches your priorities" ──
  // Strongest signal — explicit alignment with the user's profile.
  for (const v of variants) {
    const sig = sigOf(v);
    if (!sig) continue;
    const t1 = [
      new RegExp(`\\b${sig}\\b[^.]*\\b(more|best|better|much|properly)\\s+aligned\\b`, "i"),
      new RegExp(`\\b${sig}\\b[^.]*\\bmatches your\\b`, "i"),
      new RegExp(`\\b${sig}\\b[^.]*\\bhonors your priorities\\b`, "i"),
    ];
    if (t1.some((re) => re.test(content))) return v.name;
  }

  // ── Tier 2 · explicit recommend / go with / choose <title> ──
  for (const v of variants) {
    const t = v.title.toLowerCase();
    if (
      lower.includes(`recommend ${t}`) ||
      lower.includes(`recommend the ${t}`) ||
      lower.includes(`go with ${t}`) ||
      lower.includes(`go with the ${t}`) ||
      lower.includes(`choose ${t}`) ||
      lower.includes(`my pick is ${t}`)
    ) {
      return v.name;
    }
  }

  // ── Tier 3 · "recommend Option N" (legacy) ──
  const m = content.match(/\brecommend(?:ation)?[^.]*\bOption\s+(\d+)/i);
  if (m) {
    const idx = parseInt(m[1], 10) - 1;
    if (idx >= 0 && idx < variants.length) return variants[idx].name;
  }

  // ── Tier 4 · "best fits / ideal for / perfect for" ──
  for (const v of variants) {
    const sig = sigOf(v);
    if (!sig) continue;
    const t4 = [
      new RegExp(`\\b${sig}\\s+route\\b[^.]*\\b(ideal|perfect)\\b`, "i"),
      new RegExp(`\\bbest fit\\b[^.]*\\b${sig}\\b`, "i"),
      new RegExp(`\\b${sig}\\b[^.]*\\bbest fits\\b`, "i"),
    ];
    if (t4.some((re) => re.test(content))) return v.name;
  }

  // ── Tier 5 (weakest) · "<X> fits your <something>" ──
  // Only fires when no stronger signal won — used to be Tier 1, demoted
  // because it incorrectly matched when both variants had a "fits" line.
  for (const v of variants) {
    const sig = sigOf(v);
    if (!sig) continue;
    if (new RegExp(`\\b${sig}\\b[^.]*\\bfits\\b`, "i").test(content)) {
      return v.name;
    }
  }

  return undefined;
}
