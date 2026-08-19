"""
Interview Controller
====================
Builds and manages a deterministic interview plan.

Responsibilities:
- Select curriculum days/topics for the interview.
- Prefer candidate weak areas, strengths, and project-related topics.
- Provide the next planned topic.
- Guarantee minimum curriculum coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InterviewPlan:
    """Plan for a single interview."""

    target_days: list[int] = field(default_factory=list)
    target_topics: list[str] = field(default_factory=list)


def _extract_day_topics(
    curriculum_days: list[dict[str, Any]],
) -> list[tuple[int, list[str]]]:
    """Extract (day_number, topics) from curriculum data."""

    result: list[tuple[int, list[str]]] = []

    for day in curriculum_days:
        try:
            day_number = int(day.get("day"))
        except (TypeError, ValueError):
            continue

        topics = [
            str(topic).strip()
            for topic in day.get("topics", [])
            if str(topic).strip()
        ]

        if topics:
            result.append((day_number, topics))

    return result


def build_interview_plan(
    candidate: dict[str, Any],
    curriculum_days: list[dict[str, Any]],
    minimum_days: int = 4,
) -> InterviewPlan:
    """
    Build a deterministic curriculum plan.

    Priority:
    1. Candidate weak areas
    2. Candidate strengths
    3. Candidate projects
    4. Remaining curriculum
    """

    day_topics = _extract_day_topics(curriculum_days)

    if not day_topics:
        return InterviewPlan()

    strengths = [
        str(item).lower()
        for item in candidate.get("strengths", [])
    ]

    weak_areas = [
        str(item).lower()
        for item in candidate.get("weak_areas", [])
    ]

    projects_text = " ".join(
        f"{project.get('name', '')} "
        f"{project.get('description', '')}"
        for project in candidate.get("projects", [])
    ).lower()

    scored_days: list[tuple[int, int, str]] = []

    for day_number, topics in day_topics:
        topic_text = " ".join(topics).lower()
        score = 0

        # Weak-area relevance
        for weak_area in weak_areas:
            for word in weak_area.split():
                if len(word) > 3 and word in topic_text:
                    score += 4

        # Strength relevance
        for strength in strengths:
            for word in strength.split():
                if len(word) > 3 and word in topic_text:
                    score += 2

        # Project relevance
        for word in topic_text.split():
            if len(word) > 4 and word in projects_text:
                score += 3

        # Use the first topic as the representative topic for now.
        representative_topic = topics[0]

        scored_days.append(
            (
                score,
                day_number,
                representative_topic,
            )
        )

    # Highest relevance first, then earlier day.
    scored_days.sort(
        key=lambda item: (-item[0], item[1])
    )

    selected = scored_days[:minimum_days]

    # Fallback: ensure enough distinct days.
    if len(selected) < minimum_days:
        existing_days = {
            item[1]
            for item in selected
        }

        for item in scored_days:
            if item[1] not in existing_days:
                selected.append(item)
                existing_days.add(item[1])

            if len(selected) >= minimum_days:
                break

    return InterviewPlan(
        target_days=[
            item[1]
            for item in selected
        ],
        target_topics=[
            item[2]
            for item in selected
        ],
    )


def get_target_for_question(
    plan: InterviewPlan,
    question_count: int,
) -> tuple[int, str] | None:
    """
    Return (day, topic) for the given question slot using deterministic
    2-questions-per-topic mapping:
        question_count 0 or 1 -> topic index 0
        question_count 2 or 3 -> topic index 1
        question_count 4 or 5 -> topic index 2
        question_count 6 or 7 -> topic index 3

    Topic selection is strictly determined by question_count // 2,
    NOT by whether a curriculum day has already been recorded in coverage history.
    """

    if not plan.target_days or not plan.target_topics:
        return None

    topic_index = min(
        question_count // 2,
        len(plan.target_topics) - 1,
    )

    return (
        plan.target_days[topic_index],
        plan.target_topics[topic_index],
    )


def get_next_target(
    plan: InterviewPlan,
    covered_days: list[int],
) -> tuple[int, str] | None:
    """
    Return the next planned day/topic that hasn't been covered.
    """

    covered = set(covered_days)

    for day, topic in zip(
        plan.target_days,
        plan.target_topics,
    ):
        if day not in covered:
            return day, topic

    return None


def get_plan_from_session(
    session: Any,
) -> InterviewPlan:
    """
    Convert the session's stored plan into an InterviewPlan object.
    """

    plan = session.interview_plan or {}

    return InterviewPlan(
        target_days=list(
            plan.get("target_days", [])
        ),
        target_topics=list(
            plan.get("target_topics", [])
        ),
    )


def has_required_coverage(
    covered_days: list[int],
    minimum_days: int = 4,
) -> bool:
    """Return True when enough distinct curriculum days are covered."""

    return len(
        set(covered_days)
    ) >= minimum_days