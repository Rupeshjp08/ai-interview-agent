"""
Answer Evaluator Service
========================

Evaluates candidate responses for technical accuracy, answer quality,
demonstrated strengths, missing concepts, confidence, and recommended
difficulty adjustments.

This evaluator operates internally. Its results guide the interview's
dynamic difficulty progression without exposing internal scoring or raw prompt output to the candidate.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Difficulty levels ladder
DIFFICULTY_LEVELS = ["beginner", "intermediate", "advanced"]


@dataclass
class AnswerEvaluation:
    """Structured evaluation of a candidate's answer."""

    answer_quality: int = 5          # 1 to 10
    technical_accuracy: int = 5      # 1 to 10
    confidence: str = "medium"       # "low", "medium", "high"
    strengths: list[str] = field(default_factory=list)
    missing_concepts: list[str] = field(default_factory=list)
    difficulty_adjustment: str = "maintain"  # "increase", "maintain", "decrease"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FALLBACK_EVALUATION = AnswerEvaluation(
    answer_quality=5,
    technical_accuracy=5,
    confidence="medium",
    strengths=["Provided a basic response"],
    missing_concepts=["Evaluation fallback applied"],
    difficulty_adjustment="maintain",
)


def apply_difficulty_adjustment(
    current_difficulty: str,
    adjustment: str,
) -> str:
    """
    Apply a difficulty adjustment step to the current difficulty level.

    Ladder:
        beginner <-> intermediate <-> advanced

    'increase': move up 1 step (max: advanced)
    'decrease': move down 1 step (min: beginner)
    'maintain': keep unchanged
    """
    curr = str(current_difficulty).lower().strip()
    if curr not in DIFFICULTY_LEVELS:
        curr = "intermediate"

    adj = str(adjustment).lower().strip()
    idx = DIFFICULTY_LEVELS.index(curr)

    if adj == "increase":
        new_idx = min(idx + 1, len(DIFFICULTY_LEVELS) - 1)
    elif adj == "decrease":
        new_idx = max(idx - 1, 0)
    else:
        new_idx = idx

    return DIFFICULTY_LEVELS[new_idx]


def evaluate_answer_mock(
    user_message: str,
    current_topic: str,
    current_difficulty: str,
) -> AnswerEvaluation:
    """
    Simulated answer evaluator for MOCK_MODE testing.

    Heuristics:
    - Detailed answers with key technical terms or words > 80 chars -> High quality -> "increase"
    - Very short answers (< 25 chars) or weak indicators -> Low quality -> "decrease"
    - Moderate answers -> "maintain"
    """
    text = (user_message or "").strip()
    lower_text = text.lower()

    # Check for explicitly weak or vague answers
    weak_signals = ["i don't know", "not sure", "no idea", "pass", "dunno", "skip"]
    if any(sig in lower_text for sig in weak_signals) or len(text) < 25:
        return AnswerEvaluation(
            answer_quality=3,
            technical_accuracy=3,
            confidence="low",
            strengths=[],
            missing_concepts=["Core domain concepts"],
            difficulty_adjustment="decrease",
        )

    # Check for strong, detailed responses
    strong_keywords = [
        "architecture", "trade-off", "tradeoff", "latency", "scale",
        "implementation", "vector", "memory", "buffer", "embeddings",
        "langchain", "prompt", "optimization", "pipeline", "component",
        "comprehensive", "production", "design", "indexing", "transformer"
    ]
    has_strong_keywords = any(kw in lower_text for kw in strong_keywords)

    if len(text) > 80 or (len(text) > 40 and has_strong_keywords):
        return AnswerEvaluation(
            answer_quality=8,
            technical_accuracy=8,
            confidence="high",
            strengths=["Clear technical articulation", "Demonstrated domain knowledge"],
            missing_concepts=[],
            difficulty_adjustment="increase",
        )

    # Moderate answer
    return AnswerEvaluation(
        answer_quality=6,
        technical_accuracy=6,
        confidence="medium",
        strengths=["Basic technical response"],
        missing_concepts=["Depth and trade-off details"],
        difficulty_adjustment="maintain",
    )


