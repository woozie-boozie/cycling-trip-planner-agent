/**
 * API client for the cycling trip planner backend.
 *
 * Two endpoints today:
 *   POST /chat           — single conversational turn
 *   GET  /trace/{id}     — full ordered event log for a session
 *
 * The base URL is configured via NEXT_PUBLIC_API_URL. In dev that's
 * http://localhost:8000 (FastAPI); in prod it points at the Cloud Run URL
 * set in Vercel's project env vars.
 */

import type { ChatRequest, ChatResponse, TraceResponse } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let details: unknown;
    try {
      details = await res.json();
    } catch {
      details = await res.text().catch(() => "");
    }
    throw new ApiError(`${res.status} ${res.statusText}`, res.status, details);
  }
  return (await res.json()) as T;
}

export async function postChat(req: ChatRequest, signal?: AbortSignal): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  return jsonOrThrow<ChatResponse>(res);
}

export async function getTrace(sessionId: string, signal?: AbortSignal): Promise<TraceResponse> {
  const res = await fetch(`${API_URL}/trace/${encodeURIComponent(sessionId)}`, {
    signal,
  });
  return jsonOrThrow<TraceResponse>(res);
}

export const apiBaseUrl = API_URL;
