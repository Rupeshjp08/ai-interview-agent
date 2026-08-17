"""
AI interview agent using Google Gemini.

Responsibilities:
- Build a personalised interview prompt.
- Conduct a multi-turn technical interview.
- Ask exactly one question at a time.
- Adapt questions based on candidate answers.
- Complete the interview after the minimum number of questions.
- Generate structured feedback.
- Handle Gemini rate limits and temporary service errors.
"""

import json
import logging
import os
import re
import time
from typing import Any

import google.generativeai as genai
from google.api_core.exceptions import (
    GoogleAPIError,
    ResourceExhausted,
    ServiceUnavailable,
)

from services.session_manager import InterviewSession, can_complete

MOCK_MODE = True

MOCK_QUESTIONS = [
    "Welcome to the interview! Let's start with a foundational question: How do you determine the optimal chunk size when building a RAG pipeline?",
    "That makes sense. Now, what are the trade-offs between dense and sparse retrieval in vector databases?",
    "Can you explain how embeddings capture semantic meaning behind the text?",
    "What techniques do you use to improve retrieval accuracy in a RAG system?",
    "Moving on to orchestration, how does LangGraph help in managing state across AI agents?",
    "What are the key differences between a traditional conversational agent and a LangGraph-based agent?",
    "How do you approach prompt engineering to minimize hallucinations in complex tasks?",
    "Could you describe a challenging bug you faced while working with AI agents and how you resolved it?",
    "What is your approach to evaluating the performance of an LLM-based application?"
]

logger = logging.getLogger(__name__)


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

# Use models that your API key showed as available.
_MODEL_FALLBACK_ORDER = [
    "gemini-3-flash-preview",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

_genai_configured = False


def _ensure_genai_configured() -> None:
    """Configure Gemini using GOOGLE_API_KEY."""

    global _genai_configured

    if _genai_configured:
        return

    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY environment variable is not set. "
            "Add it to backend/.env."
        )

    genai.configure(api_key=api_key)

    _genai_configured = True


def _get_gemini_model(model_name: str) -> genai.GenerativeModel:
    """Create a Gemini model instance."""

    _ensure_genai_configured()

    return genai.GenerativeModel(
        model_name=model_name,
        generation_config=genai.GenerationConfig(
            temperature=0.7,
            max_output_tokens=2048,
        ),
    )


# ============================================================
# SYSTEM PROMPT
# ============================================================

_SYSTEM_PROMPT_TEMPLATE = """
You are an expert AI Engineering interviewer conducting a rigorous but friendly technical interview.

## Candidate Profile

Name: {name}
Cohort: {cohort}
Days Completed: {days_completed} / 31
Strengths: {strengths}
Weak Areas: {weak_areas}
Projects Built: {projects}
Learning Notes: {learning_notes}

## Curriculum Covered

The candidate has studied the following topics:

{curriculum_summary}

## Interview Guidelines

1. Ask EXACTLY ONE focused technical question per turn.
2. NEVER ask multiple questions in one response.
3. NEVER use numbered questions.
4. NEVER use bullet-point questions.
5. NEVER ask questions such as "What is X and how does Y work?"
6. If multiple areas are available, choose only ONE area for this turn.
7. Start with a warm and professional welcome.
8. Tailor questions to the candidate's projects, strengths and weak areas.
9. Follow up naturally based on the candidate's previous answer.
10. Ask for implementation details, reasoning, examples, trade-offs or debugging experience when appropriate.
11. Start at medium difficulty.
12. Increase difficulty when the candidate gives strong answers.
13. Simplify the question if the candidate struggles.
14. Keep the conversation natural.
15. Do not repeat questions that have already been asked.
16. After {min_questions} or more questions, conclude the interview when the conversation feels complete.

## IMPORTANT QUESTION RULE

Every interviewer response must contain ONLY ONE technical question.

For example, this is GOOD:

"How did you choose the chunk size for your RAG pipeline?"

This is BAD:

"How did you choose the chunk size, and what was your overlap?"

This is also BAD:

"How did you choose the chunk size?
What embedding model did you use?"

Ask one thing at a time.

## COMPLETION

When the interview is complete after at least {min_questions} questions, return ONLY valid JSON in this exact structure:

{{
  "interview_complete": true,
  "next_question": "Thank you for participating in the interview.",
  "feedback": {{
    "overall_score": 8,
    "summary": "The candidate demonstrated strong technical understanding and practical implementation skills.",
    "strengths_demonstrated": [
      "Technical understanding",
      "Problem solving"
    ],
    "areas_for_improvement": [
      "System design depth",
      "Communication clarity"
    ],
    "topic_scores": {{
      "Technical Knowledge": 8,
      "Project Understanding": 8,
      "Problem Solving": 7
    }},
    "recommendation": "Hire"
  }}
}}

Before reaching {min_questions} questions, NEVER return the completion JSON.

Instead, ask the next single technical question normally.
""".strip()


