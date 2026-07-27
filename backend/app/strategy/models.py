from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from time import time
from typing import Any


class BattleState(str, Enum):
    CRITICAL = "critical"
    ATTACKING = "attacking"
    DEFENDING = "defending"
    MANAGING = "managing"
    CLEAR_AIR = "clear_air"
    PIT_WINDOW = "pit_window"
    UNKNOWN = "unknown"


class BoxAction(str, Enum):
    BOX_NOW = "box_now"
    STAY_OUT = "stay_out"
    CONDITIONAL = "conditional"
    ALREADY_BOXING = "already_boxing"
    UNKNOWN = "unknown"


class EnergyAction(str, Enum):
    DEPLOY = "deploy"
    SAVE_THEN_DEPLOY = "save_then_deploy"
    DEFEND = "defend"
    HARVEST = "harvest"
    BALANCED = "balanced"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class NearbyCarAssessment:
    role: str
    name: str
    position: int | None
    gap_s: float | None
    gap_trend_s_per_lap: float | None
    relative_last_lap_s: float | None
    in_drs_range: bool
    pit_status: int = 0
    pit_stops: int = 0
    assessment: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TyreProjection:
    compound: str
    age_laps: int
    max_wear_pct: float
    average_wear_pct: float
    hottest_temp_c: float
    wear_per_lap_pct: float
    laps_remaining: int | None
    projected_finish_wear_pct: float | None
    can_finish: bool | None
    status: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BoxDecision:
    action: BoxAction
    confidence: float
    summary: str
    reason_codes: list[str] = field(default_factory=list)
    expected_rejoin_position: int | None = None
    estimated_positions_lost: int | None = None
    traffic_cars: list[str] = field(default_factory=list)
    estimated_pit_loss_s: float | None = None
    undercut_opportunity: bool = False
    overcut_opportunity: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        return data


@dataclass(slots=True)
class EnergyPlan:
    action: EnergyAction
    battery_percent: float
    target_percent: float
    minimum_reserve_percent: float
    deployment_zone: str
    summary: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        return data


@dataclass(slots=True)
class CoachingPlan:
    focus: str
    summary: str
    severity: str = "info"
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LiveRaceDecision:
    generated_at: float
    connected: bool
    battle_state: BattleState
    position: int | None
    lap_number: int | None
    total_laps: int | None
    laps_remaining: int | None
    car_ahead: NearbyCarAssessment | None
    car_behind: NearbyCarAssessment | None
    tyres: TyreProjection
    box: BoxDecision
    energy: EnergyPlan
    coaching: CoachingPlan
    data_quality: float
    reason_codes: list[str] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "LiveRaceDecision":
        return cls(
            generated_at=time(),
            connected=False,
            battle_state=BattleState.UNKNOWN,
            position=None,
            lap_number=None,
            total_laps=None,
            laps_remaining=None,
            car_ahead=None,
            car_behind=None,
            tyres=TyreProjection(
                compound="UNKNOWN",
                age_laps=0,
                max_wear_pct=0.0,
                average_wear_pct=0.0,
                hottest_temp_c=0.0,
                wear_per_lap_pct=0.0,
                laps_remaining=None,
                projected_finish_wear_pct=None,
                can_finish=None,
                status="unavailable",
                confidence=0.0,
            ),
            box=BoxDecision(
                action=BoxAction.UNKNOWN,
                confidence=0.0,
                summary="Waiting for live race telemetry.",
            ),
            energy=EnergyPlan(
                action=EnergyAction.UNKNOWN,
                battery_percent=0.0,
                target_percent=0.0,
                minimum_reserve_percent=0.0,
                deployment_zone="next long straight",
                summary="Waiting for ERS telemetry.",
                confidence=0.0,
            ),
            coaching=CoachingPlan(
                focus="collect_data",
                summary="Collecting driving data.",
                confidence=0.0,
            ),
            data_quality=0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "connected": self.connected,
            "battle_state": self.battle_state.value,
            "position": self.position,
            "lap_number": self.lap_number,
            "total_laps": self.total_laps,
            "laps_remaining": self.laps_remaining,
            "car_ahead": self.car_ahead.to_dict() if self.car_ahead else None,
            "car_behind": self.car_behind.to_dict() if self.car_behind else None,
            "tyres": self.tyres.to_dict(),
            "box": self.box.to_dict(),
            "energy": self.energy.to_dict(),
            "coaching": self.coaching.to_dict(),
            "data_quality": self.data_quality,
            "reason_codes": list(self.reason_codes),
        }
