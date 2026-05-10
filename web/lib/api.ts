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

import type {
  ChatRequest,
  ChatResponse,
  TraceResponse,
  UserProfile,
  UserProfileCreate,
} from "@/lib/types";

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

export async function postProfile(
  body: UserProfileCreate,
  signal?: AbortSignal,
): Promise<UserProfile> {
  const res = await fetch(`${API_URL}/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  return jsonOrThrow<UserProfile>(res);
}

export async function getProfile(
  profileId: string,
  signal?: AbortSignal,
): Promise<UserProfile> {
  const res = await fetch(
    `${API_URL}/profile/${encodeURIComponent(profileId)}`,
    { signal },
  );
  return jsonOrThrow<UserProfile>(res);
}

// ---------------------------------------------------------------------------
// Streaming chat — Phase 1.10c
// ---------------------------------------------------------------------------

/** Events that arrive over POST /chat/stream as Server-Sent Events. */
export type ChatStreamEvent =
  | { type: "session"; session_id: string }
  | { type: "text_delta"; iteration: number; text: string }
  | { type: "tool_use_start"; iteration: number; id: string; name: string }
  | {
      type: "tool_use_complete";
      iteration: number;
      id: string;
      name: string;
      input: Record<string, unknown>;
    }
  | {
      type: "tool_result";
      iteration: number;
      id: string;
      name: string;
      is_error: boolean;
      latency_ms: number;
    }
  | { type: "iteration_end"; iteration: number; stop_reason: string }
  | {
      type: "done";
      session_id: string;
      stop_reason: string;
      iterations: number;
      input_tokens: number;
      output_tokens: number;
      cache_read_tokens?: number;
      cache_creation_tokens?: number;
      tool_calls: { name: string; args: string[] }[];
      error?: string;
    }
  /** Mid-stream error from the backend — emitted instead of raising so the
   *  SSE connection can deliver a structured message. `kind` lets the UI
   *  pick a specific recovery hint. */
  | {
      type: "error";
      kind: "rate_limit" | "timeout" | "network" | "unknown";
      message: string;
    };

/**
 * POST /chat/stream — consumes Server-Sent Events.
 *
 * Uses native `fetch` + `ReadableStream` rather than `EventSource` because
 * EventSource only supports GET. Each SSE event is a JSON object; we parse
 * `data: {...}\n\n` frames and call `onEvent` per parsed object.
 */
export async function postChatStream(
  req: ChatRequest,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) {
    let details: unknown;
    try {
      details = await res.json();
    } catch {
      details = await res.text().catch(() => "");
    }
    throw new ApiError(`${res.status} ${res.statusText}`, res.status, details);
  }
  if (!res.body) {
    throw new Error("/chat/stream returned no body");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Split on double-newline frame boundary; keep any trailing partial frame
    // in `buffer` for the next read.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const trimmed = frame.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const json = trimmed.slice(6);
      try {
        onEvent(JSON.parse(json) as ChatStreamEvent);
      } catch {
        // Skip malformed frames rather than crashing the stream.
      }
    }
  }
}

export const apiBaseUrl = API_URL;
