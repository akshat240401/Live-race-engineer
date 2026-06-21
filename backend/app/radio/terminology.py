from __future__ import annotations

import re


# Common speech-recognition mistakes seen with racing vocabulary. These are
# intentionally conservative: replacements are applied only to whole phrases.
_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bengine near\b", "engineer"),
    (r"\bengine here\b", "engineer"),
    (r"\brain engineer\b", "race engineer"),
    (r"\bdear ass\b", "DRS"),
    (r"\bd r s\b", "DRS"),
    (r"\be r s\b", "ERS"),
    (r"\benergy recovery system\b", "ERS"),
    (r"\bbox slap\b", "box this lap"),
    (r"\bbox the slap\b", "box this lap"),
    (r"\bunder cut\b", "undercut"),
    (r"\bover cut\b", "overcut"),
    (r"\bsoft tires\b", "soft tyres"),
    (r"\bmedium tires\b", "medium tyres"),
    (r"\bhard tires\b", "hard tyres"),
    (r"\bintermediate tires\b", "intermediate tyres"),
    (r"\bwet tires\b", "wet tyres"),
    (r"\btires\b", "tyres"),
    (r"\btire\b", "tyre"),
    (r"\bbreak temperatures?\b", "brake temperatures"),
    (r"\bbreak bias\b", "brake bias"),
    (r"\bsector to\b", "sector two"),
    (r"\bsector too\b", "sector two"),
    (r"\bsector tree\b", "sector three"),
    (r"\bcar head\b", "car ahead"),
)


def normalize_racing_transcript(text: str) -> str:
    """Normalize common F1 terms while preserving readable punctuation."""
    normalized = " ".join(str(text).strip().split())
    for pattern, replacement in _REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return normalized


def normalized_message_key(text: str) -> str:
    """Create a stable key for duplicate suppression."""
    value = normalize_racing_transcript(text).casefold()
    value = re.sub(r"\d+(?:\.\d+)?", "#", value)
    value = re.sub(r"[^a-z0-9#]+", " ", value)
    return " ".join(value.split())
