from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import time
from typing import Any
from app.f1.constants import TYRE_COMPOUNDS

@dataclass
class EngineerMessage:
    id: int
    timestamp: float
    severity: str
    category: str
    title: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class LapSummary:
    lap_number: int
    lap_time_ms: int
    valid: bool
    timestamp: float
    position: int = 0
    tyre_compound: str = "UNKNOWN"
    tyre_age_laps: int = 0
    fuel_remaining_laps: float = 0.0
    ers_percent: float = 0.0

    @property
    def lap_time_s(self) -> float:
        return self.lap_time_ms / 1000.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["lap_time_s"] = self.lap_time_s
        return data

@dataclass
class RaceEvent:
    id: int
    timestamp: float
    session_time: float
    lap_number: int
    event_type: str
    severity: str
    title: str
    description: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class CarRaceState:
    car_index: int
    name: str
    position: int
    lap_number: int
    lap_distance_m: float
    total_distance_m: float
    current_lap_time_ms: int
    last_lap_time_ms: int
    delta_to_leader_s: float
    delta_to_car_ahead_s: float
    pit_status: int
    pit_stops: int
    grid_position: int
    driver_status: int
    result_status: int
    penalties_s: int
    team_id: int | None = None
    driver_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class LiveTelemetrySnapshot:
    connected: bool = False
    packet_count: int = 0
    last_packet_age_s: float | None = None
    packet_format: int | None = None
    game_year: int | None = None
    session_uid: int | None = None
    session_time: float = 0.0
    frame: int = 0

    speed_kph: int = 0
    throttle: float = 0.0
    brake: float = 0.0
    steer: float = 0.0
    gear: int = 0
    rpm: int = 0
    drs: bool = False
    rev_lights_percent: int = 0

    lap_number: int = 0
    total_laps: int = 0
    current_lap_time_ms: int = 0
    last_lap_time_ms: int = 0
    best_lap_time_ms: int | None = None
    lap_distance_m: float = 0.0
    total_distance_m: float = 0.0
    track_length_m: int | None = None
    track_id: int | None = None
    session_type: int | None = None

    position: int = 0
    grid_position: int = 0
    grid_size: int = 0
    positions_gained: int = 0
    sector: int = 1
    lap_invalid: bool = False
    warnings: int = 0
    penalties_s: int = 0
    pit_status: int = 0
    pit_stops: int = 0
    driver_status: int = 0
    result_status: int = 0
    delta_to_car_ahead_s: float = 0.0
    delta_to_leader_s: float = 0.0

    fuel_remaining_laps: float = 0.0
    fuel_in_tank_kg: float = 0.0
    ers_store_j: float = 0.0
    ers_percent: float = 0.0
    ers_deploy_mode: int = 0
    drs_allowed: bool = False
    drs_activation_distance_m: int = 0
    tyre_age_laps: int = 0
    tyre_compound: str = "UNKNOWN"
    front_brake_bias: int = 0
    traction_control: int = 0
    abs_enabled: bool = False

    brake_temps_c: list[int] = field(
        default_factory=lambda: [0, 0, 0, 0]
    )
    tyre_surface_temps_c: list[int] = field(
        default_factory=lambda: [0, 0, 0, 0]
    )
    tyre_inner_temps_c: list[int] = field(
        default_factory=lambda: [0, 0, 0, 0]
    )
    tyre_pressures_psi: list[float] = field(
        default_factory=lambda: [0.0, 0.0, 0.0, 0.0]
    )
    tyre_wear_pct: list[float] = field(
        default_factory=lambda: [0.0, 0.0, 0.0, 0.0]
    )
    tyre_damage_pct: list[int] = field(
        default_factory=lambda: [0, 0, 0, 0]
    )
    wing_damage_pct: dict[str, int] = field(
        default_factory=lambda: {
            "fl": 0,
            "fr": 0,
            "rear": 0,
        }
    )

    world_position: list[float] = field(
        default_factory=lambda: [0.0, 0.0, 0.0]
    )
    world_velocity: list[float] = field(
        default_factory=lambda: [0.0, 0.0, 0.0]
    )
    g_force_lateral: float = 0.0
    g_force_longitudinal: float = 0.0

    player_name: str = "YOU"
    car_ahead: dict[str, Any] | None = None
    car_behind: dict[str, Any] | None = None
    leader: dict[str, Any] | None = None
    classification: list[dict[str, Any]] = field(default_factory=list)

    active_session_id: str | None = None
    recording_enabled: bool = False

    completed_laps: list[dict[str, Any]] = field(default_factory=list)
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    race_events: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    track_points: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def compound_name(value: int) -> str:
    return TYRE_COMPOUNDS.get(value, f"ID-{value}")

def now() -> float:
    return time()