def _build_system_prompt(
    candidate: dict[str, Any],
    curriculum_summary: str,
    min_questions: int = 8,
) -> str:
    """Build personalised system prompt."""

    projects = "; ".join(
        f"{project.get('name', 'Unnamed Project')} "
        f"({project.get('description', 'No description')})"
        for project in candidate.get("projects", [])
    )

    if not projects:
        projects = "None listed"

    return _SYSTEM_PROMPT_TEMPLATE.format(
        name=candidate.get("name", "Candidate"),
        cohort=candidate.get(
            "cohort",
            "AI Engineering Cohort",
        ),
        days_completed=candidate.get(
            "days_completed",
            0,
        ),
        strengths=", ".join(
            candidate.get("strengths", [])
        )
        or "Not specified",
        weak_areas=", ".join(
            candidate.get("weak_areas", [])
        )
        or "Not specified",
        projects=projects,
        learning_notes=candidate.get(
            "learning_notes",
            "No notes available.",
        ),
        curriculum_summary=(
            curriculum_summary
            or "No curriculum data available."
        ),
        min_questions=min_questions,
    )


# ============================================================
# RESPONSE PARSER
# ============================================================

def _parse_response(
    raw_text: str,
) -> tuple[str, bool, dict[str, Any] | None]:
    """
    Parse Gemini response.

    Returns:
        message, is_complete, feedback
    """

    text = raw_text.strip()

    def _extract_completion(payload: Any) -> tuple[str, bool, dict[str, Any] | None] | None:
        if isinstance(payload, dict):
            is_complete = payload.get("interview_complete")
            if is_complete is True or str(is_complete).lower() == "true":
                return (
                    str(payload.get("next_question", "Thank you for participating in the interview.")),
                    True,
                    payload.get("feedback"),
                )
        return None

    # --------------------------------------------------------
    # 1. Try JSON inside ```json ... ```
    # --------------------------------------------------------

    code_block_match = re.search(
        r"```json\s*(.*?)\s*```",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    if code_block_match:
        json_text = code_block_match.group(1).strip()
        try:
            payload = json.loads(json_text)
            result = _extract_completion(payload)
            if result:
                return result
        except json.JSONDecodeError:
            logger.warning("Gemini returned invalid completion JSON inside code block.")

    # --------------------------------------------------------
    # 2 & 3. Try raw JSON or JSON preceded/followed by other text
    # --------------------------------------------------------
    
    idx = text.find('"interview_complete"')
    if idx != -1:
        start_idx = text.rfind('{', 0, idx)
        if start_idx != -1:
            # Try all '}' from the end backwards until json.loads succeeds
            for end_idx in range(len(text) - 1, start_idx, -1):
                if text[end_idx] == '}':
                    try:
                        json_text = text[start_idx:end_idx + 1]
                        payload = json.loads(json_text)
                        result = _extract_completion(payload)
                        if result:
                            return result
                    except json.JSONDecodeError:
                        continue

    # --------------------------------------------------------
    # Normal interviewer response
    # --------------------------------------------------------

    clean_text = re.sub(
        r"```json.*?```",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()

    return clean_text, False, None


# ============================================================
# GEMINI REQUEST WITH RETRIES
# ============================================================

def _call_with_retry(
    model_name: str,
    history: list[dict[str, Any]],
    message: str,
    max_retries: int = 3,
) -> str:
    """
    Send request to Gemini.

    Handles:
    - Rate limits
    - Temporary service errors
    - Model fallback
    """

    models_to_try = [
        model_name,
        *[
            model
            for model in _MODEL_FALLBACK_ORDER
            if model != model_name
        ],
    ]

    last_error: Exception | None = None

    for attempt_model in models_to_try:

        for attempt in range(max_retries):

            try:
                logger.info(
                    "Calling Gemini model: %s",
                    attempt_model,
                )

                model = _get_gemini_model(
                    attempt_model
                )

                chat = model.start_chat(
                    history=history
                )  # type: ignore  # type: ignore

                response = chat.send_message(
                    message
                )

                return response.text

            # ------------------------------------------------
            # Rate limit / quota
            # ------------------------------------------------

            except ResourceExhausted as error:

                last_error = error

                wait_time = 2 ** attempt * 3

                logger.warning(
                    "Rate limit for %s. Retry %d/%d. "
                    "Waiting %d seconds.",
                    attempt_model,
                    attempt + 1,
                    max_retries,
                    wait_time,
                )

                if attempt < max_retries - 1:
                    time.sleep(wait_time)

            # ------------------------------------------------
            # Temporary service unavailable
            # ------------------------------------------------

            except ServiceUnavailable as error:

                last_error = error

                wait_time = 2 ** attempt * 2

                logger.warning(
                    "Gemini temporarily unavailable. "
                    "Retry %d/%d.",
                    attempt + 1,
                    max_retries,
                )

                if attempt < max_retries - 1:
                    time.sleep(wait_time)

            # ------------------------------------------------
            # Other Google API errors
            # ------------------------------------------------

            except GoogleAPIError as error:

                last_error = error

                error_text = str(error)

                lower_error = error_text.lower()

                # Model unavailable -> try next model
                if (
                    "not found" in lower_error
                    or "not available" in lower_error
                    or "404" in lower_error
                ):
                    logger.warning(
                        "Model %s unavailable. "
                        "Trying next model.",
                        attempt_model,
                    )

                    break

                logger.error(
                    "Gemini API error: %s",
                    error_text,
                )

                raise RuntimeError(
                    f"Gemini API error: {error_text[:300]}"
                ) from error

            except Exception as error:

                logger.exception(
                    "Unexpected Gemini error."
                )

                raise RuntimeError(
                    f"Unexpected Gemini error: {error}"
                ) from error

    raise RuntimeError(
        "All Gemini models failed. "
        f"Last error: {last_error}"
    )


# ============================================================
# MAIN INTERVIEW FUNCTION
# ============================================================

async def run_interview_turn(
    session: InterviewSession,
    candidate: dict[str, Any],
    curriculum_summary: str,
    user_message: str | None,
) -> tuple[str, bool, dict[str, Any] | None]:
    """
    Run one interview turn.

    Returns:

        (
            interviewer_message,
            is_complete,
            feedback
        )
    """

    if MOCK_MODE:
        if can_complete(session) and user_message:
            return (
                "Thank you for participating in the interview. We will be in touch soon.",
                True,
                {
                    "overall_score": 8,
                    "summary": "The candidate provided strong answers across RAG, vector DBs, and prompt engineering.",
                    "strengths_demonstrated": ["RAG Architecture", "Prompt Engineering"],
                    "areas_for_improvement": ["Advanced LangGraph Concepts"],
                    "topic_scores": {
                        "RAG": 9,
                        "Vector Databases": 8,
                        "LangGraph": 6,
                    },
                    "recommendation": "Strong Hire"
                }
            )
        
        # Pick a question based on how many questions have been asked
        # session.question_count tracks questions asked so far.
        question_idx = session.question_count
        if question_idx >= len(MOCK_QUESTIONS):
            question_idx = len(MOCK_QUESTIONS) - 1
            
        return MOCK_QUESTIONS[question_idx], False, None

    system_prompt = _build_system_prompt(
        candidate,
        curriculum_summary,
    )

    preferred_model = _MODEL_FALLBACK_ORDER[0]

    # ========================================================
    # FIRST TURN
    # ========================================================

    if (
        not user_message
        and not session.conversation_history
    ):

        prompt = (
            f"{system_prompt}\n\n"
            "Begin the interview now. "
            "Give a warm welcome and then ask exactly ONE "
            "technical question."
        )

        raw_response = _call_with_retry(
            model_name=preferred_model,
            history=[],
            message=prompt,
        )

        return _parse_response(raw_response)

    # ========================================================
    # SUBSEQUENT TURNS
    # ========================================================

    history = list(
        session.conversation_history
    )

    # --------------------------------------------------------
    # Completion hint
    # --------------------------------------------------------

    completion_hint = ""

    if can_complete(session):
        completion_hint = """

IMPORTANT:
The minimum number of interview questions has been reached.

The interview MUST now be completed.

Do NOT ask another technical question.

Return ONLY the completion JSON specified in the system instructions.
"""

    # --------------------------------------------------------
    # Build prompt
    # --------------------------------------------------------

    if user_message:

        prompt = (
            f"{system_prompt}\n\n"
            f"Candidate's latest answer:\n"
            f"{user_message}\n\n"
            f"{completion_hint}"
        )

    else:

        prompt = (
            f"{system_prompt}\n\n"
            "Continue the interview by asking exactly ONE "
            "technical question."
        )

    # --------------------------------------------------------
    # Gemini request
    # --------------------------------------------------------

    raw_response = _call_with_retry(
        model_name=preferred_model,
        history=history,
        message=prompt,
    )

    return _parse_response(raw_response)