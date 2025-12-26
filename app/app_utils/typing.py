"""Shared typing models for the FastAPI app."""

from __future__ import annotations

from pydantic import BaseModel


class Feedback(BaseModel):
    """Feedback payload accepted by the /feedback endpoint."""

    score: int | None = None
    user_id: str | None = None
    session_id: str | None = None
    text: str | None = None
