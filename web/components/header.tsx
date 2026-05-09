"use client";

import { Bike, RotateCcw, UserCog } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface HeaderProps {
  sessionId: string | null;
  onReset: () => void;
  hasProfile?: boolean;
  onEditProfile?: () => void;
}

export function Header({
  sessionId,
  onReset,
  hasProfile = false,
  onEditProfile,
}: HeaderProps) {
  const sessionLabel = sessionId ? sessionId.slice(0, 8) : "new";

  return (
    <header className="border-b border-border/40 bg-card/40 backdrop-blur supports-[backdrop-filter]:bg-card/30">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary/15 p-2 text-primary ring-1 ring-primary/20">
            <Bike className="h-5 w-5" aria-hidden />
          </div>
          <div>
            <h1 className="text-base font-semibold leading-tight tracking-tight text-foreground">
              Cycling Trip Planner
            </h1>
            <p className="text-xs text-muted-foreground leading-tight">
              An AI agent that plans multi-day rides
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {hasProfile && (
            <Badge
              variant="outline"
              className="hidden border-primary/40 bg-primary/10 text-[10px] text-primary sm:inline-flex"
            >
              personalised
            </Badge>
          )}
          <Badge variant="secondary" className="font-mono text-[10px] tracking-wider">
            session · {sessionLabel}
          </Badge>
          {onEditProfile && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onEditProfile}
              className="text-muted-foreground hover:text-foreground"
              title={hasProfile ? "Edit your profile" : "Set up your profile"}
            >
              <UserCog className="h-3.5 w-3.5" aria-hidden />
              <span className="hidden sm:inline">
                {hasProfile ? "Edit profile" : "Set up profile"}
              </span>
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onReset}
            disabled={!sessionId}
            className="text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden />
            <span className="hidden sm:inline">New conversation</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
