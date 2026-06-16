from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any
from app.telemetry.models import LiveTelemetrySnapshot, EngineerMessage
from app.telemetry.state import LiveTelemetryState

@dataclass
class RuleResult:
    key: str
    severity: str
    category: str
    title: str
    message: str
    evidence: dict[str, Any]
    cooldown_s: float = 20.0
    radio: str | None = None
    priority: int = 50
    voice_cooldown_s: float | None = None
    can_voice: bool = True

class CoachingRuleEngine:
    """Rule-based coaching engine.
    The dashboard can show detail, but the radio receives short radio lines
    and longer cooldowns so it does not spam the driver while racing
    """

    def __init__(self, state: LiveTelemetryState) -> None:
        self.state = state
        self.enabled = True
        self._last_fired: dict[str, float] = {}
        self._previous_lap_number: int | None = None
        self._previous_best: int | None = None
        self._previous_invalid = False

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def analyze(self, snapshot: LiveTelemetrySnapshot) -> list[EngineerMessage]:
        if not self.enabled or not snapshot.connected:
            return []

        results: list[RuleResult] = []
        results.extend(self._driving_input_rules(snapshot))
        results.extend(self._car_health_rules(snapshot))
        results.extend(self._race_management_rules(snapshot))
        results.extend(self._lap_event_rules(snapshot))

        out: list[EngineerMessage] = []
        now_ts = time()

        # Highest priority messages should appear first when several rules fire together.
        results.sort(key=lambda item: item.priority, reverse=True)

        for result in results:
            last = self._last_fired.get(result.key, 0.0)
            if now_ts - last < result.cooldown_s:
                continue

            self._last_fired[result.key] = now_ts
            evidence = dict(result.evidence)
            evidence["radio"] = result.radio or result.title
            evidence["priority"] = result.priority
            evidence["can_voice"] = result.can_voice
            evidence["voice_cooldown_s"] = result.voice_cooldown_s if result.voice_cooldown_s is not None else max(result.cooldown_s, 20.0)
            evidence["voice_key"] = result.key

            out.append(
                self.state.add_message(
                    severity=result.severity,
                    category=result.category,
                    title=result.title,
                    message=result.message,
                    evidence=evidence,
                )
            )

        return out

    def _driving_input_rules(self, s: LiveTelemetrySnapshot) -> list[RuleResult]:
        r: list[RuleResult] = []
        abs_steer = abs(s.steer)

        if 55 < s.speed_kph < 220 and abs_steer > 0.30 and s.throttle > 0.82:
            r.append(RuleResult(
                key="aggressive_throttle_exit",
                severity="warning",
                category="inputs",
                title="Throttle too early",
                message="Throttle is high while the steering wheel is still loaded. Feed the throttle in later and more progressively on exit.",
                radio="Easy throttle.",
                evidence={"throttle": round(s.throttle, 2), "steer": round(s.steer, 2), "speed_kph": s.speed_kph},
                cooldown_s=18,
                voice_cooldown_s=28,
                priority=72,
            ))

        if s.brake > 0.35 and s.throttle > 0.18 and s.speed_kph > 80:
            r.append(RuleResult(
                key="brake_throttle_overlap",
                severity="info",
                category="inputs",
                title="Brake and throttle overlap",
                message="Brake and throttle are overlapping. Separate the pedals to keep the car stable and protect tyre temperature.",
                radio="Brake and throttle overlap.",
                evidence={"brake": round(s.brake, 2), "throttle": round(s.throttle, 2), "speed_kph": s.speed_kph},
                cooldown_s=20,
                voice_cooldown_s=30,
                priority=68,
            ))

        if s.brake > 0.88 and s.speed_kph < 135 and abs_steer > 0.24:
            r.append(RuleResult(
                key="trail_brake_release",
                severity="info",
                category="braking",
                title="Release brake earlier",
                message="Brake pressure is still very high at low speed with steering applied. Bleed off the brake earlier before apex.",
                radio="Release the brake.",
                evidence={"brake": round(s.brake, 2), "steer": round(s.steer, 2), "speed_kph": s.speed_kph},
                cooldown_s=20,
                voice_cooldown_s=32,
                priority=70,
            ))

        if s.g_force_longitudinal < -3.2 and s.speed_kph < 150 and abs_steer > 0.22:
            r.append(RuleResult(
                key="peak_brake_too_late",
                severity="info",
                category="braking",
                title="Peak brake too late",
                message="You are carrying a big braking load into the corner phase. Move peak brake pressure earlier and trail off sooner.",
                radio="Peak brake earlier.",
                evidence={"longitudinal_g": round(s.g_force_longitudinal, 2), "steer": round(s.steer, 2), "speed_kph": s.speed_kph},
                cooldown_s=24,
                voice_cooldown_s=38,
                priority=66,
            ))

        return r

    def _car_health_rules(self, s: LiveTelemetrySnapshot) -> list[RuleResult]:
        r: list[RuleResult] = []
        rear_temps = s.tyre_surface_temps_c[0:2]
        front_temps = s.tyre_surface_temps_c[2:4]
        rear_max = max(rear_temps) if rear_temps else 0
        front_max = max(front_temps) if front_temps else 0
        brake_max = max(s.brake_temps_c) if s.brake_temps_c else 0
        wear_max = max(s.tyre_wear_pct) if s.tyre_wear_pct else 0

        if rear_max >= 106:
            r.append(RuleResult(
                key="rear_tyre_hot",
                severity="warning",
                category="tyres",
                title="Rear tyres hot",
                message="Rear tyre surface temperatures are high. Reduce wheelspin and avoid sharp throttle on exits.",
                radio="Rear tyres are hot.",
                evidence={"rear_surface_temps_c": rear_temps},
                cooldown_s=32,
                voice_cooldown_s=45,
                priority=75,
            ))

        if front_max >= 108:
            r.append(RuleResult(
                key="front_tyre_hot",
                severity="warning",
                category="tyres",
                title="Front tyres hot",
                message="Front tyre surface temperatures are high. Reduce entry sliding and avoid over-rotating the car.",
                radio="Fronts are hot.",
                evidence={"front_surface_temps_c": front_temps},
                cooldown_s=32,
                voice_cooldown_s=45,
                priority=74,
            ))

        if brake_max >= 980:
            r.append(RuleResult(
                key="brakes_hot",
                severity="danger",
                category="brakes",
                title="Brake temperatures high",
                message="Brake temperatures are very high. Open up braking zones and avoid dragging the brake.",
                radio="Brake temps high.",
                evidence={"brake_temps_c": s.brake_temps_c},
                cooldown_s=30,
                voice_cooldown_s=45,
                priority=92,
            ))

        if wear_max >= 65:
            r.append(RuleResult(
                key="tyre_wear_high",
                severity="danger",
                category="tyres",
                title="Tyre wear critical",
                message="Tyre wear is critical. Prioritise clean exits and consider boxing soon.",
                radio="Tyre wear critical.",
                evidence={"tyre_wear_pct": [round(x, 1) for x in s.tyre_wear_pct]},
                cooldown_s=40,
                voice_cooldown_s=60,
                priority=94,
            ))

        return r

    def _race_management_rules(self, s: LiveTelemetrySnapshot) -> list[RuleResult]:
        r: list[RuleResult] = []

        if 0 < s.ers_percent < 12 and s.speed_kph > 120:
            r.append(RuleResult(
                key="ers_low",
                severity="info",
                category="ers",
                title="ERS low",
                message="ERS battery is low. Harvest this lap and avoid unnecessary deployment.",
                radio="Recharge ERS.",
                evidence={"ers_percent": round(s.ers_percent, 1)},
                cooldown_s=40,
                voice_cooldown_s=60,
                priority=58,
            ))

        if s.fuel_remaining_laps < -0.2:
            r.append(RuleResult(
                key="fuel_negative",
                severity="warning",
                category="fuel",
                title="Fuel below target",
                message="Fuel is below target. Lift and coast into heavy braking zones.",
                radio="Fuel target negative.",
                evidence={"fuel_remaining_laps": round(s.fuel_remaining_laps, 2)},
                cooldown_s=35,
                voice_cooldown_s=55,
                priority=78,
            ))

        if s.drs_allowed and not s.drs and s.speed_kph > 180:
            r.append(RuleResult(
                key="drs_available",
                severity="info",
                category="drs",
                title="DRS available",
                message="DRS is available on the straight.",
                radio="DRS available.",
                evidence={"drs_activation_distance_m": s.drs_activation_distance_m},
                cooldown_s=20,
                can_voice=False,
                priority=25,
            ))

        return r

    def _lap_event_rules(self, s: LiveTelemetrySnapshot) -> list[RuleResult]:
        r: list[RuleResult] = []

        if s.lap_invalid and not self._previous_invalid:
            r.append(RuleResult(
                key=f"lap_invalid_{s.lap_number}",
                severity="warning",
                category="race_control",
                title="Lap invalidated",
                message="Lap invalidated. Reset and focus on exit precision next lap.",
                radio="Lap deleted.",
                evidence={"lap_number": s.lap_number, "warnings": s.warnings},
                cooldown_s=1,
                voice_cooldown_s=3,
                priority=88,
            ))
        self._previous_invalid = s.lap_invalid

        if self._previous_lap_number is not None and s.lap_number > self._previous_lap_number:
            if s.last_lap_time_ms > 0:
                lap_s = s.last_lap_time_ms / 1000.0
                if s.best_lap_time_ms == s.last_lap_time_ms:
                    r.append(RuleResult(
                        key=f"new_pb_{s.lap_number}",
                        severity="success",
                        category="lap_time",
                        title="New personal best",
                        message=f"New personal best: {lap_s:.3f} seconds.",
                        radio=f"New personal best. {lap_s:.3f}.",
                        evidence={"last_lap_time_ms": s.last_lap_time_ms},
                        cooldown_s=1,
                        voice_cooldown_s=1,
                        priority=86,
                    ))
                elif s.best_lap_time_ms:
                    delta = (s.last_lap_time_ms - s.best_lap_time_ms) / 1000.0
                    r.append(RuleResult(
                        key=f"lap_complete_{s.lap_number}",
                        severity="info",
                        category="lap_time",
                        title="Lap complete",
                        message=f"Lap complete. You were {delta:.3f} seconds off your current best.",
                        radio=f"Lap complete. Plus {delta:.3f}.",
                        evidence={"delta_to_pb_s": round(delta, 3)},
                        cooldown_s=1,
                        voice_cooldown_s=1,
                        priority=55,
                    ))

        self._previous_lap_number = s.lap_number
        self._previous_best = s.best_lap_time_ms
        return r