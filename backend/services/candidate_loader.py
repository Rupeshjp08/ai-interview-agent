"""
Candidate Loader Service
========================
Loads candidate JSON profiles from data/candidates/<candidate_id>.json.
Raises an HTTPException(404) if the profile is not found.
"""

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException

# Path relative to this file: ../../data/candidates/
_DATA_DIR = Path(__file__).parent.parent / "data" / "candidates"


def load_candidate(candidate_id: str) -> dict[str, Any]:
    """
    Load and return the candidate profile dict for the given candidate_id.

    Args:
        candidate_id: The unique identifier (e.g. 'candidate_001').

    Returns:
        A dict containing the full candidate profile.

    Raises:
        HTTPException(404): If no profile file exists for candidate_id.
    """
    profile_path = _DATA_DIR / f"{candidate_id}.json"

    if not profile_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Candidate profile not found for '{candidate_id}'. "
                f"Expected file: data/candidates/{candidate_id}.json"
            ),
        )

    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_candidates() -> list[dict[str, Any]]:
    """
    List all available candidate profiles as summary dicts.

    Returns only the fields needed for a selection list:
    candidate_id, name, cohort, days_completed, interview_difficulty,
    strengths, weak_areas.

    Returns:
        List of candidate summary dicts, sorted by candidate_id.
    """
    if not _DATA_DIR.exists():
        return []

    candidates = []
    for json_file in sorted(_DATA_DIR.glob("*.json")):
        # Skip README and non-candidate files
        if json_file.stem.startswith("README"):
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Return a trimmed summary (don't send full learning notes etc. in list)
            candidates.append(
                {
                    "candidate_id": data.get("candidate_id", json_file.stem),
                    "name": data.get("name", "Unknown"),
                    "cohort": data.get("cohort", "Unknown"),
                    "days_completed": data.get("days_completed", 0),
                    "interview_difficulty": data.get(
                        "interview_difficulty", "intermediate"
                    ),
                    "strengths": data.get("strengths", []),
                    "weak_areas": data.get("weak_areas", []),
                }
            )
        except (json.JSONDecodeError, OSError):
            continue  # Skip malformed files

    return candidates
