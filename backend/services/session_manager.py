"""
Session Manager Service
=======================
In-memory session store for multi-turn interview conversations.
Each session tracks conversation history, question count, and completion state.

NOTE: This is a development-grade in-memory store.
      For production, replace with Redis or a database-backed store.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InterviewSession:
    """Represents a single ongoing interview session."""

    session_id: str
    candidate_id: str

    # Gemini-compatible conversation history
    conversation_history: list[dict[str, Any]] = field(default_factory=list)

    # Number of interview questions asked (model turns)
    question_count: int = 0

    # Curriculum days actually covered during this interview
    curriculum_days_covered: list[int] = field(default_factory=list)

    # Interview completion state
    is_complete: bool = False

    # Final structured feedback
    feedback: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Global in-memory store
# ---------------------------------------------------------------------------
_sessions: dict[str, InterviewSession] = {}

# Minimum questions before interview can be marked complete
MIN_QUESTIONS = 8


def create_session(candidate_id: str) -> InterviewSession:
    """
    Create a new interview session for the given candidate.

    Args:
        candidate_id: The candidate's unique identifier.

    Returns:
        A newly created InterviewSession.
    """
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    session = InterviewSession(session_id=session_id, candidate_id=candidate_id)
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> InterviewSession | None:
    """
    Retrieve an existing session by ID.

    Args:
        session_id: The session identifier.

    Returns:
        The InterviewSession if found, else None.
    """
    return _sessions.get(session_id)


def get_or_create_session(
    session_id: str | None, candidate_id: str
) -> InterviewSession:
    """
    Return an existing session if session_id is valid, otherwise create one.

    Args:
        session_id: Optional existing session identifier.
        candidate_id: The candidate's unique identifier.

    Returns:
        An InterviewSession (existing or newly created).
    """
    if session_id:
        session = get_session(session_id)
        if session:
            return session
    return create_session(candidate_id)


def delete_session(session_id: str) -> bool:
    """
    Remove a session from the in-memory store.

    Args:
        session_id: The session identifier.

    Returns:
        True if the session was found and deleted, False otherwise.
    """
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False


def add_user_message(session: InterviewSession, message: str) -> None:
    """Append a user message to the session's conversation history."""
    session.conversation_history.append({"role": "user", "parts": [{"text": message}]})


def add_model_message(session: InterviewSession, message: str) -> None:
    """Append a model (assistant) message to the session's conversation history."""
    session.conversation_history.append({"role": "model", "parts": [{"text": message}]})
    session.question_count += 1


def can_complete(session: InterviewSession) -> bool:
    """Return True if the session has reached the minimum question threshold."""
    return session.question_count >= MIN_QUESTIONS


def add_curriculum_day(session: InterviewSession, day: int) -> None:
    """
    Record a curriculum day covered by an interview question.

    Duplicate days are ignored so the list only contains
    distinct curriculum days.
    """
    if day not in session.curriculum_days_covered:
        session.curriculum_days_covered.append(day)


def has_minimum_curriculum_coverage(
    session: InterviewSession, minimum_days: int = 4
) -> bool:
    """
    Return True when the interview has covered the required
    number of distinct curriculum days.
    """
    return len(session.curriculum_days_covered) >= minimum_days


def list_active_sessions() -> list[dict[str, Any]]:
    """
    Return a summary of all active sessions (for admin/debug purposes).
    """
    return [
        {
            "session_id": s.session_id,
            "candidate_id": s.candidate_id,
            "question_count": s.question_count,
            "is_complete": s.is_complete,
            "message_count": len(s.conversation_history),
        }
        for s in _sessions.values()
    ]
