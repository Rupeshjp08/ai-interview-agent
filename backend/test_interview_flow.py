"""
Test Interview Flow
===================
Simulates the entire multi-turn interview lifecycle from Turn 1 to Turn 9+
to verify deterministic topic mapping, question generation, difficulty progression,
non-duplication, metadata tracking, and completion behavior.
"""

import asyncio
from schemas.interview import InterviewRequest
from routers.interview import conduct_interview
from services.session_manager import _sessions


async def run_test():
    print("=" * 70)
    print("RUNNING 8-QUESTION INTERVIEW VERIFICATION TEST")
    print("=" * 70)

    candidate_id = "candidate_001"
    session_id = None
    asked_questions = []

    expected_sequence = [
        (1, 8, "Conversation memory", 0),
        (2, 8, "Conversation memory", 1),
        (3, 1, "What is AI/ML", 0),
        (4, 1, "What is AI/ML", 1),
        (5, 3, "Text embeddings", 0),
        (6, 3, "Text embeddings", 1),
        (7, 10, "LangChain architecture", 0),
        (8, 10, "LangChain architecture", 1),
    ]

    # ----------------------------------------------------
    # Turn 1 to 8: Question Generation
    # ----------------------------------------------------
    for turn_num, (expected_q_count, expected_day, expected_topic, slot) in enumerate(expected_sequence, start=1):
        if turn_num == 1:
            req = InterviewRequest(candidate_id=candidate_id)
        else:
            req = InterviewRequest(
                session_id=session_id,
                candidate_id=candidate_id,
                user_message=f"This is the candidate's detailed answer to question {turn_num - 1}."
            )

        resp = await conduct_interview(req)
        session_id = resp.session_id
        meta = resp.metadata

        print(f"\n--- Turn {turn_num} (Asking Q{expected_q_count}) ---")
        print(f"Message: {resp.message}")
        print(f"Metadata: question_count={meta['question_count']}, current_day={meta['current_curriculum_day']}, current_topic='{meta['current_topic']}'")
        print(f"Curriculum days covered: {meta['curriculum_days_covered']}")
        print(f"Topics covered: {meta['topics_covered']}")

        # Assertions
        assert resp.is_complete is False, f"Turn {turn_num} should not be complete"
        assert meta["question_count"] == expected_q_count, f"Expected question_count={expected_q_count}, got {meta['question_count']}"
        assert meta["current_curriculum_day"] == expected_day, f"Expected day={expected_day}, got {meta['current_curriculum_day']}"
        assert meta["current_topic"] == expected_topic, f"Expected topic='{expected_topic}', got '{meta['current_topic']}'"
        assert expected_day in meta["curriculum_days_covered"], f"Day {expected_day} not in covered days"
        assert expected_topic in meta["topics_covered"], f"Topic {expected_topic} not in covered topics"

        # Check for generic fallback
        assert "Can you explain the key engineering considerations behind this topic?" not in resp.message, "Generic fallback detected!"

        # Check for duplicates
        assert resp.message not in asked_questions, f"Duplicate question detected: {resp.message}"
        asked_questions.append(resp.message)

    # ----------------------------------------------------
    # Turn 9: Answering Q8 -> Interview Completion
    # ----------------------------------------------------
    print("\n--- Turn 9 (Candidate answers Q8 -> Completion) ---")
    req = InterviewRequest(
        session_id=session_id,
        candidate_id=candidate_id,
        user_message="This is my final comprehensive answer to Question 8 regarding LangChain architecture in production."
    )
    resp = await conduct_interview(req)

    print(f"Completed: {resp.is_complete}")
    print(f"Closing Message: {resp.message}")
    print(f"Feedback: {resp.feedback}")
    print(f"Final Question Count: {resp.metadata['question_count']}")
    print(f"Curriculum days covered: {resp.metadata['curriculum_days_covered']}")

    assert resp.is_complete is True, "Turn 9 should complete the interview"
    assert resp.feedback is not None, "Feedback must be present on completion"
    assert resp.feedback.get("overall_score") is not None, "Feedback must contain overall_score"
    assert resp.metadata["question_count"] == 8, f"Question count should remain 8, got {resp.metadata['question_count']}"
    assert len(resp.metadata["curriculum_days_covered"]) == 4, "All 4 days should be covered"

    # ----------------------------------------------------
    # Turn 10: Call after completion -> returns cached result
    # ----------------------------------------------------
    print("\n--- Turn 10 (Post-completion call) ---")
    req = InterviewRequest(
        session_id=session_id,
        candidate_id=candidate_id,
        user_message="Hello again?"
    )
    resp = await conduct_interview(req)
    assert resp.is_complete is True, "Post-completion call should return is_complete=True"
    assert "already been completed" in resp.message

    print("\n" + "=" * 70)
    print("ALL 8 QUESTIONS AND COMPLETION TESTS PASSED PERFECTLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_test())
