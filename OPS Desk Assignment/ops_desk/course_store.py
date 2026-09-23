"""Load courses.json from disk (FR-2). Course facts never live in code."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

COURSES_PATH = Path(__file__).resolve().parent.parent / "courses.json"


class CourseDataError(Exception):
    """Internal load problem — tools convert this to a model-actionable sentence (NFR-4)."""


@lru_cache(maxsize=1)
def load_courses() -> dict[str, Any]:
    if not COURSES_PATH.is_file():
        raise CourseDataError(f"courses.json not found at {COURSES_PATH}")
    try:
        with COURSES_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise CourseDataError(f"courses.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("courses"), list):
        raise CourseDataError("courses.json must be an object with a top-level 'courses' array")
    return data


def clear_course_cache() -> None:
    """Test/fixture helper: drop cache after editing courses.json."""
    load_courses.cache_clear()


def find_course(course_id: str) -> dict[str, Any] | None:
    for course in load_courses()["courses"]:
        if course.get("id") == course_id:
            return course
    return None


def find_assignment(assignment_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    for course in load_courses()["courses"]:
        for assignment in course.get("assignments") or []:
            if assignment.get("id") == assignment_id:
                return course, assignment
    return None
