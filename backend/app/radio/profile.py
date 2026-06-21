from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from threading import Lock
from time import time
from typing import Any

from app.radio.models import RadioMode


class DriverProfileStore:
    """Small persistent memory used to personalize live radio responses."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(os.path.expandvars(str(path))).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._data = self._load()

    def mode(self, fallback: RadioMode) -> RadioMode:
        with self._lock:
            raw = str(self._data.get("mode") or fallback.value)
        try:
            return RadioMode(raw)
        except ValueError:
            return fallback

    def set_mode(self, mode: RadioMode) -> None:
        with self._lock:
            self._data["mode"] = mode.value
            self._data["updated_at"] = time()
            self._save_locked()

    def record_question(self, topic: str | None) -> None:
        if not topic:
            return
        with self._lock:
            topics = Counter(self._data.get("question_topics") or {})
            topics[topic] += 1
            self._data["question_topics"] = dict(topics)
            self._data["updated_at"] = time()
            self._save_locked()

    def record_coaching_category(self, category: str | None) -> None:
        if not category:
            return
        with self._lock:
            categories = Counter(self._data.get("coaching_categories") or {})
            categories[category] += 1
            self._data["coaching_categories"] = dict(categories)
            self._data["updated_at"] = time()
            self._save_locked()

    def context(self) -> dict[str, Any]:
        with self._lock:
            data = json.loads(json.dumps(self._data))
        question_topics = Counter(data.get("question_topics") or {})
        coaching_categories = Counter(data.get("coaching_categories") or {})
        return {
            "mode": data.get("mode", RadioMode.RACE.value),
            "frequent_question_topics": question_topics.most_common(5),
            "recurring_coaching_categories": coaching_categories.most_common(5),
            "interaction_count": int(sum(question_topics.values())),
        }

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {
                "version": 1,
                "mode": RadioMode.RACE.value,
                "question_topics": {},
                "coaching_categories": {},
                "updated_at": time(),
            }

    def _save_locked(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.path)