def _parse_evaluation_json(raw_text: str) -> AnswerEvaluation:
    """
    Safely parse raw JSON or JSON within Markdown code blocks from Gemini evaluation output.
    Returns FALLBACK_EVALUATION if parsing fails or invalid structure.
    """
    if not raw_text or not raw_text.strip():
        logger.warning("Empty raw text provided to evaluation parser.")
        return FALLBACK_EVALUATION

    text = raw_text.strip()

    # 1. Try markdown json code block
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        json_str = match.group(1).strip()
    else:
        # 2. Try raw JSON extraction between { and }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = text[start : end + 1]
        else:
            json_str = text

    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return FALLBACK_EVALUATION

        # Extract fields with safe defaults and clamping
        quality = int(data.get("answer_quality", 5))
        quality = max(1, min(10, quality))

        accuracy = int(data.get("technical_accuracy", 5))
        accuracy = max(1, min(10, accuracy))

        conf = str(data.get("confidence", "medium")).lower()
        if conf not in {"low", "medium", "high"}:
            conf = "medium"

        adj = str(data.get("difficulty_adjustment", "maintain")).lower()
        if adj not in {"increase", "maintain", "decrease"}:
            adj = "maintain"

        strengths = data.get("strengths", [])
        if not isinstance(strengths, list):
            strengths = [str(strengths)]
        strengths = [str(s) for s in strengths]

        missing = data.get("missing_concepts", [])
        if not isinstance(missing, list):
            missing = [str(missing)]
        missing = [str(m) for m in missing]

        return AnswerEvaluation(
            answer_quality=quality,
            technical_accuracy=accuracy,
            confidence=conf,
            strengths=strengths,
            missing_concepts=missing,
            difficulty_adjustment=adj,
        )
    except Exception as exc:
        logger.warning("Failed to parse evaluation JSON from model output: %s", exc)
        return FALLBACK_EVALUATION


def evaluate_answer_gemini(
    user_message: str,
    last_question: str,
    current_topic: str,
    current_difficulty: str,
    call_gemini_func: Any,
) -> AnswerEvaluation:
    """
    Evaluate candidate answer using Gemini.
    `call_gemini_func` is a callable taking (history, prompt) and returning str.
    """
    prompt = f"""
You are an expert AI engineering interviewer evaluating a candidate's answer.

## INTERVIEW CONTEXT
Current Topic: {current_topic}
Current Question Difficulty: {current_difficulty}
Interviewer Question Asked: "{last_question}"
Candidate Answer: "{user_message}"

## EVALUATION INSTRUCTIONS
Analyze the candidate's answer for:
1. answer_quality (integer 1-10): Clarity, completeness, and structure.
2. technical_accuracy (integer 1-10): Correctness of concepts, terminology, and reasoning.
3. confidence ("low", "medium", or "high"): Assessment of candidate certainty.
4. strengths (list of strings): What the candidate did well or answered correctly.
5. missing_concepts (list of strings): Key points, trade-offs, or nuances the candidate missed.
6. difficulty_adjustment ("increase", "maintain", or "decrease"):
   - "increase": Answer was thorough, accurate, and strong. Target a harder question.
   - "maintain": Answer was adequate but missing some depth. Maintain current difficulty.
   - "decrease": Answer was vague, incorrect, or candidate struggled. Target an easier question.

Return ONLY valid JSON matching this exact structure:
```json
{{
  "answer_quality": 8,
  "technical_accuracy": 8,
  "confidence": "high",
  "strengths": ["Clear explanation of component architecture"],
  "missing_concepts": ["Did not mention error handling"],
  "difficulty_adjustment": "increase"
}}
```
""".strip()

    try:
        raw_output = call_gemini_func(history=[], message=prompt)
        return _parse_evaluation_json(raw_output)
    except Exception as exc:
        logger.warning("Gemini answer evaluation failed: %s. Using fallback.", exc)
        return FALLBACK_EVALUATION
