from __future__ import annotations

from time import time
from typing import Iterable

from app.telemetry.models import EngineerMessage


SEVERITY_PRIORITY = {
    "danger": 90,
    "warning": 75,
    "success": 70,
    "info": 45,
}


class RaceRadioDirector:
    """Decides what should actually be spoken.

    The rule engine can create several dashboard messages. The radio should only
    choose the most useful short call, then wait before talking again.
    """

    def __init__(self, min_gap_s: float = 3.5) -> None:
        self.min_gap_s = min_gap_s
        self._last_global_spoken = 0.0
        self._last_by_key: dict[str, float] = {}

    def reset(self) -> None:
        self._last_global_spoken = 0.0
        self._last_by_key.clear()

    def select_line(self, messages: Iterable[EngineerMessage]) -> str | None:
        candidates = list(messages)
        if not candidates:
            return None

        candidates.sort(key=self._message_priority, reverse=True)
        now_ts = time()

        for msg in candidates:
            if not bool(msg.evidence.get("can_voice", True)):
                continue

            line = self._radio_line(msg)
            if not line:
                continue

            key = str(msg.evidence.get("voice_key") or f"{msg.category}:{msg.title}")
            cooldown = float(msg.evidence.get("voice_cooldown_s", 25.0))
            priority = self._message_priority(msg)

            if now_ts - self._last_by_key.get(key, 0.0) < cooldown:
                continue

            # Let urgent calls interrupt sooner; keep normal advice from spamming.
            if priority < 85 and now_ts - self._last_global_spoken < self.min_gap_s:
                continue

            self._last_by_key[key] = now_ts
            self._last_global_spoken = now_ts
            return line

        return None

    def _message_priority(self, msg: EngineerMessage) -> int:
        evidence_priority = msg.evidence.get("priority")
        if isinstance(evidence_priority, int):
            return evidence_priority
        return SEVERITY_PRIORITY.get(msg.severity, 40)

    def _radio_line(self, msg: EngineerMessage) -> str | None:
        radio = msg.evidence.get("radio")
        if isinstance(radio, str) and radio.strip():
            return self._clean(radio)

        # Safe fallback for any future message that does not provide a radio line.
        if msg.severity in {"danger", "warning", "success"}:
            return self._clean(msg.title)
        return None

    def _clean(self, text: str) -> str:
        text = " ".join(text.strip().split())
        # Keep radio calls short. The dashboard still shows the full message.
        words = text.split()
        if len(words) > 9:
            text = " ".join(words[:9]) + "."
        return text