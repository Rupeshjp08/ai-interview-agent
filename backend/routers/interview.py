"""
Interview router — /api/interview, /api/candidates, /api/sessions/{id}
======================================================================
Drives a full multi-turn AI technical interview using Google Gemini.

Endpoints:
  POST /api/interview          — drive one interview turn
  GET  /api/candidates         — list available candidate profiles
  GET  /api/candidates/{id}    — get a single candidate profile
  GET  /api/sessions/{id}      — retrieve session metadata
  DELETE /api/sessions/{id}    — reset / delete a session

Flow per POST /api/interview request:
  1. Load candidate profile (raises 404 if unknown).
  2. Load curriculum for this candidate.
  3. Init or restore the in-memory interview session.
  4. Persist the user's message into session history.
  5. Run the AI agent to generate the next question / response.
  6. Persist the AI's reply into session history.
  7. Return the response (with feedback if the interview is complete).
"""

import logging

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException

from schemas.interview import (
    CandidateListResponse,
    CandidateSummary,
    InterviewRequest,
    InterviewResponse,
    SessionStatusResponse,
)
from services.ai_agent import run_interview_turn
from services.candidate_loader import list_candidates, load_candidate
from services.curriculum_loader import load_candidate_curriculum, summarise_curriculum
from services.session_manager import (
    add_model_message,
    add_user_message,
    delete_session,
    get_or_create_session,
    get_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Interview"])


# ---------------------------------------------------------------------------
# POST /api/interview
# ---------------------------------------------------------------------------


@router.post("/interview", response_model=InterviewResponse)
async def conduct_interview(payload: InterviewRequest) -> InterviewResponse:
    """
    Drive a single turn of the AI technical interview.

    **Behaviour:**
    - On the first call (no session_id, no user_message): starts the interview,
      returns a welcome message and the first question.
    - On subsequent calls: accepts the candidate's answer, generates the next
      adaptive question.
    - After ≥ 8 questions, the agent may conclude the interview and return
      structured feedback.

    **Request fields:**
    - `candidate_id` (required): identifies which candidate profile to load.
    - `session_id` (optional): omit on first turn; include on all subsequent turns.
    - `user_message` (optional): omit on first turn; include the candidate's answer.
    """

    # ------------------------------------------------------------------
    # Step 1 — Load candidate profile
    # ------------------------------------------------------------------
    candidate = load_candidate(payload.candidate_id)

    # ------------------------------------------------------------------
    # Step 2 — Load curriculum for this candidate
    # ------------------------------------------------------------------
    days_completed: int = candidate.get("days_completed", 0)
    curriculum_days = load_candidate_curriculum(days_completed)
    curriculum_summary = summarise_curriculum(curriculum_days)

    # ------------------------------------------------------------------
    # Step 3 — Init or restore session
    # ------------------------------------------------------------------
    session = get_or_create_session(payload.session_id, payload.candidate_id)

    # If the session is already complete, return cached feedback
    if session.is_complete:
        return InterviewResponse(
            session_id=session.session_id,
            message="The interview has already been completed. Thank you!",
            is_complete=True,
            feedback=session.feedback,
            metadata={"question_count": session.question_count},
        )

    # ------------------------------------------------------------------
    # Step 4 — Persist user message (if provided)
    # ------------------------------------------------------------------
    if payload.user_message:
        add_user_message(session, payload.user_message)

    # ------------------------------------------------------------------
    # Step 5 — Run AI agent
    # ------------------------------------------------------------------
    try:
        ai_message, is_complete, feedback = await run_interview_turn(
            session=session,
            candidate=candidate,
            curriculum_summary=curriculum_summary,
            user_message=payload.user_message,
        )
    except RuntimeError as exc:
        # AI / quota error — surface a clean 503 to the client
        logger.error("AI agent error for session %s: %s", session.session_id, exc)
        raise HTTPException(
            status_code=503,
            detail=(
                f"The AI service is temporarily unavailable: {exc}. "
                "Please try again in a few moments."
            ),
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error in AI agent for session %s", session.session_id
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again.",
        ) from exc

    # ------------------------------------------------------------------
    # Step 6 — Persist AI response + update session state
    # ------------------------------------------------------------------
    add_model_message(session, ai_message)

    if is_complete:
        session.is_complete = True
        session.feedback = feedback

    # ------------------------------------------------------------------
    # Step 7 — Return response
    # ------------------------------------------------------------------
    return InterviewResponse(
        session_id=session.session_id,
        message=ai_message,
        is_complete=is_complete,
        feedback=feedback if is_complete else None,
        metadata={
            "question_count": session.question_count,
            "days_covered": days_completed,
            "candidate_name": candidate.get("name"),
            "can_complete": session.question_count >= 8,
        },
    )


# ---------------------------------------------------------------------------
# GET /api/candidates
# ---------------------------------------------------------------------------


@router.get("/candidates", response_model=CandidateListResponse)
async def get_candidates() -> CandidateListResponse:
    """
    List all available candidate profiles.

    Returns a list of candidates with their basic info (id, name, cohort, etc.)
    so the frontend can populate a selection list.
    """
    candidates = list_candidates()
    return CandidateListResponse(
        candidates=[CandidateSummary(**c) for c in candidates],
        total=len(candidates)
    )


# ---------------------------------------------------------------------------
# GET /api/candidates/{candidate_id}
# ---------------------------------------------------------------------------


@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: str) -> dict:
    """
    Retrieve a single candidate's full profile.

    Raises 404 if the candidate does not exist.
    """
    return load_candidate(candidate_id)


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str) -> SessionStatusResponse:
    """
    Retrieve the current status of an interview session.

    Raises 404 if the session does not exist.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found. It may have expired.",
        )
    return SessionStatusResponse(
        session_id=session.session_id,
        candidate_id=session.candidate_id,
        question_count=session.question_count,
        is_complete=session.is_complete,
        feedback=session.feedback,
        message_count=len(session.conversation_history),
    )


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{session_id}
# ---------------------------------------------------------------------------


@router.delete("/sessions/{session_id}")
async def reset_session(session_id: str) -> dict:
    """
    Delete an interview session, allowing the candidate to start fresh.

    Raises 404 if the session does not exist.
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )
    delete_session(session_id)
    return {
        "message": f"Session '{session_id}' has been deleted.",
        "session_id": session_id,
    }
