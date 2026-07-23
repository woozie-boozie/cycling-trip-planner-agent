"""Firebase ID-token verification — Phase 3 (auth).

The web app signs every visitor in with Firebase Auth (anonymous by
default, Google when they upgrade) and sends the ID token as
``Authorization: Bearer <token>`` on every request. This module verifies
that token and exposes the caller's stable ``uid`` as a FastAPI
dependency.

Verification is offline: firebase-admin checks the JWT signature against
Google's public certs (cached) and the audience against our project id —
no service-account key required on Cloud Run.

Rollout switch: ``REQUIRE_AUTH`` env var.
  - unset / "false"  → tokenless requests pass through with uid=None
                       (used while old frontends are still live)
  - "true"           → tokenless or invalid-token requests get a 401
"""

from __future__ import annotations

import os

import firebase_admin
import structlog
from fastapi import Header, HTTPException, status
from firebase_admin import auth as fb_auth

log = structlog.get_logger()

_DEFAULT_PROJECT_ID = "cycling-agent-prod"


def _get_app() -> firebase_admin.App:
    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app(
            options={
                "projectId": os.getenv("FIREBASE_PROJECT_ID", _DEFAULT_PROJECT_ID)
            }
        )


def _require_auth() -> bool:
    return os.getenv("REQUIRE_AUTH", "false").strip().lower() == "true"


async def get_uid(authorization: str | None = Header(default=None)) -> str | None:
    """FastAPI dependency: the verified Firebase uid of the caller.

    Returns None only while REQUIRE_AUTH is off (rollout compatibility).
    """
    if not authorization or not authorization.startswith("Bearer "):
        if _require_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sign-in required. Send a Firebase ID token as a Bearer header.",
            )
        return None

    token = authorization.removeprefix("Bearer ").strip()
    try:
        decoded = fb_auth.verify_id_token(token, app=_get_app())
    except Exception as exc:  # expired, malformed, wrong audience, …
        log.warning("auth.token.invalid", error=str(exc)[:200])
        if _require_auth():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired credentials — sign in again.",
            ) from exc
        return None

    uid: str = decoded["uid"]
    return uid
