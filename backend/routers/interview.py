"""
Interview Router
================
API endpoints for the AI technical interview system.

Endpoints:
    POST   /api/interview
    GET    /api/candidates
    GET    /api/candidates/{candidate_id}
    GET    /api/sessions/{session_id}
    DELETE /api/sessions/{session_id}
"""

import logging

from fastapi import APIRouter, HTTPException

from schemas.interview import (
    CandidateListResponse,
    CandidateSummary,
    InterviewRequest,
    InterviewResponse,
    SessionStatusResponse,
)

from services.ai_agent import run_interview_turn
from services.candidate_loader import (
    list_candidates,
    load_candidate,
)
from services.curriculum_loader import (
    load_candidate_curriculum,
    summarise_curriculum,
)
from services.interview_controller import (
    build_interview_plan,
)
from services.session_manager import (
    add_model_message,
    add_user_message,
    can_complete,
    delete_session,
    get_or_create_session,
    get_session,
    set_difficulty,
    set_interview_plan,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Interview"])


# ---------------------------------------------------------------------------
# POST /api/interview
# ---------------------------------------------------------------------------

@router.post(
    "/interview",
    response_model=InterviewResponse,
)
async def conduct_interview(
    payload: InterviewRequest,
) -> InterviewResponse:
    """
    Drive one turn of the technical interview.

    First request:
        - candidate_id required
        - session_id omitted
        - user_message omitted

    Subsequent requests:
        - candidate_id required
        - session_id required
        - user_message contains the candidate's latest answer

    The endpoint:
        1. Loads candidate profile.
        2. Loads completed curriculum.
        3. Creates/restores interview session.
        4. Builds an interview plan for new sessions.
        5. Stores the candidate's answer.
        6. Calls the AI interview agent.
        7. Stores the AI response.
        8. Returns interview state and feedback.
    """

    # ------------------------------------------------------------------
    # Step 1 — Load candidate
    # ------------------------------------------------------------------

    candidate = load_candidate(
        payload.candidate_id
    )

    # ------------------------------------------------------------------
    # Step 2 — Load candidate curriculum
    # ------------------------------------------------------------------

    days_completed: int = candidate.get(
        "days_completed",
        0,
    )

    curriculum_days = load_candidate_curriculum(
        days_completed
    )

    curriculum_summary = summarise_curriculum(
        curriculum_days
    )

    # ------------------------------------------------------------------
    # Step 3 — Create or restore session
    # ------------------------------------------------------------------

    session = get_or_create_session(
        payload.session_id,
        payload.candidate_id,
    )

    # ------------------------------------------------------------------
    # Step 4 — Build interview plan once per session
    # ------------------------------------------------------------------

    if session.interview_plan is None:

        plan = build_interview_plan(
            candidate=candidate,
            curriculum_days=curriculum_days,
            minimum_days=4,
        )

        set_interview_plan(
            session=session,
            target_days=plan.target_days,
            target_topics=plan.target_topics,
        )

        set_difficulty(
            session=session,
            difficulty=candidate.get("interview_difficulty", "intermediate"),
        )

        logger.info(
            "Created interview plan for session %s: "
            "days=%s topics=%s difficulty=%s",
            session.session_id,
            plan.target_days,
            plan.target_topics,
            session.current_difficulty,
        )

    # ------------------------------------------------------------------
    # Step 5 — If already complete, return cached result
    # ------------------------------------------------------------------

    if session.is_complete:

        return InterviewResponse(
            session_id=session.session_id,
            message=(
                "The interview has already been completed. "
                "Thank you!"
            ),
            is_complete=True,
            feedback=session.feedback,
            metadata={
                "question_count": session.question_count,
                "curriculum_days_covered": (
                    session.curriculum_days_covered
                ),
                "curriculum_day_count": len(
                    session.curriculum_days_covered
                ),
                "topics_covered": session.topics_covered,
                "current_curriculum_day": (
                    session.current_curriculum_day
                ),
                "current_topic": (
                    session.current_topic
                ),
                "current_difficulty": (
                    session.current_difficulty
                ),
                "interview_plan": session.interview_plan,
            },
        )

    # ------------------------------------------------------------------
    # Step 6 — Save candidate answer
    # ------------------------------------------------------------------

    if payload.user_message:
        add_user_message(
            session,
            payload.user_message,
        )

    # ------------------------------------------------------------------
    # Step 7 — Run AI interviewer
    # ------------------------------------------------------------------

    try:

        (
            ai_message,
            is_complete,
            feedback,
        ) = await run_interview_turn(
            session=session,
            candidate=candidate,
            curriculum_summary=curriculum_summary,
            user_message=payload.user_message,
        )

    except RuntimeError as exc:

        logger.error(
            "AI agent error for session %s: %s",
            session.session_id,
            exc,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "The AI service is temporarily unavailable. "
                f"{exc}"
            ),
        ) from exc

    except Exception as exc:

        logger.exception(
            "Unexpected error in AI agent for session %s",
            session.session_id,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "An unexpected error occurred. "
                "Please try again."
            ),
        ) from exc

    # ------------------------------------------------------------------
    # Step 8 — Save AI response
    # ------------------------------------------------------------------

    add_model_message(
        session=session,
        message=ai_message,
        is_question=not is_complete,
    )

    # ------------------------------------------------------------------
    # Step 9 — Store completion state
    # ------------------------------------------------------------------

    if is_complete:

        session.is_complete = True
        session.feedback = feedback

    # ------------------------------------------------------------------
    # Step 10 — Build metadata
    # ------------------------------------------------------------------

    metadata = {
        "question_count": session.question_count,
        "candidate_name": candidate.get("name"),
        "curriculum_days_covered": (
            session.curriculum_days_covered
        ),
        "curriculum_day_count": len(
            session.curriculum_days_covered
        ),
        "topics_covered": (
            session.topics_covered
        ),
        "current_curriculum_day": (
            session.current_curriculum_day
        ),
        "current_topic": (
            session.current_topic
        ),
        "current_difficulty": (
            session.current_difficulty
        ),
        "interview_plan": (
            session.interview_plan
        ),
        "can_complete": can_complete(session),
    }

    # ------------------------------------------------------------------
    # Step 11 — Return response
    # ------------------------------------------------------------------

    return InterviewResponse(
        session_id=session.session_id,
        message=ai_message,
        is_complete=is_complete,
        feedback=feedback if is_complete else None,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# GET /api/candidates
# ---------------------------------------------------------------------------

@router.get(
    "/candidates",
    response_model=CandidateListResponse,
)
async def get_candidates() -> CandidateListResponse:
    """
    Return all available candidate summaries.
    """

    candidates = list_candidates()

    return CandidateListResponse(
        candidates=[
            CandidateSummary(**candidate)
            for candidate in candidates
        ],
        total=len(candidates),
    )


# ---------------------------------------------------------------------------
# GET /api/candidates/{candidate_id}
# ---------------------------------------------------------------------------

@router.get(
    "/candidates/{candidate_id}"
)
async def get_candidate(
    candidate_id: str,
) -> dict:
    """
    Return a single candidate's complete profile.
    """

    return load_candidate(
        candidate_id
    )


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}
# ---------------------------------------------------------------------------

