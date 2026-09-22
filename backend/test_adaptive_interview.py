"""
Test Answer-Aware Adaptive Interviewing
======================================

Validates dynamic difficulty progression, answer evaluation, topic progression,
fallback parsing, and privacy constraints.
"""

import asyncio
from schemas.interview import InterviewRequest
from routers.interview import conduct_interview
from services.session_manager import _sessions
from services.answer_evaluator import (
    AnswerEvaluation,
    _parse_evaluation_json,
    apply_difficulty_adjustment,
    evaluate_answer_mock,
)


async def test_adaptive_scenarios():
    print("=" * 70)
    print("RUNNING ADAPTIVE INTERVIEWING VERIFICATION TESTS")
    print("=" * 70)

    # ----------------------------------------------------
    # 1. Test Difficulty Ladder Unit Logic
    # ----------------------------------------------------
    print("\n--- Test 1: Difficulty Ladder Unit Logic ---")
    assert apply_difficulty_adjustment("intermediate", "increase") == "advanced"
    assert apply_difficulty_adjustment("advanced", "increase") == "advanced"  # Max clamp
    assert apply_difficulty_adjustment("intermediate", "decrease") == "beginner"
    assert apply_difficulty_adjustment("beginner", "decrease") == "beginner"  # Min clamp
    assert apply_difficulty_adjustment("intermediate", "maintain") == "intermediate"
    print("[PASS] Difficulty ladder logic passed")

    # ----------------------------------------------------
    # 2. Test Robust JSON Parser
    # ----------------------------------------------------
    print("\n--- Test 2: JSON Parser Fallback & Robustness ---")
    # Code block JSON
    json_block = """```json
    {
        "answer_quality": 9,
        "technical_accuracy": 9,
        "confidence": "high",
        "strengths": ["Excellent detail"],
        "missing_concepts": [],
        "difficulty_adjustment": "increase"
    }
    ```"""
    parsed = _parse_evaluation_json(json_block)
    assert parsed.answer_quality == 9
    assert parsed.difficulty_adjustment == "increase"

    # Malformed text
    parsed_bad = _parse_evaluation_json("This is not JSON at all!")
    assert parsed_bad.answer_quality == 5
    assert parsed_bad.difficulty_adjustment == "maintain"
    print("[PASS] JSON parser robustness passed")

    # ----------------------------------------------------
    # 3. Scenario A: Strong Candidate -> Difficulty Increases
    # ----------------------------------------------------
    print("\n--- Test 3: Strong Candidate Flow (Difficulty Increases) ---")
    candidate_id = "candidate_001"
    
    # Turn 1 (Q1)
    req1 = InterviewRequest(candidate_id=candidate_id)
    resp1 = await conduct_interview(req1)
    sess_id = resp1.session_id
    print(f"Q1 asked: {resp1.message}")
    assert resp1.metadata["current_difficulty"] == "intermediate"

    # Turn 2: Provide a strong, detailed answer to Q1
    strong_answer = (
        "To design conversation memory for a multi-turn AI application, I would implement "
        "a modular memory architecture using a hybrid strategy. First, a short-term buffer memory "
        "retains recent interaction turns for immediate context window insertion. Second, a summarization "
        "agent periodically compresses earlier dialog into dense key-value summaries. Third, long-term "
        "episodic memory is persisted in a vector database like Chroma or Pinecone, indexed using high-dimensional embeddings."
    )
    req2 = InterviewRequest(session_id=sess_id, candidate_id=candidate_id, user_message=strong_answer)
    resp2 = await conduct_interview(req2)
    print(f"Q2 asked: {resp2.message}")
    print(f"Metadata Q2 difficulty: {resp2.metadata['current_difficulty']}")
    assert resp2.metadata["current_difficulty"] == "advanced", "Difficulty should increase to advanced after strong answer"
    assert resp2.metadata["current_topic"] == "Conversation memory", "Topic should remain Conversation memory for Q2"

    # Turn 3: Provide another strong answer to Q2 -> Topic switches to 'What is AI/ML'
    req3 = InterviewRequest(session_id=sess_id, candidate_id=candidate_id, user_message=strong_answer)
    resp3 = await conduct_interview(req3)
    print(f"Q3 asked: {resp3.message}")
    print(f"Metadata Q3 topic: '{resp3.metadata['current_topic']}', difficulty: {resp3.metadata['current_difficulty']}")
    assert resp3.metadata["current_topic"] == "What is AI/ML", "Topic should switch to 'What is AI/ML' for Q3"
    assert resp3.metadata["current_difficulty"] == "advanced", "Difficulty should remain advanced across topic transition (Constraint 1)"
    print("[PASS] Strong candidate flow and cross-topic difficulty retention passed")

    # ----------------------------------------------------
    # 4. Scenario B: Weak Candidate -> Difficulty Decreases
    # ----------------------------------------------------
    print("\n--- Test 4: Weak Candidate Flow (Difficulty Decreases) ---")
    req1 = InterviewRequest(candidate_id=candidate_id)
    resp1 = await conduct_interview(req1)
    sess_id = resp1.session_id

    # Provide a weak/short answer to Q1
    weak_answer = "i don't know"
    req2 = InterviewRequest(session_id=sess_id, candidate_id=candidate_id, user_message=weak_answer)
    resp2 = await conduct_interview(req2)
    print(f"Q2 asked: {resp2.message}")
    print(f"Metadata Q2 difficulty: {resp2.metadata['current_difficulty']}")
    assert resp2.metadata["current_difficulty"] == "beginner", "Difficulty should decrease to beginner after weak answer"
    assert resp2.metadata["current_topic"] == "Conversation memory"
    print("[PASS] Weak candidate flow passed")

    # ----------------------------------------------------
    # 5. Scenario C: Privacy Check (last_evaluation not leaked)
    # ----------------------------------------------------
    print("\n--- Test 5: Privacy Check ---")
    resp_dict = resp2.model_dump()
    assert "last_evaluation" not in resp_dict, "last_evaluation must not be exposed in top-level response"
    assert "last_evaluation" not in resp2.metadata, "last_evaluation must not be exposed in response metadata"
    
    # Internal session does hold it
    session_obj = _sessions[sess_id]
    assert session_obj.last_evaluation is not None, "Internal session object should store last_evaluation internally"
    assert session_obj.last_evaluation["difficulty_adjustment"] == "decrease"
    print("[PASS] Internal evaluation privacy enforcement passed")

    print("\n" + "=" * 70)
    print("ALL ADAPTIVE INTERVIEWING TESTS PASSED PERFECTLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_adaptive_scenarios())
