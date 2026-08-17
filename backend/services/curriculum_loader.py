"""
Curriculum Loader Service
=========================
Loads the 31-day AI Engineering Cohort curriculum from JSON files
in data/curriculum/. Only loads days that exist on disk; gracefully
skips missing day files.
"""

import json
from pathlib import Path
from typing import Any

# Path relative to this file: ../../data/curriculum/
_CURRICULUM_DIR = Path(__file__).parent.parent / "data" / "curriculum"


def load_all_curriculum() -> dict[int, dict[str, Any]]:
    """
    Load all available curriculum day files into a dict keyed by day number.

    Returns:
        Dict mapping day number (int) → curriculum dict.
    """
    curriculum: dict[int, dict[str, Any]] = {}

    if not _CURRICULUM_DIR.exists():
        return curriculum

    for json_file in sorted(_CURRICULUM_DIR.glob("day_*.json")):
        try:
            day_num = int(json_file.stem.split("_")[1])
            with open(json_file, "r", encoding="utf-8") as f:
                curriculum[day_num] = json.load(f)
        except (ValueError, json.JSONDecodeError):
            # Skip malformed files
            continue

    return curriculum


def load_candidate_curriculum(days_completed: int) -> list[dict[str, Any]]:
    """
    Return only the curriculum days the candidate has completed.

    Args:
        days_completed: Total number of cohort days the candidate finished.

    Returns:
        List of curriculum day dicts, sorted by day number.
    """
    all_curriculum = load_all_curriculum()
    return [
        day_data
        for day_num, day_data in sorted(all_curriculum.items())
        if day_num <= days_completed
    ]


def summarise_curriculum(curriculum_days: list[dict[str, Any]]) -> str:
    """
    Build a concise text summary of curriculum topics for inclusion
    in an AI system prompt.

    Args:
        curriculum_days: List of curriculum day dicts.

    Returns:
        Multi-line string summarising topics and key concepts.
    """
    lines: list[str] = []
    for day in curriculum_days:
        day_num = day.get("day", "?")
        title = day.get("title", "Unknown")
        topics = ", ".join(day.get("topics", []))
        lines.append(f"  Day {day_num}: {title} — {topics}")
    return "\n".join(lines)
