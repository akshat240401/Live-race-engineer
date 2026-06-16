from __future__ import annotations

from collections import deque
from math import hypot, isfinite
from threading import Lock
from time import time
from typing import Any
from app.f1.packets import ParsedPacket
from app.telemetry.models import LiveTelemetrySnapshot, EngineerMessage, LapSummary, compound_name

class LiveTelemetryState:
    def __init__(self, history_limit: int = 600) -> None:
        self._lock = Lock()
        self._snapshot = LiveTelemetrySnapshot()
        self._history: deque[dict[str, Any]] = deque(maxlen=history_limit)
        self._track_points: deque[dict[str, Any]] = deque(maxlen=3500)
        self._messages: deque[dict[str, Any]] = deque(maxlen=80)
        self._completed_laps: deque[dict[str, Any]] = deque(maxlen=100)
        self._last_packet_ts: float | None = None
        self._last_lap_number: int | None = None
        self._message_id = 0
        self._last_track_point: dict[str, Any] | None = None
        self._last_track_lap: int | None = None

    def reset(self) -> None:
        with self._lock:
            self._snapshot = LiveTelemetrySnapshot()
            self._history.clear()
            self._track_points.clear()
            self._messages.clear()
            self._completed_laps.clear()
            self._last_packet_ts = None
            self._last_lap_number = None
            self._message_id = 0
            self._last_track_point = None
            self._last_track_lap = None

    def add_message(self, severity: str, category: str, title: str, message: str, evidence: dict[str, Any] | None = None) -> EngineerMessage:
        with self._lock:
            self._message_id += 1
            msg = EngineerMessage(
                id=self._message_id,
                timestamp=time(),
                severity=severity,
                category=category,
                title=title,
                message=message,
                evidence=evidence or {},
            )
            d = msg.to_dict()
            self._messages.appendleft(d)
            self._snapshot.recent_messages = list(self._messages)
            return msg

    def apply_packet(self, parsed: ParsedPacket) -> LiveTelemetrySnapshot:
        with self._lock:
            s = self._snapshot
            s.connected = True
            s.packet_count += 1
            self._last_packet_ts = time()
            s.packet_format = parsed.header.packet_format
            s.game_year = parsed.header.game_year
            s.session_time = parsed.header.session_time
            s.frame = parsed.header.overall_frame_identifier

            p = parsed.player
            if parsed.kind == "car_telemetry":
                s.speed_kph = int(p.get("speed_kph", s.speed_kph))
                s.throttle = float(p.get("throttle", s.throttle))
                s.brake = float(p.get("brake", s.brake))
                s.steer = float(p.get("steer", s.steer))
                s.gear = int(p.get("gear", s.gear))
                s.rpm = int(p.get("rpm", s.rpm))
                s.drs = bool(p.get("drs", s.drs))
                s.rev_lights_percent = int(p.get("rev_lights_percent", s.rev_lights_percent))
                s.brake_temps_c = list(p.get("brake_temps_c", s.brake_temps_c))
                s.tyre_surface_temps_c = list(p.get("tyre_surface_temps_c", s.tyre_surface_temps_c))
                s.tyre_inner_temps_c = list(p.get("tyre_inner_temps_c", s.tyre_inner_temps_c))
                s.tyre_pressures_psi = list(p.get("tyre_pressures_psi", s.tyre_pressures_psi))

            elif parsed.kind == "lap_data":
                old_lap = s.lap_number
                s.last_lap_time_ms = int(p.get("last_lap_time_ms", s.last_lap_time_ms))
                s.current_lap_time_ms = int(p.get("current_lap_time_ms", s.current_lap_time_ms))
                s.lap_distance_m = float(p.get("lap_distance_m", s.lap_distance_m))
                s.position = int(p.get("position", s.position))
                s.lap_number = int(p.get("lap_number", s.lap_number))
                s.sector = int(p.get("sector", s.sector))
                s.lap_invalid = bool(p.get("lap_invalid", s.lap_invalid))
                s.penalties_s = int(p.get("penalties_s", s.penalties_s))
                s.warnings = int(p.get("warnings", s.warnings))

                if old_lap and s.lap_number > old_lap and s.last_lap_time_ms > 0:
                    lap = LapSummary(
                        lap_number=old_lap,
                        lap_time_ms=s.last_lap_time_ms,
                        valid=not s.lap_invalid,
                        timestamp=time(),
                    ).to_dict()
                    self._completed_laps.appendleft(lap)
                    s.completed_laps = list(self._completed_laps)
                    if not s.lap_invalid and (s.best_lap_time_ms is None or s.last_lap_time_ms < s.best_lap_time_ms):
                        s.best_lap_time_ms = s.last_lap_time_ms

            elif parsed.kind == "car_status":
                s.fuel_remaining_laps = float(p.get("fuel_remaining_laps", s.fuel_remaining_laps))
                s.fuel_in_tank_kg = float(p.get("fuel_in_tank_kg", s.fuel_in_tank_kg))
                s.ers_store_j = float(p.get("ers_store_j", s.ers_store_j))
                s.ers_percent = max(0.0, min(100.0, s.ers_store_j / 4_000_000.0 * 100.0))
                s.ers_deploy_mode = int(p.get("ers_deploy_mode", s.ers_deploy_mode))
                s.drs_allowed = bool(p.get("drs_allowed", s.drs_allowed))
                s.drs_activation_distance_m = int(p.get("drs_activation_distance_m", s.drs_activation_distance_m))
                s.tyre_age_laps = int(p.get("tyre_age_laps", s.tyre_age_laps))
                s.tyre_compound = compound_name(int(p.get("visual_tyre_compound", 0)))
                s.front_brake_bias = int(p.get("front_brake_bias", s.front_brake_bias))
                s.traction_control = int(p.get("traction_control", s.traction_control))
                s.abs_enabled = bool(p.get("anti_lock_brakes", s.abs_enabled))

            elif parsed.kind == "car_damage":
                s.tyre_wear_pct = list(p.get("tyre_wear_pct", s.tyre_wear_pct))
                s.tyre_damage_pct = list(p.get("tyre_damage_pct", s.tyre_damage_pct))
                s.wing_damage_pct = {
                    "fl": int(p.get("front_left_wing_damage_pct", s.wing_damage_pct["fl"])),
                    "fr": int(p.get("front_right_wing_damage_pct", s.wing_damage_pct["fr"])),
                    "rear": int(p.get("rear_wing_damage_pct", s.wing_damage_pct["rear"])),
                }

            elif parsed.kind == "motion":
                s.world_position = list(p.get("world_position", s.world_position))
                s.world_velocity = list(p.get("world_velocity", s.world_velocity))
                s.g_force_lateral = float(p.get("g_force_lateral", s.g_force_lateral))
                s.g_force_longitudinal = float(p.get("g_force_longitudinal", s.g_force_longitudinal))
                self._append_track_point_locked()

            elif parsed.kind == "session":
                s.track_length_m = int(p.get("track_length_m", s.track_length_m or 0)) or s.track_length_m
                s.track_id = int(p.get("track_id", s.track_id or 0)) if p.get("track_id", None) is not None else s.track_id

            self._append_history_locked()
            return self._copy_snapshot_locked()

    def _append_history_locked(self) -> None:
        s = self._snapshot
        item = {
            "t": time(),
            "session_time": s.session_time,
            "speed_kph": s.speed_kph,
            "throttle": s.throttle,
            "brake": s.brake,
            "steer": s.steer,
            "gear": s.gear,
            "rpm": s.rpm,
            "lap_distance_m": s.lap_distance_m,
            "lap_number": s.lap_number,
            "ers_percent": s.ers_percent,
            "fuel_remaining_laps": s.fuel_remaining_laps,
            "world_position": list(s.world_position),
            "world_velocity": list(s.world_velocity),
            "g_force_lateral": s.g_force_lateral,
            "g_force_longitudinal": s.g_force_longitudinal,
        }
        if not self._history or item["session_time"] != self._history[-1].get("session_time"):
            self._history.append(item)

    def _append_track_point_locked(self) -> None:
        s = self._snapshot
        if len(s.world_position) < 3:
            return

        x = float(s.world_position[0])
        y = float(s.world_position[1])
        z = float(s.world_position[2])

        if not all(isfinite(v) for v in (x, y, z)):
            return

        # Ignore placeholder zeros before the game sends useful motion packets.
        if abs(x) < 0.001 and abs(z) < 0.001 and s.speed_kph == 0:
            return

        lap = int(s.lap_number or 0)
        if self._last_track_lap is not None and lap > self._last_track_lap:
            # Keep the built map, but allow immediate point capture on a new lap.
            self._last_track_point = None
        self._last_track_lap = lap

        point = {
            "t": time(),
            "session_time": s.session_time,
            "lap_number": s.lap_number,
            "lap_distance_m": s.lap_distance_m,
            "x": x,
            "y": y,
            "z": z,
            "speed_kph": s.speed_kph,
        }

        if self._last_track_point is not None:
            dx = x - float(self._last_track_point["x"])
            dz = z - float(self._last_track_point["z"])
            moved_m = hypot(dx, dz)
            distance_delta = abs(s.lap_distance_m - float(self._last_track_point.get("lap_distance_m", s.lap_distance_m)))
            if moved_m < 3.0 and distance_delta < 3.0:
                return

        self._track_points.append(point)
        self._last_track_point = point

    def _copy_snapshot_locked(self) -> LiveTelemetrySnapshot:
        s = self._snapshot
        if self._last_packet_ts is not None:
            s.last_packet_age_s = time() - self._last_packet_ts
            s.connected = s.last_packet_age_s < 2.5
        s.history = list(self._history)[-260:]
        s.track_points = list(self._track_points)
        s.recent_messages = list(self._messages)
        s.completed_laps = list(self._completed_laps)
        return LiveTelemetrySnapshot(**s.to_dict())

    def snapshot(self) -> LiveTelemetrySnapshot:
        with self._lock:
            return self._copy_snapshot_locked()

    def messages(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._messages)