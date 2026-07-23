"""HTTP routes for the cycling trip planner agent.

Endpoints:
  GET  /health                   — liveness probe (was /healthz pre-2026-05-11;
                                   Google Cloud Run reserves /healthz at the GFE
                                   edge, so the path renamed for prod parity)
  GET  /                         — root, same shape as /health
  POST /chat                     — single conversational turn (the brief's required endpoint)
  POST /profile                  — upsert a cyclist profile (Phase 2D)
  GET  /profile/{profile_id}     — fetch a cyclist profile (Phase 2D)
  DELETE /profile/{profile_id}   — drop a profile (Phase 2D)
  GET  /sessions                 — list active session ids
  GET  /sessions/{session_id}    — full conversation state for a session
  DELETE /sessions/{session_id}  — drop a session
  GET  /trace/{session_id}       — observability — full ordered trace
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Literal

import structlog
from anthropic import APIConnectionError, APITimeoutError, AsyncAnthropic, RateLimitError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.agent import (
    AgentLoopExceeded,
    AgentResponse,
    ConversationState,
    TraceEvent,
    run_turn,
    run_turn_stream,
)
from src.api.auth import get_uid
from src.api.dependencies import (
    get_anthropic_client,
    get_profile_store,
    get_session_store,
)
from src.sessions import (
    ProfileStore,
    SessionConflict,
    SessionStore,
    UserProfile,
    UserProfileCreate,
)

log = structlog.get_logger(__name__)

router = APIRouter()


def _classify_stream_error(exc: BaseException) -> tuple[str, str]:
    """Map a streaming-turn exception to a (kind, user-message) tuple.

    The streaming endpoint can't raise to FastAPI's exception handler once
    headers have been sent — instead it yields a structured `error` SSE
    event the frontend renders inline. The `kind` field lets the UI pick
    a specific recovery hint (e.g. "Start a new trip" for context-overflow
    cases) without parsing prose.
    """
    if isinstance(exc, SessionConflict):
        return (
            "session_conflict",
            "This session was modified by another request in flight. "
            "Refetch the session and retry — your message was processed "
            "but not persisted.",
        )
    if isinstance(exc, RateLimitError):
        return (
            "rate_limit",
            "Hit Anthropic's per-minute rate limit. Wait ~60 seconds and "
            "retry, or start a new trip to shrink the context.",
        )
    if isinstance(exc, APITimeoutError):
        return ("timeout", "The model took too long to respond. Try again.")
    if isinstance(exc, APIConnectionError):
        return (
            "network",
            "Couldn't reach the model. Check your connection and try again.",
        )
    return ("unknown", "Something went wrong during this turn. Try again.")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """Liveness probe for Cloud Run + local dev.

    Path is ``/health`` (not ``/healthz``) because Google's Cloud Run
    Frontend Service reserves ``/healthz`` at the edge for its own
    infrastructure probing — requests to ``/healthz`` never reach the
    container. Verified empirically against ``cycling-trip-planner-backend``
    in europe-west1 on 2026-05-11: ``/randomx`` and ``/`` show up in the
    container access logs but ``/healthz`` doesn't.
    """
    return HealthResponse(status="ok", service="cycling-trip-planner-agent", version="0.1.0")


@router.get("/", response_model=HealthResponse, tags=["meta"])
async def root() -> HealthResponse:
    return HealthResponse(status="ok", service="cycling-trip-planner-agent", version="0.1.0")


# ---------------------------------------------------------------------------
# Chat — the brief's required endpoint
# ---------------------------------------------------------------------------


class ChatImage(BaseModel):
    """Optional image attachment for multimodal /chat requests.

    Mirrors Anthropic's content-block image format. The agent receives the
    image as the first content block of the user message and reasons about
    it directly — no separate "extract intent" pass.

    Validation is strict at this boundary: a malformed base64 payload
    surfaces as HTTP 422 here, not as an opaque HTTP 500 from inside the
    agent loop after we've already spent tokens on the round-trip.
    """

    media_type: Literal["image/jpeg", "image/png", "image/webp", "image/gif"] = Field(
        description="MIME type. Anthropic vision supports JPEG, PNG, WebP, and GIF."
    )
    base64_data: str = Field(
        min_length=1,
        max_length=10_000_000,
        description="Base64-encoded image data. Cap at ~7MB encoded (~5MB decoded).",
    )

    @field_validator("base64_data")
    @classmethod
    def _validate_base64(cls, v: str) -> str:
        """Ensure ``base64_data`` is well-formed base64.

        Pydantic's default ``str`` type accepts any string, so a junk
        payload like "not actually base64!!!" would pass validation,
        reach the Anthropic SDK, and fail with a confusing 500. Catching
        it here turns the failure into a deterministic 422 with a clear
        ``"invalid base64 payload"`` detail.
        """
        try:
            # validate=True rejects non-base64 chars; b64decode handles
            # both URL-safe and standard encoding internally.
            base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError(f"invalid base64 payload: {e}") from e
        return v


class ChatRequest(BaseModel):
    """Body for POST /chat.

    Pass `session_id` to continue an existing conversation. Omit it to start a
    fresh one — the response will include a generated id you can re-send.

    Optionally attach an `image` (base64) to send a multimodal turn — the
    agent will reason over the image (e.g. a Strava/Komoot screenshot) AND
    the text in one loop.
    """

    message: str = Field(
        min_length=1,
        max_length=4000,
        description="The user's message for this turn.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional. If provided and the session exists, the conversation resumes. "
        "If omitted, a fresh session is created.",
    )
    image: ChatImage | None = Field(
        default=None,
        description=(
            "Optional. Base64-encoded image to attach to the user's message. "
            "When provided, the agent receives both the image and the text as content blocks."
        ),
    )
    profile_id: str | None = Field(
        default=None,
        description=(
            "Optional cyclist profile id (Phase 2D). When supplied and known, "
            "the agent personalises its planning to this rider's experience, "
            "priorities, and dietary needs. Created via POST /profile."
        ),
    )


class ChatResponse(BaseModel):
    """Reply for POST /chat.

    Always includes the `session_id` so a client without prior context can use
    the response directly to continue the conversation.
    """

    session_id: str
    message: str = Field(description="The agent's final assistant text for this turn.")
    stop_reason: str
    iterations: int = Field(description="LLM round-trips required to resolve this turn.")
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = Field(
        default=0,
        description="Input tokens served from Anthropic's prompt cache (billed at ~10% rate).",
    )
    cache_creation_tokens: int = Field(
        default=0,
        description="Input tokens written to prompt cache this turn (one-off ~125% cost).",
    )
    tool_calls: list[dict[str, Any]] = Field(
        description="Summary of tools invoked this turn — names and argument keys."
    )


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(
    request: ChatRequest,
    _uid: str | None = Depends(get_uid),
    store: SessionStore = Depends(get_session_store),
    profile_store: ProfileStore = Depends(get_profile_store),
    client: AsyncAnthropic = Depends(get_anthropic_client),
) -> ChatResponse:
    """Run one conversational turn against the cycling trip planner agent.

    Behavior:
      - With no session_id: creates a fresh ConversationState.
      - With a known session_id: resumes the existing conversation.
      - With an unknown session_id: 404. (We don't silently create — that
        would mask client bugs.)

    The agent's tool-use loop runs to completion before the response returns.
    Multi-turn flows are coordinated by the client re-sending the session_id.
    """
    if request.session_id is None:
        state = ConversationState()
        is_new = True
    else:
        existing = await store.get(request.session_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session {request.session_id!r} not found",
            )
        state = existing
        is_new = False

    # Load the profile (if requested + known). Treat missing profile as a soft
    # miss — log it but proceed without personalisation; mirrors the same
    # contract as session expiry on /chat (frontend handles re-onboarding).
    profile: UserProfile | None = None
    if request.profile_id is not None:
        profile = await profile_store.get(request.profile_id)
        if profile is None:
            log.info(
                "chat.profile.unknown",
                session_id=state.session_id,
                profile_id=request.profile_id,
            )

    log.info(
        "chat.turn.start",
        session_id=state.session_id,
        is_new=is_new,
        message_len=len(request.message),
        has_image=request.image is not None,
        has_profile=profile is not None,
    )

    # Multimodal: build a content list with the image as the first block,
    # text as the second. Anthropic accepts a string OR a list of content
    # blocks for the user message — see docs/agent-loop.md.
    user_message: str | list[dict[str, Any]]
    if request.image is not None:
        user_message = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": request.image.media_type,
                    "data": request.image.base64_data,
                },
            },
            {"type": "text", "text": request.message},
        ]
    else:
        user_message = request.message

    try:
        response: AgentResponse = await run_turn(
            state, user_message, client=client, profile=profile
        )
    except AgentLoopExceeded as e:
        log.warning("chat.loop_exceeded", session_id=state.session_id, error=str(e))
        # Persist the partial state so /trace can still show what happened.
        # Tolerate a SessionConflict here — if another writer beat us to
        # the partial save, /trace will read their version (also partial)
        # which is fine for observability.
        try:
            await store.put(state)
        except SessionConflict:
            log.info(
                "chat.loop_exceeded.partial_save_conflict",
                session_id=state.session_id,
            )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="agent did not converge — see /trace for what it tried",
        ) from e

    try:
        await store.put(state)
    except SessionConflict as e:
        # Another /chat call to the same session_id wrote between our get
        # and put. The user's message was processed by Claude but isn't
        # persisted. Return 409 so the client can refetch the session and
        # retry — frontend's session-conflict UI surfaces this.
        log.info(
            "chat.session_conflict",
            session_id=state.session_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "kind": "session_conflict",
                "message": (
                    "This session was modified by another request in flight. "
                    "Refetch the session and retry — your message was processed "
                    "but not persisted."
                ),
                "session_id": state.session_id,
            },
        ) from e

    log.info(
        "chat.turn.done",
        session_id=state.session_id,
        iterations=response.iterations,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        tool_calls=len(response.tool_calls),
    )

    return ChatResponse(
        session_id=response.session_id,
        message=response.message,
        stop_reason=response.stop_reason,
        iterations=response.iterations,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cache_read_tokens=response.cache_read_tokens,
        cache_creation_tokens=response.cache_creation_tokens,
        tool_calls=response.tool_calls,
    )


# ---------------------------------------------------------------------------
# Streaming chat — Phase 1.10c · Server-Sent Events for live agent thinking
# ---------------------------------------------------------------------------


@router.post("/chat/stream", tags=["chat"])
async def chat_stream(
    request: ChatRequest,
    _uid: str | None = Depends(get_uid),
    store: SessionStore = Depends(get_session_store),
    profile_store: ProfileStore = Depends(get_profile_store),
    client: AsyncAnthropic = Depends(get_anthropic_client),
) -> StreamingResponse:
    """Server-Sent Events variant of /chat — streams the agent's reasoning live.

    Each SSE event is a JSON object: see ``src/agent/streaming.py`` for the
    full event protocol (text_delta / tool_use_start / tool_use_complete /
    tool_result / iteration_end / done).

    Headers:
      - ``Cache-Control: no-cache`` — proxies must not cache the stream
      - ``X-Accel-Buffering: no`` — nginx/Cloud Run buffer-disable hint
      - ``Connection: keep-alive``
    """
    # Session resolution mirrors POST /chat exactly so the streaming path
    # has the same semantics (404 on unknown session_id, fresh otherwise).
    if request.session_id is None:
        state = ConversationState()
        is_new = True
    else:
        existing = await store.get(request.session_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session {request.session_id!r} not found",
            )
        state = existing
        is_new = False

    # Profile soft-miss — same contract as /chat.
    profile: UserProfile | None = None
    if request.profile_id is not None:
        profile = await profile_store.get(request.profile_id)
        if profile is None:
            log.info(
                "chat.stream.profile.unknown",
                session_id=state.session_id,
                profile_id=request.profile_id,
            )

    log.info(
        "chat.stream.turn.start",
        session_id=state.session_id,
        is_new=is_new,
        message_len=len(request.message),
        has_image=request.image is not None,
        has_profile=profile is not None,
    )

    # Multimodal user-message construction — same pattern as /chat.
    user_message: str | list[dict[str, Any]]
    if request.image is not None:
        user_message = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": request.image.media_type,
                    "data": request.image.base64_data,
                },
            },
            {"type": "text", "text": request.message},
        ]
    else:
        user_message = request.message

    async def event_stream() -> Any:
        # Always emit a "session_id" preamble so the frontend can persist
        # it before the first text_delta arrives. Avoids a "session is null"
        # window in the UI when the user starts a fresh conversation.
        yield (
            f"data: {json.dumps({'type': 'session', 'session_id': state.session_id})}\n\n"
        )
        try:
            async for event in run_turn_stream(
                state, user_message, client=client, profile=profile
            ):
                # Race condition fix: persist state BEFORE yielding `done` so
                # the frontend's immediate `refreshTrace(session_id)` finds
                # the session. Otherwise the trace fetch races the finally
                # block, returns 404, and the frontend treats it as a stale
                # session (clears the id, blanks the trace panel).
                if event.get("type") == "done":
                    await store.put(state)
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # noqa: BLE001
            # SSE response — headers are already sent, so we can't raise to
            # FastAPI's exception handler. Convert known errors into a
            # structured `error` event the frontend can render cleanly.
            kind, message = _classify_stream_error(exc)
            log.warning(
                "chat.stream.turn.error",
                session_id=state.session_id,
                kind=kind,
                error=str(exc),
            )
            yield (
                f"data: {json.dumps({'type': 'error', 'kind': kind, 'message': message})}\n\n"
            )
        finally:
            # Backstop persist for error paths and partial streams (when
            # the agent loop hits an exception before yielding `done`).
            # If the `done` branch above already wrote, the second put
            # here will SessionConflict — that's expected, not an error.
            # We MUST swallow it: an uncaught exception in a StreamingResponse
            # generator's finally crashes the ASGI handler AFTER the
            # response body has been sent, which surfaces as a network
            # error on the frontend even though the user got their reply.
            try:
                await store.put(state)
            except SessionConflict:
                # The done-path put already persisted. Nothing to do.
                pass
            except Exception as exc:  # noqa: BLE001
                # Any other persistence error in the backstop path: log
                # and move on. The user already got their stream.
                log.warning(
                    "chat.stream.backstop_put.failed",
                    session_id=state.session_id,
                    error=str(exc),
                )
            log.info(
                "chat.stream.turn.done",
                session_id=state.session_id,
                total_input_tokens=state.total_input_tokens,
                total_output_tokens=state.total_output_tokens,
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Profile — Phase 2D · onboarding wizard backend
# ---------------------------------------------------------------------------


@router.post("/profile", response_model=UserProfile, tags=["profile"])
async def upsert_profile(
    create: UserProfileCreate,
    uid: str | None = Depends(get_uid),
    profile_store: ProfileStore = Depends(get_profile_store),
) -> UserProfile:
    """Create or update a cyclist profile.

    Idempotent: send the same `profile_id` to update the existing profile,
    omit it for a fresh one (server generates a UUID4). The returned object
    includes the canonical `profile_id` the client should persist locally.

    `max_daily_km_comfort` is derived from `experience` server-side — clients
    don't need to know the mapping.
    """
    profile = create.to_profile()
    profile.firebase_uid = uid
    return await profile_store.upsert(profile)


@router.get("/profile/{profile_id}", response_model=UserProfile, tags=["profile"])
async def get_profile(
    profile_id: str,
    uid: str | None = Depends(get_uid),
    profile_store: ProfileStore = Depends(get_profile_store),
) -> UserProfile:
    profile = await profile_store.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    if profile.firebase_uid and uid and profile.firebase_uid != uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your profile")
    return profile


@router.delete("/profile/{profile_id}", tags=["profile"])
async def delete_profile(
    profile_id: str,
    uid: str | None = Depends(get_uid),
    profile_store: ProfileStore = Depends(get_profile_store),
) -> dict[str, bool]:
    existing = await profile_store.get(profile_id)
    if existing and existing.firebase_uid and uid and existing.firebase_uid != uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your profile")
    deleted = await profile_store.delete(profile_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Sessions — read/list/delete
# ---------------------------------------------------------------------------


class SessionDetail(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    total_turns: int
    total_input_tokens: int
    total_output_tokens: int
    messages: list[dict[str, Any]]


class SessionList(BaseModel):
    session_ids: list[str]
    count: int


@router.get("/sessions", response_model=SessionList, tags=["sessions"])
async def list_sessions(
    _uid: str | None = Depends(get_uid),
    store: SessionStore = Depends(get_session_store),
) -> SessionList:
    ids = await store.list_ids()
    return SessionList(session_ids=ids, count=len(ids))


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetail,
    tags=["sessions"],
)
async def get_session(
    session_id: str, store: SessionStore = Depends(get_session_store)
) -> SessionDetail:
    state = await store.get(session_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return SessionDetail(
        session_id=state.session_id,
        created_at=state.created_at.isoformat(),
        updated_at=state.updated_at.isoformat(),
        total_turns=state.total_turns,
        total_input_tokens=state.total_input_tokens,
        total_output_tokens=state.total_output_tokens,
        messages=state.messages,
    )


@router.delete("/sessions/{session_id}", tags=["sessions"])
async def delete_session(
    session_id: str,
    _uid: str | None = Depends(get_uid),
    store: SessionStore = Depends(get_session_store),
) -> dict[str, bool]:
    deleted = await store.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Trace — observability for the agent loop
# ---------------------------------------------------------------------------


class TraceResponse(BaseModel):
    session_id: str
    events: list[TraceEvent]
    event_count: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float = Field(
        description=(
            "Rough cost estimate using Sonnet-tier pricing — accurate to ~10%, "
            "intended for at-a-glance debugging not billing."
        )
    )


# Sonnet 4.5 / 4.6 input ≈ $3 / 1M tokens, output ≈ $15 / 1M tokens.
_INPUT_COST_PER_1M = 3.0
_OUTPUT_COST_PER_1M = 15.0


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens / 1_000_000) * _INPUT_COST_PER_1M
        + (output_tokens / 1_000_000) * _OUTPUT_COST_PER_1M,
        4,
    )


@router.get("/trace/{session_id}", response_model=TraceResponse, tags=["trace"])
async def get_trace(
    session_id: str,
    _uid: str | None = Depends(get_uid),
    store: SessionStore = Depends(get_session_store),
) -> TraceResponse:
    """Return the full ordered trace of a session — every user message,
    assistant text, tool call, and tool result, in order, with token usage
    and estimated cost.

    This is what makes the agent inspectable. Useful in the demo for showing
    Edo and Sunny exactly how the agent reasoned over multiple turns.
    """
    state = await store.get(session_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    return TraceResponse(
        session_id=state.session_id,
        events=state.trace,
        event_count=len(state.trace),
        total_input_tokens=state.total_input_tokens,
        total_output_tokens=state.total_output_tokens,
        estimated_cost_usd=_estimate_cost(state.total_input_tokens, state.total_output_tokens),
    )


# ---------------------------------------------------------------------------
# GPX export — the canonical artifact a cyclist rides with
# ---------------------------------------------------------------------------


@router.get("/route/gpx", tags=["route"])
async def route_gpx(
    start: str = Query(..., description="Corridor start city (e.g. 'London')"),
    end: str = Query(..., description="Corridor end city (e.g. 'Paris')"),
    variant: str | None = Query(
        None, description="Variant name from CorridorVariant.name (e.g. 'v16a_beauvais'). Defaults to the corridor's is_default variant."
    ),
    daily_km: float = Query(
        80.0, gt=0, le=300, description="Daily target km — used to derive the per-day split for mode=day when from/to are not supplied."
    ),
    mode: Literal["full", "day"] = Query(
        "full", description="full = whole trip in one GPX; day = a single day's stretch."
    ),
    day: int | None = Query(
        None, ge=1, description="1-indexed day number. Required when mode=day unless from/to are supplied."
    ),
    from_city: str | None = Query(
        None,
        alias="from",
        description="Day start waypoint name (preferred for mode=day — ensures the GPX boundaries match the UI exactly).",
    ),
    to_city: str | None = Query(
        None,
        alias="to",
        description="Day end waypoint name (preferred for mode=day — ensures the GPX boundaries match the UI exactly).",
    ),
) -> Response:
    """Return a GPX 1.1 file for the planned route. The file includes the
    BRouter track polyline + named ``<wpt>`` pins for every overnight stop
    so head-units (Garmin, Wahoo, Karoo) show pins at hotels and ferries
    along the track.

    Reuses BRouter's geometry from the shared segment cache — the first
    call after a plan is sub-second; subsequent downloads are instant.
    """
    from src.tools.route_gpx import GPX_MIME, build_gpx_for_variant

    if mode == "day" and day is None and not (from_city and to_city):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="`day` (or both `from` and `to`) is required when mode=day",
        )

    try:
        build = await build_gpx_for_variant(
            start=start,
            end=end,
            variant_name=variant,
            daily_km=daily_km,
            mode=mode,
            day=day,
            from_city=from_city,
            to_city=to_city,
        )
    except Exception as exc:
        log.exception("gpx_build_failed", start=start, end=end, variant=variant)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to build GPX: {exc!s}",
        ) from exc

    if build is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No GPX available for {start} → {end}"
                + (f" variant={variant}" if variant else "")
                + (f" day={day}" if day else "")
            ),
        )

    return Response(
        content=build.xml,
        media_type=GPX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{build.filename}"',
            # CORS-friendly headers so a browser <a download> from the web
            # app can read the filename from this header.
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
