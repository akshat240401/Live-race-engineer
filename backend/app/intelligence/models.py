from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ForecastPoint:
    horizon_laps: int
    ahead_gap_s: float | None
    ahead_low_s: float | None
    ahead_high_s: float | None
    ahead_drs_probability: float | None
    behind_gap_s: float | None
    behind_low_s: float | None
    behind_high_s: float | None
    behind_drs_probability: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RivalModel:
    role: str
    name: str
    position: int | None
    current_gap_s: float | None
    predicted_gap_next_lap_s: float | None
    gap_trend_s_per_lap: float | None
    closing_probability: float
    drs_probability_next_lap: float
    pressure_score: float
    consistency_score: float
    predictability_score: float
    sample_count: int
    model_quality: float
    pit_status: int = 0
    pit_stops: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RelativePace:
    ahead_s_per_lap: float | None
    behind_s_per_lap: float | None
    ahead_confidence: float
    behind_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BattleProbabilities:
    attack: float
    defend: float
    contested: float
    clear: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DecisionEvent:
    timestamp: float
    session_time: float
    lap_number: int | None
    state: str
    target: str | None
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ModelMeta:
    name: str
    method: str
    session_uid: int | None
    sample_count: int
    effective_sample_count: int
    lap_time_estimate_s: float | None
    data_quality: float
    drs_window_s: float
    state_confidence_z: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BattleIntelligence:
    generated_at: float
    connected: bool
    state: str
    target: str | None
    target_role: str | None
    confidence: float
    decision_resolved: bool
    state_margin: float
    dominant_probability: float
    runner_up_probability: float
    window_laps: int | None
    probabilities: BattleProbabilities
    ahead: RivalModel | None
    behind: RivalModel | None
    relative_pace: RelativePace
    forecast: list[ForecastPoint] = field(default_factory=list)
    timeline: list[DecisionEvent] = field(default_factory=list)
    model: ModelMeta | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "connected": self.connected,
            "state": self.state,
            "target": self.target,
            "target_role": self.target_role,
            "confidence": self.confidence,
            "decision_resolved": self.decision_resolved,
            "state_margin": self.state_margin,
            "dominant_probability": self.dominant_probability,
            "runner_up_probability": self.runner_up_probability,
            "window_laps": self.window_laps,
            "probabilities": self.probabilities.to_dict(),
            "ahead": self.ahead.to_dict() if self.ahead else None,
            "behind": self.behind.to_dict() if self.behind else None,
            "relative_pace": self.relative_pace.to_dict(),
            "forecast": [point.to_dict() for point in self.forecast],
            "timeline": [event.to_dict() for event in self.timeline],
            "model": self.model.to_dict() if self.model else None,
        }
