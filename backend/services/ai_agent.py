"""
AI Interview Agent
==================

Responsibilities:
- Build a personalized interview prompt.
- Conduct a multi-turn technical interview.
- Ask exactly one question at a time.
- Use the interview plan created by the Interview Controller.
- Track the current curriculum day/topic deterministically.
- Enforce 2 questions per planned topic across the 8 question slots.
- Adapt questions based on candidate answers when Gemini mode is enabled.
- Complete the interview after the required coverage is reached.
- Generate structured feedback.
- Handle Gemini rate limits and temporary service errors.

Development note:
    MOCK_MODE is currently enabled so the complete interview flow can be
    tested without repeatedly consuming Gemini API quota.

For the real AI-powered version:
    Set MOCK_MODE = False.
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

from services.interview_controller import (
    get_plan_from_session,
    get_target_for_question,
)
from services.session_manager import (
    InterviewSession,
    can_complete,
    record_covered_topic,
    set_current_topic,
)


logger = logging.getLogger(__name__)


# ============================================================
# DEVELOPMENT MODE
# ============================================================

# Keep this True while validating the interview-controller logic.
# Set to False to use Gemini for real adaptive questions.
MOCK_MODE = True


# ============================================================
# MOCK QUESTION BANK
# ============================================================
# Each topic maps to [Slot 0: Foundational / Design, Slot 1: Deeper / Trade-offs]

MOCK_TOPIC_QUESTIONS: dict[str, list[str]] = {
    "memory": [
        (
            "How would you design conversation memory for "
            "a multi-turn AI application?"
        ),
        (
            "What challenges can arise when maintaining "
            "conversation memory across multiple turns?"
        ),
    ],
    "ai_ml": [
        (
            "Can you explain the fundamental differences between "
            "traditional machine learning and modern large language models?"
        ),
        (
            "How do tokenization and context window limits impact "
            "the design of production LLM applications?"
        ),
    ],
    "embedding": [
        (
            "How do text embeddings capture semantic meaning, "
            "and how are vector representations generated?"
        ),
        (
            "How would you evaluate whether an embedding model "
            "is suitable for semantic retrieval and similarity search?"
        ),
    ],
    "langchain": [
        (
            "How does LangChain architecture structure an LLM application "
            "and orchestrate complex components?"
        ),
        (
            "What are the main engineering challenges and trade-offs "
            "when using LangChain abstractions in production?"
        ),
    ],
    "rag": [
        (
            "How would you design an end-to-end Retrieval-Augmented Generation "
            "(RAG) architecture for enterprise document search?"
        ),
        (
            "What strategies would you implement to optimize chunking, "
            "re-ranking, and retrieval precision in a RAG pipeline?"
        ),
    ],
    "vector": [
        (
            "How do vector databases index and perform similarity search "
            "over high-dimensional embeddings?"
        ),
        (
            "What factors and trade-offs would you consider when choosing "
            "an indexing strategy like HNSW versus IVF for a vector database?"
        ),
    ],
    "langgraph": [
        (
            "How does LangGraph help manage state and graph execution "
            "in multi-step AI workflows?"
        ),
        (
            "How would you handle cyclic loops, checkpoint persistence, "
            "and human-in-the-loop validation in a LangGraph agent?"
        ),
    ],
    "prompt": [
        (
            "How do few-shot examples and chain-of-thought reasoning "
            "improve LLM response quality?"
        ),
        (
            "What techniques would you use to protect prompt templates "
            "against prompt injection and jailbreak attacks?"
        ),
    ],
    "agent": [
        (
            "How does the ReAct pattern enable AI agents to alternate "
            "between reasoning and tool execution?"
        ),
        (
            "How do you prevent infinite loops and handle tool execution "
            "errors in multi-step agent workflows?"
        ),
    ],
    "deployment": [
        (
            "What key architectural considerations are critical when "
            "deploying LLM services to production?"
        ),
        (
            "How would you design latency caching, rate-limiting, "
            "and observability pipelines for production AI systems?"
        ),
    ],
    "evaluation": [
        (
            "How would you design an evaluation framework to measure "
            "the factual accuracy and groundedness of an LLM system?"
        ),
        (
            "What metrics and synthetic dataset generation methods would "
            "you use with frameworks like RAGAS in continuous integration?"
        ),
    ],
    "transformer": [
        (
            "How does the scaled dot-product self-attention mechanism "
            "operate within a Transformer architecture?"
        ),
        (
            "What are the computational bottlenecks of multi-head attention "
            "with long sequences, and how do modern optimizations address them?"
        ),
    ],
    "finetuning": [
        (
            "What are the key differences between full fine-tuning "
            "and Parameter-Efficient Fine-Tuning (PEFT) like LoRA?"
        ),
        (
            "How do quantization and rank selection in QLoRA affect "
            "memory footprint and downstream model accuracy?"
        ),
    ],
}


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

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


def _get_gemini_model(
    model_name: str,
) -> genai.GenerativeModel:
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
3. NEVER use numbered questions or bullet points.
4. NEVER ask compound questions such as "What is X and how does Y work?"
5. Stay strictly within the assigned current topic for this turn.
6. Tailor questions to the candidate's projects, strengths and weak areas.
7. Follow up naturally based on the candidate's previous answer.
8. Ask for implementation details, reasoning, examples, trade-offs or debugging experience when appropriate.
9. Keep the conversation natural and professional.
10. Do not repeat questions that have already been asked.
11. Respect the interview plan supplied below.

## IMPORTANT QUESTION RULE

Every interviewer response must contain ONLY ONE technical question.
Ask one thing at a time.

## COMPLETION

When the interview is complete after the required number of questions AND the required curriculum coverage has been reached, return ONLY valid JSON in this exact structure:

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

Before the required interview length and curriculum coverage are satisfied,
NEVER return the completion JSON.
""".strip()