@router.get(
    "/sessions/{session_id}",
    response_model=SessionStatusResponse,
)
async def get_session_status(
    session_id: str,
) -> SessionStatusResponse:
    """
    Return detailed status of an interview session.
    """

    session = get_session(
        session_id
    )

    if not session:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Session '{session_id}' not found. "
                "It may have expired."
            ),
        )

    return SessionStatusResponse(
        session_id=session.session_id,
        candidate_id=session.candidate_id,
        question_count=session.question_count,
        is_complete=session.is_complete,
        message_count=len(
            session.conversation_history
        ),
        curriculum_days_covered=(
            session.curriculum_days_covered
        ),
        curriculum_day_count=len(
            session.curriculum_days_covered
        ),
        topics_covered=(
            session.topics_covered
        ),
        current_curriculum_day=(
            session.current_curriculum_day
        ),
        current_topic=(
            session.current_topic
        ),
        interview_plan=(
            session.interview_plan
        ),
        feedback=session.feedback,
    )


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{session_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/sessions/{session_id}"
)
async def reset_session(
    session_id: str,
) -> dict:
    """
    Delete an interview session so a new interview can be started.
    """

    session = get_session(
        session_id
    )

    if not session:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Session '{session_id}' not found."
            ),
        )

    delete_session(
        session_id
    )

    return {
        "message": (
            f"Session '{session_id}' has been deleted."
        ),
        "session_id": session_id,
    }