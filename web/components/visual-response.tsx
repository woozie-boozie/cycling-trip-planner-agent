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
 *   1. We have a corridor matched from conversation context
 *   2. The corridor has 2+ known variants in route-variants.ts
 *   3. The message contains 2+ "Option N" or "Option N:" markers
 *
 * Otherwise returns "markdown".
 */
function detectResponseShape(content: string, corridor: Corridor | null): Detection {
  if (!corridor) {
    // No corridor in conversation context yet — fall back even if the
    // message itself has option-like patterns. We need a corridor to know
    // which variant set to render.
    const fromMessage = matchCorridor(content);
    if (!fromMessage) return { kind: "markdown" };
    corridor = fromMessage;
  }

  const variants = getVariants(corridor.id);
  if (!variants) return { kind: "markdown" };

  // Count "Option N" markers — robust to "Option 1:", "**Option 1:**",
  // "## Option 1: Title", "Option 1 — Title".
  const optionMarkerRegex = /\bOption\s+\d+\b/gi;
  const matches = content.match(optionMarkerRegex);
  if (!matches || matches.length < 2) return { kind: "markdown" };

  // Try to detect which variant the agent recommended (if any).
  const recommendedName = inferRecommended(content, variants);

  // Trim the variant-comparison block off the front and pass the
  // remaining "recommendation" prose through MarkdownRenderer below.
  const afterText = content.split(/\bWhich (?:would|route|variant)\b/i).slice(1).join("");

  return {
    kind: "comparison",
    corridor,
    variants,
    recommendedName,
    afterText: afterText.trim() || undefined,
  };
}

/**
 * Look for phrases like "I'd recommend Option 1" or "Go with the V16a"
 * and map back to a variant name. Best-effort; returns undefined if we
 * can't infer.
 */
function inferRecommended(
  content: string,
  variants: RouteVariantSummary[],
): string | undefined {
  const lower = content.toLowerCase();
  // Try title match
  for (const v of variants) {
    const titleLower = v.title.toLowerCase();
    if (
      lower.includes(`recommend ${titleLower}`) ||
      lower.includes(`go with ${titleLower}`) ||
      lower.includes(`choose ${titleLower}`)
    ) {
      return v.name;
    }
  }
  // Try "recommend Option N"
  const m = content.match(/\brecommend(?:ation)?[^.]*\bOption\s+(\d+)/i);
  if (m) {
    const idx = parseInt(m[1], 10) - 1;
    if (idx >= 0 && idx < variants.length) return variants[idx].name;
  }
  return undefined;
}
