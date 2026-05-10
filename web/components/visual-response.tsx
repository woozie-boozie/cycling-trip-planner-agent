"use client";

import { useMemo } from "react";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { RouteComparisonCard } from "@/components/route-comparison-card";
import { matchCorridor, type Corridor } from "@/lib/corridors";
import { getVariants, type RouteVariantSummary } from "@/lib/route-variants";

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
        <div className="space-y-3">
          <RouteComparisonCard
            corridor={detection.corridor}
            variants={detection.variants}
            recommendedName={detection.recommendedName}
            onPick={onPickVariant}
          />
          {detection.afterText && (
            <div className="prose prose-sm max-w-none text-sm leading-relaxed text-foreground">
              <MarkdownRenderer content={detection.afterText} />
            </div>
          )}
        </div>
      );
    case "markdown":
    default:
      return <MarkdownRenderer content={content} />;
  }
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
      /** Markdown that follows the variant block (the agent's recommendation prose) */
      afterText?: string;
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
  if (!variants) return { kind: "markdown" };

  const lowered = content.toLowerCase();

  // Primary signal: how many variant titles appear in the message?
  // Agent's actual responses use bold titles like "**INLAND EV7/12 HYBRID**"
  // or headings like "## Coastal EV12 North Sea", not "Option 1/2".
  const titleHits = variants.filter((v) =>
    lowered.includes(v.title.toLowerCase()),
  ).length;

  // Fallback signal: legacy "Option N" markers (some agent runs use these).
  const optionMarkerRegex = /\bOption\s+\d+\b/gi;
  const optionHits = (content.match(optionMarkerRegex) ?? []).length;

  // Need at least 2 of either signal to show a comparison card.
  const isComparison = titleHits >= 2 || optionHits >= 2;
  if (!isComparison) return { kind: "markdown" };

  // Try to detect which variant the agent recommended (if any).
  const recommendedName = inferRecommended(content, variants);

  // Trim the variant-comparison block off the front and pass the
  // remaining "recommendation" prose through MarkdownRenderer below.
  // Cuts cleanly past the agent's "Which variant would you like?"
  // question + any trailing markdown markers (**, whitespace).
  let afterText = "";
  const cutMatch = content.match(
    /\bWhich (?:variant|route|option|one)\b[^?]*\?[*_\s]*/i,
  );
  if (cutMatch && cutMatch.index !== undefined) {
    afterText = content.slice(cutMatch.index + cutMatch[0].length).trim();
  }

  return {
    kind: "comparison",
    corridor,
    variants,
    recommendedName,
    afterText: afterText || undefined,
  };
}

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