def _build_system_prompt(
    candidate: dict[str, Any],
    curriculum_summary: str,
    min_questions: int = 8,
) -> str:
    """Build a personalized system prompt."""

    projects = "; ".join(
        f"{project.get('name', 'Unnamed Project')} "
        f"({project.get('description', 'No description')})"
        for project in candidate.get("projects", [])
    )

    if not projects:
        projects = "None listed"

    return _SYSTEM_PROMPT_TEMPLATE.format(
        name=candidate.get(
            "name",
            "Candidate",
        ),
        cohort=candidate.get(
            "cohort",
            "AI Engineering Cohort",
        ),
        days_completed=candidate.get(
            "days_completed",
            0,
        ),
        strengths=", ".join(
            candidate.get(
                "strengths",
                [],
            )
        )
        or "Not specified",
        weak_areas=", ".join(
            candidate.get(
                "weak_areas",
                [],
            )
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
# INTERVIEW PLAN CONTEXT
# ============================================================

def _build_interview_plan_context(
    session: InterviewSession,
) -> str:
    """
    Build prompt context from the current interview plan.
    """

    plan = session.interview_plan

    if not plan:
        return "No explicit interview plan is available."

    target_days = plan.get(
        "target_days",
        [],
    )

    target_topics = plan.get(
        "target_topics",
        [],
    )

    covered_days = session.curriculum_days_covered
    covered_topics = session.topics_covered

    lines = [
        "## Interview Plan",
        (
            "Target curriculum days: "
            f"{target_days or 'None'}"
        ),
        (
            "Target topics: "
            f"{target_topics or 'None'}"
        ),
        (
            "Curriculum days already covered: "
            f"{covered_days or 'None'}"
        ),
        (
            "Topics already covered: "
            f"{covered_topics or 'None'}"
        ),
        (
            "Current curriculum day: "
            f"{session.current_curriculum_day or 'None'}"
        ),
        (
            "Current topic: "
            f"{session.current_topic or 'None'}"
        ),
    ]

    return "\n".join(lines)


# ============================================================
# TOPIC NORMALIZATION & FALLBACKS
# ============================================================

def _normalize_topic(
    topic: str,
) -> str:
    """
    Normalize curriculum topic names so they can be mapped
    to the mock question bank.
    """

    topic_lower = topic.lower().strip()

    if (
        "conversation" in topic_lower
        or "memory" in topic_lower
        or "buffer" in topic_lower
    ):
        return "memory"

    if (
        "ai/ml" in topic_lower
        or "what is ai" in topic_lower
        or "llm fundamental" in topic_lower
        or "introduction to ai" in topic_lower
    ):
        return "ai_ml"

    if (
        "embedding" in topic_lower
        or "cosine" in topic_lower
    ):
        return "embedding"

    if (
        "langgraph" in topic_lower
        or "state machine" in topic_lower
    ):
        return "langgraph"

    if (
        "langchain" in topic_lower
        or "lcel" in topic_lower
        or "chain" in topic_lower
    ):
        return "langchain"

    if (
        "vector" in topic_lower
        or "pinecone" in topic_lower
        or "chroma" in topic_lower
        or "weaviate" in topic_lower
        or "qdrant" in topic_lower
    ):
        return "vector"

    if (
        "retrieval" in topic_lower
        or "rag" in topic_lower
        or "retrieval augmented" in topic_lower
    ):
        return "rag"

    if (
        "prompt" in topic_lower
        or "zero-shot" in topic_lower
        or "few-shot" in topic_lower
        or "chain-of-thought" in topic_lower
    ):
        return "prompt"

    if (
        "agent" in topic_lower
        or "react" in topic_lower
        or "tool" in topic_lower
    ):
        return "agent"

    if (
        "deployment" in topic_lower
        or "mlops" in topic_lower
        or "docker" in topic_lower
        or "system design" in topic_lower
    ):
        return "deployment"

    if (
        "eval" in topic_lower
        or "ragas" in topic_lower
    ):
        return "evaluation"

    if (
        "attention" in topic_lower
        or "transformer" in topic_lower
    ):
        return "transformer"

    if (
        "lora" in topic_lower
        or "qlora" in topic_lower
        or "peft" in topic_lower
        or "fine-tuning" in topic_lower
        or "sft" in topic_lower
    ):
        return "finetuning"

    return "general"


def _get_topic_fallback_question(
    session: InterviewSession,
    topic: str,
    slot_within_topic: int,
) -> str:
    """
    Generate a guaranteed topic-specific question.
    Never returns a generic unrelated question.
    """

    normalized = _normalize_topic(topic)

    if normalized in MOCK_TOPIC_QUESTIONS:
        questions = MOCK_TOPIC_QUESTIONS[normalized]
        return questions[slot_within_topic % len(questions)]

    if slot_within_topic == 0:
        return (
            f"How would you approach designing and implementing "
            f"solutions based on {topic} in an AI engineering system?"
        )
    else:
        return (
            f"What are the main engineering challenges, failure modes, "
            f"and performance trade-offs when implementing {topic} in production?"
        )


# ============================================================
# TOPIC ASSIGNMENT & MOCK GENERATOR
# ============================================================

def _assign_next_planned_topic(
    session: InterviewSession,
) -> tuple[int, str] | None:
    """
    Assign the planned topic based on the interview question slot.

    Deterministic 2-question slot mapping:
        slot 0 or 1 (Q1, Q2) -> target topic index 0
        slot 2 or 3 (Q3, Q4) -> target topic index 1
        slot 4 or 5 (Q5, Q6) -> target topic index 2
        slot 6 or 7 (Q7, Q8) -> target topic index 3

    Topic selection is strictly determined by session.question_count // 2,
    NOT by curriculum_days_covered.
    """

    plan = get_plan_from_session(session)

    target = get_target_for_question(
        plan,
        session.question_count,
    )

    if target:
        day, topic = target
        set_current_topic(
            session,
            day,
            topic,
        )
        return day, topic

    return None


def _get_mock_question(
    session: InterviewSession,
) -> str:
    """
    Generate a deterministic mock question based on
    the current planned topic and the question slot within the topic.

    Slot 0 (Q1, Q3, Q5, Q7): Foundational / design question.
    Slot 1 (Q2, Q4, Q6, Q8): Deeper engineering / trade-off question.
    """

    topic = (
        session.current_topic
        or "AI Engineering"
    )

    slot_within_topic = session.question_count % 2

    return _get_topic_fallback_question(
        session,
        topic,
        slot_within_topic,
    )


# ============================================================
# RESPONSE PARSER
# ============================================================

def _parse_response(
    raw_text: str,
) -> tuple[
    str,
    bool,
    dict[str, Any] | None,
]:
    """
    Parse Gemini response.

    Returns:
        message, is_complete, feedback
    """

    text = raw_text.strip()

    def _extract_completion(
        payload: Any,
    ) -> (
        tuple[
            str,
            bool,
            dict[str, Any] | None,
        ]
        | None
    ):
        if not isinstance(
            payload,
            dict,
        ):
            return None

        is_complete = payload.get(
            "interview_complete"
        )

        if (
            is_complete is True
            or str(is_complete).lower()
            == "true"
        ):
            return (
                str(
                    payload.get(
                        "next_question",
                        (
                            "Thank you for "
                            "participating in "
                            "the interview."
                        ),
                    )
                ),
                True,
                payload.get(
                    "feedback"
                ),
            )

        return None

    # --------------------------------------------------------
    # 1. JSON code block
    # --------------------------------------------------------

    code_block_match = re.search(
        r"```json\s*(.*?)\s*```",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    if code_block_match:

        json_text = (
            code_block_match
            .group(1)
            .strip()
        )

        try:
            payload = json.loads(
                json_text
            )

            result = _extract_completion(
                payload
            )

            if result:
                return result

        except json.JSONDecodeError:

            logger.warning(
                "Gemini returned invalid "
                "completion JSON inside "
                "a code block."
            )

    # --------------------------------------------------------
    # 2. Raw / embedded JSON
    # --------------------------------------------------------

    idx = text.find(
        '"interview_complete"'
    )

    if idx != -1:

        start_idx = text.rfind(
            "{",
            0,
            idx,
        )

        if start_idx != -1:

            for end_idx in range(
                len(text) - 1,
                start_idx,
                -1,
            ):

                if text[end_idx] != "}":
                    continue

                try:

                    json_text = text[
                        start_idx:
                        end_idx + 1
                    ]

                    payload = json.loads(
                        json_text
                    )

                    result = (
                        _extract_completion(
                            payload
                        )
                    )

                    if result:
                        return result

                except json.JSONDecodeError:
                    continue

    # --------------------------------------------------------
    # 3. Normal interviewer response
    # --------------------------------------------------------

    clean_text = re.sub(
        r"```json.*?```",
        "",
        text,
        flags=(
            re.DOTALL
            | re.IGNORECASE
        ),
    ).strip()

    return (
        clean_text,
        False,
        None,
    )


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
    - rate limits
    - temporary service errors
    - model fallback
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

        for attempt in range(
            max_retries
        ):

            try:

                logger.info(
                    "Calling Gemini model: %s",
                    attempt_model,
                )

                model = (
                    _get_gemini_model(
                        attempt_model
                    )
                )

                chat = model.start_chat(
                    history=history
                )

                response = (
                    chat.send_message(
                        message
                    )
                )

                return response.text

            except ResourceExhausted as error:

                last_error = error

                wait_time = (
                    2 ** attempt * 3
                )

                logger.warning(
                    (
                        "Rate limit for %s. "
                        "Retry %d/%d. "
                        "Waiting %d seconds."
                    ),
                    attempt_model,
                    attempt + 1,
                    max_retries,
                    wait_time,
                )

                if (
                    attempt
                    < max_retries - 1
                ):
                    time.sleep(
                        wait_time
                    )

            except ServiceUnavailable as error:

                last_error = error

                wait_time = (
                    2 ** attempt * 2
                )

                logger.warning(
                    (
                        "Gemini temporarily "
                        "unavailable. "
                        "Retry %d/%d."
                    ),
                    attempt + 1,
                    max_retries,
                )

                if (
                    attempt
                    < max_retries - 1
                ):
                    time.sleep(
                        wait_time
                    )

            except GoogleAPIError as error:

                last_error = error

                error_text = str(
                    error
                )

                lower_error = (
                    error_text.lower()
                )

                if (
                    "not found"
                    in lower_error
                    or "not available"
                    in lower_error
                    or "404"
                    in lower_error
                ):
                    logger.warning(
                        (
                            "Model %s unavailable. "
                            "Trying next model."
                        ),
                        attempt_model,
                    )

                    break

                logger.error(
                    "Gemini API error: %s",
                    error_text,
                )

                raise RuntimeError(
                    (
                        "Gemini API error: "
                        f"{error_text[:300]}"
                    )
                ) from error

            except Exception as error:

                logger.exception(
                    "Unexpected Gemini error."
                )

                raise RuntimeError(
                    (
                        "Unexpected Gemini error: "
                        f"{error}"
                    )
                ) from error

    raise RuntimeError(
        (
            "All Gemini models failed. "
            f"Last error: {last_error}"
        )
    )


# ============================================================
# GEMINI GENERATION HELPERS
# ============================================================

async def _generate_gemini_question(
    session: InterviewSession,
    candidate: dict[str, Any],
    curriculum_summary: str,
    user_message: str | None,
    current_topic: str,
    current_day: int | None,
    slot_within_topic: int,
    question_num: int,
) -> tuple[
    str,
    bool,
    dict[str, Any] | None,
]:
    """
    Generate a question using Gemini with strict topic enforcement.
    """

    system_prompt = _build_system_prompt(
        candidate,
        curriculum_summary,
    )

    plan_context = _build_interview_plan_context(
        session
    )

    preferred_model = _MODEL_FALLBACK_ORDER[0]

    # Slot depth guidance
    if slot_within_topic == 0:
        slot_guidance = (
            f"This is Question {question_num} of 8 (the FIRST question on '{current_topic}').\n"
            f"- Ask a foundational, conceptual, or architectural design question strictly about '{current_topic}'.\n"
            f"- Personalize with the candidate's projects or background where applicable."
        )
    else:
        slot_guidance = (
            f"This is Question {question_num} of 8 (the SECOND question on '{current_topic}').\n"
            f"- Ask a deeper technical follow-up, practical implementation, trade-off, or troubleshooting question strictly about '{current_topic}'.\n"
            f"- Build on the candidate's previous response.\n"
            f"- Do NOT repeat previously asked questions."
        )

    asked_list = (
        "\n".join(f"- {q}" for q in session.asked_questions)
        if session.asked_questions
        else "None yet."
    )

    topic_instruction = f"""
## CURRENT INTERVIEW TOPIC
Topic: {current_topic} (Curriculum Day {current_day or 'N/A'})
Question Slot: Question {question_num} / 8 (Question {slot_within_topic + 1} of 2 for this topic)

## STRICT TOPIC ENFORCEMENT
1. You MUST generate exactly ONE technical interview question specifically and exclusively about: "{current_topic}".
2. Do NOT switch topics. Do NOT ask about other curriculum days or unrelated technologies.
3. Every generated question for this turn must remain strictly within "{current_topic}".
4. Previously asked questions in this session:
{asked_list}
5. NEVER repeat any question that has already been asked.

## DEPTH & STYLE
{slot_guidance}
"""

    if not user_message and not session.conversation_history:
        prompt = (
            f"{system_prompt}\n\n"
            f"{plan_context}\n\n"
            f"{topic_instruction}\n\n"
            "Begin the interview now. Give a brief, warm welcome (1 sentence) and then ask "
            f"Question 1 strictly on the topic: '{current_topic}'."
        )
        history: list[dict[str, Any]] = []
    else:
        prompt = (
            f"{system_prompt}\n\n"
            f"{plan_context}\n\n"
            f"{topic_instruction}\n\n"
            f"Candidate's latest answer:\n{user_message or 'No message'}\n\n"
            f"Acknowledge the candidate's answer in at most one short, natural sentence, "
            f"then ask Question {question_num} strictly focused on '{current_topic}'."
        )
        history = list(session.conversation_history)

    try:
        raw_response = _call_with_retry(
            model_name=preferred_model,
            history=history,
            message=prompt,
        )

        message, is_complete, feedback = _parse_response(
            raw_response
        )

        if not message.strip():
            message = _get_topic_fallback_question(
                session,
                current_topic,
                slot_within_topic,
            )

        return message, is_complete, feedback

    except Exception as error:
        logger.warning(
            "Gemini question generation error: %s. Using topic-specific fallback.",
            error,
        )
        fallback_question = _get_topic_fallback_question(
            session,
            current_topic,
            slot_within_topic,
        )
        return fallback_question, False, None


async def _generate_gemini_completion(
    session: InterviewSession,
    candidate: dict[str, Any],
    curriculum_summary: str,
    user_message: str | None,
) -> tuple[
    str,
    bool,
    dict[str, Any] | None,
]:
    """
    Generate structured evaluation feedback when all 8 questions have been answered.
    """

    system_prompt = _build_system_prompt(
        candidate,
        curriculum_summary,
    )

    plan_context = _build_interview_plan_context(
        session
    )

    preferred_model = _MODEL_FALLBACK_ORDER[0]

    plan = session.interview_plan or {}
    target_topics = plan.get("target_topics", [])

    prompt = f"""
{system_prompt}

{plan_context}

The candidate has completed all 8 questions of the interview across the planned topics:
{target_topics}

Candidate's final answer:
{user_message or 'Interview concluded.'}

The interview is now complete. Do NOT ask any more technical questions.
Evaluate the candidate's full performance across all topics discussed in the chat history.

Return ONLY valid JSON in this exact structure:
```json
{{
  "interview_complete": true,
  "next_question": "Thank you for participating in the interview. We have completed all technical topics.",
  "feedback": {{
    "overall_score": 8,
    "summary": "2-3 sentence summary of candidate performance across topics.",
    "strengths_demonstrated": [
      "Strength 1",
      "Strength 2"
    ],
    "areas_for_improvement": [
      "Area 1",
      "Area 2"
    ],
    "topic_scores": {{
      {', '.join(f'"{topic}": 8' for topic in target_topics) if target_topics else '"Technical Knowledge": 8'}
    }},
    "recommendation": "Strong Hire"
  }}
}}
```
"""

    history = list(session.conversation_history)

    try:
        raw_response = _call_with_retry(
            model_name=preferred_model,
            history=history,
            message=prompt,
        )

        message, is_complete, feedback = _parse_response(
            raw_response
        )

        if is_complete and feedback:
            return message, True, feedback

    except Exception as error:
        logger.warning(
            "Gemini completion generation failed: %s. Using default feedback.",
            error,
        )

    # Fallback feedback
    return (
        (
            "Thank you for participating in the interview. "
            "We have covered all target technical areas."
        ),
        True,
        {
            "overall_score": 8,
            "summary": (
                "The candidate demonstrated strong practical and conceptual understanding "
                "across the planned curriculum topics."
            ),
            "strengths_demonstrated": [
                "Technical problem solving",
                "Practical implementation knowledge",
            ],
            "areas_for_improvement": [
                "System design trade-offs",
                "Edge-case consideration",
            ],
            "topic_scores": {
                topic: 8
                for topic in target_topics
            } or {"Technical Knowledge": 8},
            "recommendation": "Hire",
        },
    )


# ============================================================
# MAIN INTERVIEW FUNCTION
# ============================================================

async def run_interview_turn(
    session: InterviewSession,
    candidate: dict[str, Any],
    curriculum_summary: str,
    user_message: str | None,
) -> tuple[
    str,
    bool,
    dict[str, Any] | None,
]:
    """
    Run one interview turn.

    Deterministic Flow:
    1. Check if completion criteria are met (8 questions answered).
    2. Assign target topic for the current question slot (question_count // 2).
    3. Record topic coverage immediately.
    4. Generate question (mock or Gemini) strictly for the assigned topic.

    Returns:
        (
            interviewer_message,
            is_complete,
            feedback
        )
    """

    # --------------------------------------------------------
    # 1. Check completion
    # --------------------------------------------------------
    if can_complete(session) and user_message:
        if MOCK_MODE:
            plan = session.interview_plan or {}
            target_topics = plan.get("target_topics", [])
            return (
                (
                    "Thank you for participating in the interview. "
                    "We have covered all target technical areas."
                ),
                True,
                {
                    "overall_score": 8,
                    "summary": (
                        "The candidate demonstrated strong practical and conceptual understanding "
                        "across all planned curriculum topics."
                    ),
                    "strengths_demonstrated": [
                        "Practical AI Engineering",
                        "RAG fundamentals",
                        "Prompt Engineering",
                    ],
                    "areas_for_improvement": [
                        "Advanced system design",
                        "Production AI concepts",
                    ],
                    "topic_scores": {
                        topic: 8
                        for topic in (session.topics_covered or target_topics)
                    } or {
                        "Technical Knowledge": 8,
                        "Project Understanding": 8,
                        "Problem Solving": 7,
                    },
                    "recommendation": "Strong Hire",
                },
            )

        return await _generate_gemini_completion(
            session=session,
            candidate=candidate,
            curriculum_summary=curriculum_summary,
            user_message=user_message,
        )

    # --------------------------------------------------------
    # 2. Assign next planned topic
    # --------------------------------------------------------
    _assign_next_planned_topic(session)
    record_covered_topic(session)

    current_topic = session.current_topic or "AI Engineering"
    current_day = session.current_curriculum_day
    slot_within_topic = session.question_count % 2
    question_num = session.question_count + 1

    # --------------------------------------------------------
    # 3. Generate Question
    # --------------------------------------------------------
    if MOCK_MODE:
        question = _get_mock_question(session)
        return (
            question,
            False,
            None,
        )

    return await _generate_gemini_question(
        session=session,
        candidate=candidate,
        curriculum_summary=curriculum_summary,
        user_message=user_message,
        current_topic=current_topic,
        current_day=current_day,
        slot_within_topic=slot_within_topic,
        question_num=question_num,
    )