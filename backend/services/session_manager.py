"""
Session Manager Service
=======================
In-memory session store for multi-turn interview conversations.

Each session tracks:
- conversation history
- question count
- curriculum coverage
- interview plan
- topics covered
- current question context
- completion state
- final feedback

NOTE:
This is a development-grade in-memory store.
For production, replace it with Redis or a database-backed store.
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
    conversation_history: list[dict[str, Any]] = field(
        default_factory=list
    )

    # Number of actual interview questions asked
    question_count: int = 0

    # Distinct curriculum days covered during this interview
    curriculum_days_covered: list[int] = field(
        default_factory=list
    )

    # Planned curriculum coverage for this interview
    #
    # Example:
    # {
    #     "target_days": [18, 22, 25, 28],
    #     "target_topics": [
    #         "RAG",
    #         "Vector Databases",
    #         "Prompt Engineering",
    #         "LangGraph"
    #     ]
    # }
    interview_plan: dict[str, Any] | None = None

    # Distinct topics covered during the interview
    topics_covered: list[str] = field(
        default_factory=list
    )

    # Actual questions already asked
    asked_questions: list[str] = field(
        default_factory=list
    )

    # Curriculum day associated with the current question
    current_curriculum_day: int | None = None

    # Topic associated with the current question
    current_topic: str | None = None

    # Interview completion state
    is_complete: bool = False

    # Final structured feedback
    feedback: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Global in-memory store
# ---------------------------------------------------------------------------

_sessions: dict[str, InterviewSession] = {}


# ---------------------------------------------------------------------------
# Interview configuration
# ---------------------------------------------------------------------------

# Minimum number of actual technical questions.
MIN_QUESTIONS = 8

# Minimum number of distinct curriculum days/topics
# the upgraded interviewer should cover before completing.
MIN_CURRICULUM_DAYS = 4


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def create_session(candidate_id: str) -> InterviewSession:
    """
    Create a new interview session.

    Args:
        candidate_id: Candidate's unique identifier.

    Returns:
        Newly created InterviewSession.
    """

    session_id = f"sess_{uuid.uuid4().hex[:12]}"

    session = InterviewSession(
        session_id=session_id,
        candidate_id=candidate_id,
    )

    _sessions[session_id] = session

    return session


def get_session(
    session_id: str,
) -> InterviewSession | None:
    """
    Retrieve an existing session by ID.

    Returns:
        InterviewSession if found, otherwise None.
    """

    return _sessions.get(session_id)


def get_or_create_session(
    session_id: str | None,
    candidate_id: str,
) -> InterviewSession:
    """
    Return an existing session when the ID is valid;
    otherwise create a new session.
    """

    if session_id:
        session = get_session(session_id)

        if session:
            return session

    return create_session(candidate_id)


def delete_session(
    session_id: str,
) -> bool:
    """
    Delete a session.

    Returns:
        True if deleted, False if it didn't exist.
    """

    if session_id in _sessions:
        del _sessions[session_id]
        return True

    return False


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

def add_user_message(
    session: InterviewSession,
    message: str,
) -> None:
    """Append a candidate message to conversation history."""

    session.conversation_history.append(
        {
            "role": "user",
            "parts": [
                {
                    "text": message,
                }
            ],
        }
    )


def add_model_message(
    session: InterviewSession,
    message: str,
    is_question: bool = True,
) -> None:
    """
    Append an interviewer message to conversation history.

    Args:
        session: Current interview session.
        message: AI-generated message.
        is_question: Whether this message represents an actual
                     interview question.

    Only actual questions increment question_count.
    """

    session.conversation_history.append(
        {
            "role": "model",
            "parts": [
                {
                    "text": message,
                }
            ],
        }
    )

    if is_question:
        session.question_count += 1

        if message.strip():
            session.asked_questions.append(
                message.strip()
            )


# ---------------------------------------------------------------------------
# Interview completion
# ---------------------------------------------------------------------------

def can_complete(
    session: InterviewSession,
) -> bool:
    """
    Return True if the interview has reached the minimum
    number of questions AND minimum curriculum coverage.

    This enforces the upgraded project requirement:

        questions >= 8
        AND
        distinct curriculum days >= 4
    """

    return (
        session.question_count >= MIN_QUESTIONS
        and has_minimum_curriculum_coverage(
            session,
            MIN_CURRICULUM_DAYS,
        )
    )


def has_minimum_questions(
    session: InterviewSession,
) -> bool:
    """Return True when the minimum number of questions is reached."""

    return session.question_count >= MIN_QUESTIONS


# ---------------------------------------------------------------------------
# Curriculum tracking
# ---------------------------------------------------------------------------

def add_curriculum_day(
    session: InterviewSession,
    day: int,
) -> None:
    """
    Record a curriculum day covered by an interview question.

    Duplicate days are ignored.
    """

    if day not in session.curriculum_days_covered:
        session.curriculum_days_covered.append(day)


def add_topic(
    session: InterviewSession,
    topic: str,
) -> None:
    """
    Record a topic covered by an interview question.

    Duplicate topics are ignored.
    """

    topic = topic.strip()

    if not topic:
        return

    if topic not in session.topics_covered:
        session.topics_covered.append(topic)


def set_current_topic(
    session: InterviewSession,
    day: int,
    topic: str,
) -> None:
    """
    Set the curriculum day and topic associated
    with the current interview question.
    """

    session.current_curriculum_day = day
    session.current_topic = topic.strip()


def record_covered_topic(
    session: InterviewSession,
) -> None:
    """
    Record the current question's curriculum day and topic
    as covered.
    """

    if session.current_curriculum_day is not None:
        add_curriculum_day(
            session,
            session.current_curriculum_day,
        )

    if session.current_topic:
        add_topic(
            session,
            session.current_topic,
        )


def clear_current_topic(
    session: InterviewSession,
) -> None:
    """Clear the current question's curriculum metadata."""

    session.current_curriculum_day = None
    session.current_topic = None


