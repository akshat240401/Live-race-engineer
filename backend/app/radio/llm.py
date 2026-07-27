from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.telemetry.models import LiveTelemetrySnapshot


class LiveLLMResponder:
    """OpenAI-compatible live response generator with strict grounding."""

    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: int = 20,
        max_words: int = 32,
    ) -> None:
        self.enabled = bool(enabled and base_url and model)
        self.base_url = base_url.strip()
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_s = timeout_s
        self.max_words = max(12, max_words)
        self.last_error: str | None = None

    def answer(
        self,
        question: str,
        snapshot: LiveTelemetrySnapshot,
        conversation: Sequence[dict[str, str]],
        profile: dict[str, Any],
    ) -> str | None:
        if not self.enabled:
            return None

        endpoint = self._endpoint()
        context = self._telemetry_context(snapshot)
        history = list(conversation[-6:])
        prompt = {
            "question": question,
            "live_telemetry": context,
            "driver_profile": profile,
            "recent_conversation": history,
        }
        system = (
            "You are a calm Formula One race engineer speaking during a live race. "
            "Use only the supplied telemetry. Never invent gaps, tyre life, weather, "
            "strategy, damage, or opponent data. If evidence is missing, say so. "
            f"Reply in one or two short sentences and no more than {self.max_words} words. "
            "Prioritize immediate, actionable guidance and avoid markdown."
        )
        body = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 120,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
        }
        request = Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = str(payload["choices"][0]["message"]["content"]).strip()
            text = " ".join(text.split())
            self.last_error = None
            return self._limit_words(text)
        except (HTTPError, URLError, TimeoutError, KeyError, ValueError, OSError) as exc:
            self.last_error = str(exc)
            return None

    def _endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _limit_words(self, text: str) -> str:
        words = text.split()
        if len(words) <= self.max_words:
            return text
        return " ".join(words[: self.max_words]).rstrip(".,;:") + "."

    @staticmethod
    def _telemetry_context(snapshot: LiveTelemetrySnapshot) -> dict[str, Any]:
        history = list(snapshot.history[-120:])
        overlap_samples = sum(
            1
            for point in history
            if float(point.get("throttle", 0.0)) > 0.15
            and float(point.get("brake", 0.0)) > 0.15
        )
        overlap_ratio = overlap_samples / len(history) if history else 0.0
        return {
            "connected": snapshot.connected,
            "session_time": snapshot.session_time,
            "lap_number": snapshot.lap_number,
            "total_laps": snapshot.total_laps,
            "position": snapshot.position,
            "grid_size": snapshot.grid_size,
            "positions_gained": snapshot.positions_gained,
            "speed_kph": snapshot.speed_kph,
            "sector": snapshot.sector,
            "current_lap_time_ms": snapshot.current_lap_time_ms,
            "last_lap_time_ms": snapshot.last_lap_time_ms,
            "best_lap_time_ms": snapshot.best_lap_time_ms,
            "delta_to_car_ahead_s": snapshot.delta_to_car_ahead_s,
            "delta_to_leader_s": snapshot.delta_to_leader_s,
            "car_ahead": snapshot.car_ahead,
            "car_behind": snapshot.car_behind,
            "fuel_remaining_laps": snapshot.fuel_remaining_laps,
            "fuel_in_tank_kg": snapshot.fuel_in_tank_kg,
            "ers_percent": snapshot.ers_percent,
            "drs": snapshot.drs,
            "drs_allowed": snapshot.drs_allowed,
            "tyre_compound": snapshot.tyre_compound,
            "tyre_age_laps": snapshot.tyre_age_laps,
            "tyre_wear_pct": snapshot.tyre_wear_pct,
            "tyre_surface_temps_c": snapshot.tyre_surface_temps_c,
            "brake_temps_c": snapshot.brake_temps_c,
            "wing_damage_pct": snapshot.wing_damage_pct,
            "tyre_damage_pct": snapshot.tyre_damage_pct,
            "warnings": snapshot.warnings,
            "penalties_s": snapshot.penalties_s,
            "pit_status": snapshot.pit_status,
            "recent_brake_throttle_overlap_ratio": round(overlap_ratio, 3),
        }
