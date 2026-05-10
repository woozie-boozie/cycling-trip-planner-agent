"use client";

/**
 * View-mode hook — controls the global text/visual rendering toggle.
 *
 * Two coexisting renderers:
 *   - "text"   : the production-shipped markdown rendering (safe fallback)
 *   - "visual" : the new visual layer (route comparison cards, big map,
 *                POI layer chips, day-by-day cards)
 *
 * The toggle is global (one button in the header, applies everywhere) and
 * persisted in localStorage. New users default to "visual" so the redesigned
 * experience is what they see first; users with an existing preference
 * (returning visits) get whichever they last chose.
 *
 * If anything in the visual layer breaks at runtime, clicking the toggle
 * reverts to text mode — the production rendering is the safety net.
 */

import { useCallback, useEffect, useState } from "react";

export type ViewMode = "text" | "visual";

const STORAGE_KEY = "view_mode";
const DEFAULT_MODE: ViewMode = "visual";

function readStoredMode(): ViewMode {
  if (typeof window === "undefined") return DEFAULT_MODE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "text" || raw === "visual") return raw;
  } catch {
    // localStorage may be unavailable (incognito, restricted) — fall through
  }
  return DEFAULT_MODE;
}

function writeStoredMode(mode: ViewMode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // ignore storage failures
  }
}

export function useViewMode(): {
  mode: ViewMode;
  setMode: (next: ViewMode) => void;
  toggle: () => void;
} {
  // SSR-safe initial state — start with the default, hydrate on mount.
  const [mode, setModeState] = useState<ViewMode>(DEFAULT_MODE);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setModeState(readStoredMode());
  }, []);

  const setMode = useCallback((next: ViewMode) => {
    writeStoredMode(next);
    setModeState(next);
  }, []);

  const toggle = useCallback(() => {
    setModeState((prev) => {
      const next = prev === "visual" ? "text" : "visual";
      writeStoredMode(next);
      return next;
    });
  }, []);

  return { mode, setMode, toggle };
}