def has_minimum_curriculum_coverage(
    session: InterviewSession,
    minimum_days: int = MIN_CURRICULUM_DAYS,
) -> bool:
    """
    Return True when enough distinct curriculum days
    have been covered.
    """

    plan_days = (session.interview_plan or {}).get("target_days", [])
    required_days = min(minimum_days, len(plan_days)) if plan_days else minimum_days

    return len(
        set(session.curriculum_days_covered)
    ) >= required_days


# ---------------------------------------------------------------------------
# Interview plan helpers
# ---------------------------------------------------------------------------

def set_interview_plan(
    session: InterviewSession,
    target_days: list[int],
    target_topics: list[str],
) -> None:
    """
    Store the interview plan in the session.
    """

    session.interview_plan = {
        "target_days": list(target_days),
        "target_topics": list(target_topics),
    }


def get_interview_plan(
    session: InterviewSession,
) -> dict[str, Any]:
    """
    Return the stored interview plan.

    Returns an empty plan when one hasn't been created yet.
    """

    return session.interview_plan or {
        "target_days": [],
        "target_topics": [],
    }


# ---------------------------------------------------------------------------
# Debug / admin helpers
# ---------------------------------------------------------------------------

def list_active_sessions() -> list[dict[str, Any]]:
    """
    Return a summary of all active sessions.
    """

    return [
        {
            "session_id": session.session_id,
            "candidate_id": session.candidate_id,
            "question_count": session.question_count,
            "curriculum_days_covered": list(
                session.curriculum_days_covered
            ),
            "topics_covered": list(
                session.topics_covered
            ),
            "current_curriculum_day": (
                session.current_curriculum_day
            ),
            "current_topic": session.current_topic,
            "is_complete": session.is_complete,
            "message_count": len(
                session.conversation_history
            ),
        }
        for session in _sessions.values()
    ]