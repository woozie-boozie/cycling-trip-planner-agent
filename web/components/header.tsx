"use client";

import { Bike, Map, RotateCcw, Type, UserCog } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { ViewMode } from "@/lib/view-mode";

interface HeaderProps {
  sessionId: string | null;
  onReset: () => void;
  hasProfile?: boolean;
  onEditProfile?: () => void;
  viewMode?: ViewMode;
  onToggleViewMode?: () => void;
}

export function Header({
  sessionId,
  onReset,
  hasProfile = false,
  onEditProfile,
  viewMode,
  onToggleViewMode,
}: HeaderProps) {
  const sessionLabel = sessionId ? sessionId.slice(0, 8) : "new";

  return (
    <header className="surface-glass sticky top-0 z-30 border-b border-border/50">
      <div className="mx-auto flex h-14 max-w-[1480px] items-center gap-4 px-4 lg:px-10 xl:px-14">
        {/* Brand */}
        <div className="flex shrink-0 items-center gap-2.5">
          <div className="relative flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-[0_2px_8px_-2px_rgba(255,61,20,0.5)]">
            <Bike className="h-3.5 w-3.5" aria-hidden />
          </div>
          <span className="text-[15px] font-semibold tracking-[-0.01em] text-foreground">
            Cyclepath
          </span>
        </div>

        {/* Center — session metadata, monospace, dim by default */}
        <div className="flex flex-1 items-center justify-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
          <span className="hidden sm:inline">session</span>
          <span className="hidden text-muted-foreground/60 sm:inline">·</span>
          <span className="rounded bg-muted/40 px-1.5 py-0.5 normal-case tracking-normal text-foreground/80">
            {sessionLabel}
          </span>
          <span className="hidden text-muted-foreground/60 sm:inline">·</span>
          <span className="hidden sm:inline">claude-sonnet-4-5</span>
        </div>

        {/* Right cluster */}
        <div className="flex shrink-0 items-center gap-1.5">
          {hasProfile && (
            <Badge
              variant="outline"
              className="hidden border-primary/30 bg-primary/[0.08] text-[9.5px] font-semibold uppercase tracking-[0.08em] text-primary sm:inline-flex"
            >
              personalised
            </Badge>
          )}
          {onToggleViewMode && viewMode && (
            <button
              type="button"
              onClick={onToggleViewMode}
              className="inline-flex h-7 items-center gap-1 rounded-full border border-border bg-card px-2 text-[11px] font-medium text-foreground/85 transition-colors hover:border-primary/40 hover:text-foreground"
              title={
                viewMode === "visual"
                  ? "Switch to text mode (markdown)"
                  : "Switch to visual mode (cards + map)"
              }
            >
              {viewMode === "visual" ? (
                <Map className="h-3 w-3 text-primary" aria-hidden />
              ) : (
                <Type className="h-3 w-3" aria-hidden />
              )}
              <span className="hidden sm:inline">
                {viewMode === "visual" ? "Visual" : "Text"}
              </span>
            </button>
          )}
          {onEditProfile && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onEditProfile}
              className="h-7 px-2 text-muted-foreground hover:text-foreground"
              title={hasProfile ? "Edit your profile" : "Set up your profile"}
            >
              <UserCog className="h-3.5 w-3.5" aria-hidden />
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onReset}
            disabled={!sessionId}
            className="h-7 px-2 text-muted-foreground hover:text-foreground"
            title="Start a new conversation"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
          </Button>
        </div>
      </div>
    </header>
  );
}
