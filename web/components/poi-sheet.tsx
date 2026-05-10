"use client";

import { Plus, X } from "lucide-react";
import { LAYER_META, type Poi } from "@/lib/pois";

interface PoiSheetProps {
  poi: Poi;
  onClose: () => void;
  onAdd?: (poi: Poi) => void;
}

/**
 * Bottom sheet for a single POI — slides up over the map when a pin
 * is clicked. Mirrors the mockup's `PoiSheet` shape: coloured icon,
 * category tag, italic-serif name, description, then a metadata row
 * of mono-font key/value pairs.
 */
export function PoiSheet({ poi, onClose, onAdd }: PoiSheetProps) {
  const meta = LAYER_META[poi.layer];
  return (
    <div className="absolute inset-x-3 bottom-3 z-[1000] overflow-hidden rounded-xl border border-border bg-card shadow-lg backdrop-blur-sm">
      <div className="flex items-start gap-3 px-4 py-3">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-white"
          style={{ background: meta.color }}
          aria-hidden
        >
          <PoiGlyph layer={poi.layer} />
        </div>
        <div className="min-w-0 flex-1">
          <div
            className="text-[10px] font-semibold uppercase tracking-wider"
            style={{ color: meta.color }}
          >
            {meta.label}
          </div>
          <div className="text-lg font-bold leading-tight tracking-[-0.015em] text-foreground">
            {poi.label}
          </div>
          <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
            {poi.description}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted/40 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="Close POI details"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      </div>

      {/* Metadata row */}
      {(poi.km_from_start != null ||
        poi.price ||
        poi.rating ||
        poi.species ||
        poi.hours) && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border/60 bg-muted/30 px-4 py-2 font-mono text-[11px] tabular-nums">
          {poi.km_from_start != null && (
            <span className="text-muted-foreground">
              km <strong className="font-semibold text-foreground">{poi.km_from_start}</strong>
            </span>
          )}
          {poi.price && (
            <span className="text-muted-foreground">
              <strong className="font-semibold text-foreground">{poi.price}</strong>
            </span>
          )}
          {poi.rating && (
            <span className="text-muted-foreground">
              <strong className="font-semibold text-foreground">★ {poi.rating}</strong>
            </span>
          )}
          {poi.species && (
            <span className="text-muted-foreground">
              species{" "}
              <strong className="font-semibold text-foreground">{poi.species}</strong>
            </span>
          )}
          {poi.hours && (
            <span className="text-muted-foreground">
              <strong className="font-semibold text-foreground">{poi.hours}</strong>
            </span>
          )}
        </div>
      )}

      {/* Actions */}
      {onAdd && (
        <div className="flex items-center justify-end gap-2 border-t border-border/60 px-4 py-2">
          <button
            type="button"
            onClick={() => onAdd(poi)}
            className="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1 text-[11px] font-semibold text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-3 w-3" aria-hidden />
            Add to plan
          </button>
        </div>
      )}
    </div>
  );
}

/** Compact 8x8 SVG glyph per layer — used inside the round icon badge. */
function PoiGlyph({ layer }: { layer: Poi["layer"] }) {
  switch (layer) {
    case "photo":
      return (
        <svg width="16" height="16" viewBox="-6 -6 12 12">
          <rect x="-4" y="-3" width="8" height="6" rx="0.7" fill="currentColor" />
          <circle cx="0" cy="0.5" r="2" fill="white" />
          <rect x="-1.5" y="-3.8" width="3" height="1" fill="currentColor" />
        </svg>
      );
    case "wildlife":
      return (
        <svg width="16" height="16" viewBox="-6 -6 12 12">
          <ellipse cx="0" cy="2" rx="2.6" ry="2" fill="currentColor" />
          <circle cx="-2" cy="-1.8" r="1.2" fill="currentColor" />
          <circle cx="2" cy="-1.8" r="1.2" fill="currentColor" />
        </svg>
      );
    case "camp":
      return (
        <svg width="16" height="16" viewBox="-6 -6 12 12">
          <path
            d="M 0 -4 L -4.5 4 L 4.5 4 Z M 0 -4 L 0 4"
            stroke="currentColor"
            strokeWidth="1.4"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case "food":
      return (
        <svg
          width="16"
          height="16"
          viewBox="-6 -6 12 12"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
          fill="none"
        >
          <line x1="-2" y1="-4" x2="-2" y2="0.5" />
          <line x1="0" y1="-4" x2="0" y2="0.5" />
          <line x1="2" y1="-4" x2="2" y2="0.5" />
          <line x1="0" y1="0.5" x2="0" y2="4" />
          <line x1="-2" y1="0.5" x2="2" y2="0.5" />
        </svg>
      );
    case "heritage":
      return (
        <svg width="16" height="16" viewBox="-6 -6 12 12" fill="currentColor">
          <path d="M -4 -2 L -4 4 L 4 4 L 4 -2 L 2.5 -2 L 2.5 -3.5 L 1 -3.5 L 1 -2 L -1 -2 L -1 -3.5 L -2.5 -3.5 L -2.5 -2 Z M -1 0 L 1 0 L 1 4 L -1 4 Z" />
        </svg>
      );
    case "repair":
      return (
        <svg width="16" height="16" viewBox="-6 -6 12 12" fill="currentColor">
          <path d="M -3.5 3.5 L 1 -1 A 2.4 2.4 0 1 1 3.5 -3.5 A 2.4 2.4 0 0 1 1 -1 L -3.5 3.5 Z" />
        </svg>
      );
    case "water":
      return (
        <svg width="16" height="16" viewBox="-6 -6 12 12" fill="currentColor">
          <path d="M 0 -4 Q 3.4 0 3.4 2 A 3.4 3.4 0 1 1 -3.4 2 Q -3.4 0 0 -4 Z" />
        </svg>
      );
    case "hospital":
      return (
        <svg width="16" height="16" viewBox="-6 -6 12 12" fill="currentColor">
          <rect x="-1.4" y="-4" width="2.8" height="8" rx="0.4" />
          <rect x="-4" y="-1.4" width="8" height="2.8" rx="0.4" />
        </svg>
      );
    case "ferry":
      return (
        <svg width="16" height="16" viewBox="-6 -6 12 12" fill="currentColor">
          <path d="M -4 1.5 Q 0 -1 4 1.5 L 4 2.5 Q 0 4 -4 2.5 Z M -1.5 -2.5 L 1.5 -2.5 L 1.5 0 L -1.5 0 Z" />
        </svg>
      );
    case "warning":
      return (
        <svg width="16" height="16" viewBox="-6 -6 12 12">
          <path d="M 0 -4 L 4 4 L -4 4 Z" fill="currentColor" />
          <rect x="-0.5" y="-1.5" width="1" height="2.6" fill="white" />
          <circle cx="0" cy="2.5" r="0.7" fill="white" />
        </svg>
      );
    default:
      return <circle r="2" fill="currentColor" />;
  }
}
