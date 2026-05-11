"use client";

import { LAYER_META, LAYER_ORDER, type PoiLayer } from "@/lib/pois";

interface LayerChipsProps {
  /** Currently visible layers */
  active: Set<PoiLayer>;
  /** Per-layer count of POIs available on the current corridor */
  counts: Partial<Record<PoiLayer, number>>;
  /** Toggle a single layer on/off */
  onToggle: (layer: PoiLayer) => void;
}

/**
 * Toggle chips for POI categories. Mockup-styled: rounded pill shape,
 * coloured swatch, badge with count when the layer has results, full
 * fill when active.
 *
 * Layers with zero POIs in the current corridor still render, but are
 * disabled — clearer than hiding them since the user can still see
 * the full taxonomy.
 */
export function LayerChips({ active, counts, onToggle }: LayerChipsProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Layers
      </span>
      {LAYER_ORDER.map((k) => {
        const meta = LAYER_META[k];
        const count = counts[k] ?? 0;
        const isOn = active.has(k);
        const isEmpty = count === 0;
        return (
          <button
            key={k}
            type="button"
            disabled={isEmpty}
            onClick={() => onToggle(k)}
            className={[
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all",
              isEmpty
                ? "cursor-not-allowed border-border/40 bg-card text-muted-foreground/50"
                : isOn
                ? "border-transparent text-white shadow-sm"
                : "border-border bg-card text-foreground/85 hover:border-foreground/30 hover:bg-muted/40",
            ].join(" ")}
            style={
              isOn && !isEmpty
                ? { background: meta.color }
                : undefined
            }
            aria-pressed={isOn}
          >
            <span
              className="h-2 w-2 rounded-full"
              style={{
                background: isOn ? "white" : meta.color,
                opacity: isEmpty ? 0.4 : 1,
              }}
              aria-hidden
            />
            {meta.label}
            {count > 0 && (
              <span
                className={[
                  "ml-0.5 rounded-full px-1.5 font-mono text-[9px] font-semibold tabular-nums",
                  isOn
                    ? "bg-white/20 text-white"
                    : "bg-muted/60 text-muted-foreground",
                ].join(" ")}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
