"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { ImagePlus, Loader2, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ImageValidationError, prepareImage, type PreparedImage } from "@/lib/image";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  isPending: boolean;
  attachedImage: PreparedImage | null;
  onAttachImage: (image: PreparedImage | null) => void;
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled,
  isPending,
  attachedImage,
  onAttachImage,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);

  // Auto-focus on mount and after the agent finishes, so the user can keep typing.
  useEffect(() => {
    if (!isPending) textareaRef.current?.focus();
  }, [isPending]);

  // Auto-grow the textarea up to a sensible cap.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const handleFile = useCallback(
    async (file: File) => {
      setImageError(null);
      try {
        const prepared = await prepareImage(file);
        onAttachImage(prepared);
      } catch (err) {
        if (err instanceof ImageValidationError) {
          setImageError(err.message);
        } else {
          setImageError("Could not attach the image — try a different file.");
        }
      }
    },
    [onAttachImage],
  );

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) void handleFile(file);
      // Reset so re-selecting the same file re-fires onChange.
      e.target.value = "";
    },
    [handleFile],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDraggingOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) void handleFile(file);
    },
    [handleFile],
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingOver(false);
  }, []);

  const canSubmit = !disabled && !isPending;

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (canSubmit) onSubmit();
    }
  }

  return (
    <div className="surface-glass border-t border-border/50">
      <div
        className="mx-auto max-w-5xl px-4 py-4"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Attached image preview */}
        {attachedImage ? (
          <div className="mb-3 flex items-start gap-3 rounded-lg border border-border/40 bg-card p-2.5">
            <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-md bg-muted">
              <Image
                src={attachedImage.dataUrl}
                alt="Attached preview"
                fill
                sizes="80px"
                className="object-cover"
                unoptimized
              />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-foreground">
                Image attached · {attachedImage.payload.media_type.replace("image/", "").toUpperCase()}
              </p>
              <p className="mt-0.5 text-[11px] text-muted-foreground/80">
                The agent will inspect this image and use it as context for the trip plan.
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => onAttachImage(null)}
              className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">Remove image</span>
            </Button>
          </div>
        ) : null}

        {/* Image error */}
        {imageError ? (
          <div className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {imageError}
          </div>
        ) : null}

        {/* Drop overlay */}
        <div
          className={
            isDraggingOver
              ? "flex items-end gap-2 rounded-2xl border-2 border-dashed border-primary bg-primary/10 p-2 transition-colors"
              : "flex items-end gap-2 rounded-2xl border border-border/50 bg-card/40 p-2 transition-colors focus-within:border-primary/40 focus-within:ring-1 focus-within:ring-primary/30"
          }
        >
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => fileInputRef.current?.click()}
            disabled={isPending}
            className="h-9 w-9 shrink-0 text-muted-foreground hover:text-foreground"
            title="Attach an image"
          >
            <ImagePlus className="h-4 w-4" aria-hidden />
            <span className="sr-only">Attach image</span>
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            onChange={handleFileInputChange}
            className="hidden"
          />

          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              attachedImage
                ? "Add optional context for the image (e.g. 'plan this for me, June, camping')…"
                : "Ask me to plan a multi-day cycling trip — or drop a route screenshot…"
            }
            disabled={isPending}
            rows={1}
            className="min-h-0 resize-none border-0 bg-transparent px-2 py-1.5 text-sm shadow-none focus-visible:ring-0"
          />

          <Button
            type="button"
            size="icon"
            onClick={onSubmit}
            disabled={!canSubmit}
            className="h-9 w-9 shrink-0"
          >
            {isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <Send className="h-4 w-4" aria-hidden />
            )}
            <span className="sr-only">Send</span>
          </Button>
        </div>

        <p className="mt-2 text-center text-[11px] text-muted-foreground/70">
          Enter sends · Shift+Enter for a new line · drop an image or click the icon to attach
        </p>
      </div>
    </div>
  );
}
