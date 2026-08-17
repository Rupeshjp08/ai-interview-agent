"""
Pydantic schemas for the /api/interview endpoints.

These models define the contract between the frontend and the backend.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Interview Request / Response
# ---------------------------------------------------------------------------


class InterviewRequest(BaseModel):
    """Payload sent by the client to drive the interview conversation."""

    session_id: str | None = Field(
        default=None,
        description=(
            "Unique session identifier. "
            "Omit on the first turn; the server will generate and return one."
        ),
    )
    candidate_id: str = Field(
        ...,
        description="Identifier for the candidate whose profile will be loaded.",
    )
    user_message: str | None = Field(
        default=None,
        description=(
            "The candidate's latest response or message. "
            "Omit on the first turn to start a new interview."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "candidate_id": "candidate_001",
                    "user_message": None,
                }
            ]
        }
    }


class InterviewResponse(BaseModel):
    """Payload returned by the server after each interview turn."""

    session_id: str = Field(
        ...,
        description="Session identifier — persist this across turns.",
    )
    message: str = Field(
        ...,
        description="The interviewer's next question or closing statement.",
    )
    is_complete: bool = Field(
        default=False,
        description="True once the interview has finished and feedback is ready.",
    )
    feedback: dict[str, Any] | None = Field(
        default=None,
        description="Structured final feedback. Populated only when is_complete=True.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional debug / diagnostic information (e.g. question count).",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "sess_abc123",
                    "message": "Hello! Let's begin your technical interview.",
                    "is_complete": False,
                    "feedback": None,
                    "metadata": {"question_count": 1},
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Candidate schemas
# ---------------------------------------------------------------------------


class CandidateSummary(BaseModel):
    """Brief summary of a candidate for listing purposes."""

    candidate_id: str
    name: str
    cohort: str
    days_completed: int
    interview_difficulty: str | None = None
    strengths: list[str] = Field(default_factory=list)
    weak_areas: list[str] = Field(default_factory=list)


class CandidateListResponse(BaseModel):
    """Response containing all available candidate profiles."""

    candidates: list[CandidateSummary]
    total: int


# ---------------------------------------------------------------------------
# Session schemas
# ---------------------------------------------------------------------------


class SessionStatusResponse(BaseModel):
    """Current status of an interview session."""

    session_id: str
    candidate_id: str
    question_count: int
    is_complete: bool
    feedback: dict[str, Any] | None = None
    message_count: int = 0
