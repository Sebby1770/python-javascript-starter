from __future__ import annotations

import re
from datetime import date, timedelta

from .store import normalise_tags, validate_due_date


PRIORITY_RE = re.compile(r"\b(high|medium|low)\s+priority\b", re.IGNORECASE)
PRIORITY_SHORT_RE = re.compile(r"\bpriority\s*:\s*(high|medium|low)\b", re.IGNORECASE)
OWNER_RE = re.compile(r"\bfor\s+([A-Za-z][A-Za-z0-9_-]*)\b", re.IGNORECASE)
OWNER_EXPLICIT_RE = re.compile(r"\bowner\s*:\s*([A-Za-z][A-Za-z0-9_-]*)\b", re.IGNORECASE)
MINUTES_RE = re.compile(
    r"\b(\d{1,3})\s*(?:min(?:ute)?s?|m)\b",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"#([\w-]+)")
DUE_RE = re.compile(
    r"\bdue\s+(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)

WEEKDAY_OFFSET = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

VALID_RECURRENCES = {"daily", "weekly", "monthly"}
RECURRENCE_RE = re.compile(r"\b(daily|weekly|monthly)\b", re.IGNORECASE)


def _next_weekday(reference: date, weekday: int) -> date:
    days_ahead = (weekday - reference.weekday()) % 7
    if days_ahead == 0:
        return reference
    return reference + timedelta(days=days_ahead)


def parse_due_token(token: str, *, reference: date | None = None) -> str | None:
    today = reference or date.today()
    lowered = token.strip().lower()

    if lowered == "today":
        return today.isoformat()
    if lowered == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if lowered in WEEKDAY_OFFSET:
        return _next_weekday(today, WEEKDAY_OFFSET[lowered]).isoformat()
    return validate_due_date(token)


def parse_task_text(text: str, *, reference: date | None = None) -> dict[str, object]:
    """Parse free-form task text into structured fields."""
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("Task text is required.")

    working = raw
    priority = "medium"
    owner = "Unassigned"
    minutes = 25
    due_date: str | None = None
    tags: list[str] = []
    recurrence: str | None = None

    for match in PRIORITY_RE.finditer(working):
        priority = match.group(1).lower()
    working = PRIORITY_RE.sub(" ", working)

    match = PRIORITY_SHORT_RE.search(working)
    if match:
        priority = match.group(1).lower()
    working = PRIORITY_SHORT_RE.sub(" ", working)

    match = OWNER_EXPLICIT_RE.search(working)
    if match:
        owner = match.group(1)
    else:
        match = OWNER_RE.search(working)
        if match:
            owner = match.group(1)
    working = OWNER_EXPLICIT_RE.sub(" ", working)
    working = OWNER_RE.sub(" ", working)

    match = MINUTES_RE.search(working)
    if match:
        minutes = max(1, int(match.group(1)))
    working = MINUTES_RE.sub(" ", working)

    match = DUE_RE.search(working)
    if match:
        due_date = parse_due_token(match.group(1), reference=reference)
    working = DUE_RE.sub(" ", working)

    tag_matches = TAG_RE.findall(working)
    if tag_matches:
        tags = normalise_tags(tag_matches)
    working = TAG_RE.sub(" ", working)

    match = RECURRENCE_RE.search(working)
    if match:
        recurrence = match.group(1).lower()
    working = RECURRENCE_RE.sub(" ", working)

    title = re.sub(r"\s+", " ", working).strip(" ,.-")
    if not title:
        raise ValueError("Could not extract a task title from the text.")

    return {
        "title": title,
        "owner": owner,
        "priority": priority,
        "minutes": minutes,
        "due_date": due_date,
        "tags": tags,
        "recurrence": recurrence,
    }