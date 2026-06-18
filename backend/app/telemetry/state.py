from __future__ import annotations

from collections import deque
from copy import deepcopy
from math import hypot, isfinite
from threading import Lock
from time import time
from typing import Any

from app.f1.packets import ParsedPacket
from app.telemetry.models import (
    CarRaceState,
    EngineerMessage,
    LapSummary,
    LiveTelemetrySnapshot,
    RaceEvent,
    compound_name,
)

class LiveTelemetryState:
    def __init__(
        self,
        history_limit: int = 9000,
    ) -> None:
        self._lock = Lock()
        self._snapshot = LiveTelemetrySnapshot()

        self._history: deque[dict[str, Any]] = deque(
            maxlen=history_limit
        )
        self._track_points: deque[dict[str, Any]] = deque(
            maxlen=5000
        )
        self._messages: deque[dict[str, Any]] = deque(
            maxlen=100
        )
        self._race_events: deque[dict[str, Any]] = deque(
            maxlen=250
        )
        self._completed_laps: deque[
            dict[str, Any]
        ] = deque(maxlen=200)

        self._participants: dict[
            int,
            dict[str, Any],
        ] = {}

        self._latest_lap_data: dict[
            int,
            dict[str, Any],
        ] = {}

        self._last_packet_ts: float | None = None
        self._message_id = 0
        self._event_id = 0
        self._last_track_point: dict[str, Any] | None = None
        self._last_position: int | None = None
        self._last_damage_total = 0
        self._last_speed_sample: tuple[
            float,
            int,
        ] | None = None
        self._last_incident_ts = 0.0
        self._last_event_signature: dict[str, float] = {}

    def reset(self) -> None:
        with self._lock:
            self._snapshot = LiveTelemetrySnapshot()
            self._history.clear()
            self._track_points.clear()
            self._messages.clear()
            self._race_events.clear()
            self._completed_laps.clear()
            self._participants.clear()
            self._latest_lap_data.clear()

            self._last_packet_ts = None
            self._message_id = 0
            self._event_id = 0
            self._last_track_point = None
            self._last_position = None
            self._last_damage_total = 0
            self._last_speed_sample = None
            self._last_incident_ts = 0.0
            self._last_event_signature.clear()

    def set_recording_state(
        self,
        session_id: str | None,
        enabled: bool,
    ) -> None:
        with self._lock:
            self._snapshot.active_session_id = session_id
            self._snapshot.recording_enabled = enabled

    def add_message(
        self,
        severity: str,
        category: str,
        title: str,
        message: str,
        evidence: dict[str, Any] | None = None,
    ) -> EngineerMessage:
        with self._lock:
            self._message_id += 1

            result = EngineerMessage(
                id=self._message_id,
                timestamp=time(),
                severity=severity,
                category=category,
                title=title,
                message=message,
                evidence=evidence or {},
            )

            data = result.to_dict()
            self._messages.appendleft(data)
            self._snapshot.recent_messages = list(
                self._messages
            )

            return result

    def apply_packet(
        self,
        parsed: ParsedPacket,
    ) -> LiveTelemetrySnapshot:
        with self._lock:
            snapshot = self._snapshot

            snapshot.connected = True
            snapshot.packet_count += 1
            self._last_packet_ts = time()

            snapshot.packet_format = (
                parsed.header.packet_format
            )
            snapshot.game_year = (
                parsed.header.game_year
            )
            snapshot.session_uid = (
                parsed.header.session_uid
            )
            snapshot.session_time = (
                parsed.header.session_time
            )
            snapshot.frame = (
                parsed.header.overall_frame_identifier
            )

            player = parsed.player

            if parsed.kind == "car_telemetry":
                snapshot.speed_kph = int(
                    player.get(
                        "speed_kph",
                        snapshot.speed_kph,
                    )
                )
                snapshot.throttle = float(
                    player.get(
                        "throttle",
                        snapshot.throttle,
                    )
                )
                snapshot.brake = float(
                    player.get(
                        "brake",
                        snapshot.brake,
                    )
                )
                snapshot.steer = float(
                    player.get(
                        "steer",
                        snapshot.steer,
                    )
                )
                snapshot.gear = int(
                    player.get(
                        "gear",
                        snapshot.gear,
                    )
                )
                snapshot.rpm = int(
                    player.get(
                        "rpm",
                        snapshot.rpm,
                    )
                )
                snapshot.drs = bool(
                    player.get(
                        "drs",
                        snapshot.drs,
                    )
                )
                snapshot.rev_lights_percent = int(
                    player.get(
                        "rev_lights_percent",
                        snapshot.rev_lights_percent,
                    )
                )
                snapshot.brake_temps_c = list(
                    player.get(
                        "brake_temps_c",
                        snapshot.brake_temps_c,
                    )
                )
                snapshot.tyre_surface_temps_c = list(
                    player.get(
                        "tyre_surface_temps_c",
                        snapshot.tyre_surface_temps_c,
                    )
                )
                snapshot.tyre_inner_temps_c = list(
                    player.get(
                        "tyre_inner_temps_c",
                        snapshot.tyre_inner_temps_c,
                    )
                )
                snapshot.tyre_pressures_psi = list(
                    player.get(
                        "tyre_pressures_psi",
                        snapshot.tyre_pressures_psi,
                    )
                )

                self._detect_sudden_stop_locked()

            elif parsed.kind == "lap_data":
                self._apply_lap_data_locked(parsed)

            elif parsed.kind == "car_status":
                snapshot.fuel_remaining_laps = float(
                    player.get(
                        "fuel_remaining_laps",
                        snapshot.fuel_remaining_laps,
                    )
                )
                snapshot.fuel_in_tank_kg = float(
                    player.get(
                        "fuel_in_tank_kg",
                        snapshot.fuel_in_tank_kg,
                    )
                )
                snapshot.ers_store_j = float(
                    player.get(
                        "ers_store_j",
                        snapshot.ers_store_j,
                    )
                )
                snapshot.ers_percent = max(
                    0.0,
                    min(
                        100.0,
                        snapshot.ers_store_j
                        / 4_000_000.0
                        * 100.0,
                    ),
                )
                snapshot.ers_deploy_mode = int(
                    player.get(
                        "ers_deploy_mode",
                        snapshot.ers_deploy_mode,
                    )
                )
                snapshot.drs_allowed = bool(
                    player.get(
                        "drs_allowed",
                        snapshot.drs_allowed,
                    )
                )
                snapshot.drs_activation_distance_m = int(
                    player.get(
                        "drs_activation_distance_m",
                        snapshot.drs_activation_distance_m,
                    )
                )
                snapshot.tyre_age_laps = int(
                    player.get(
                        "tyre_age_laps",
                        snapshot.tyre_age_laps,
                    )
                )
                snapshot.tyre_compound = compound_name(
                    int(
                        player.get(
                            "visual_tyre_compound",
                            0,
                        )
                    )
                )
                snapshot.front_brake_bias = int(
                    player.get(
                        "front_brake_bias",
                        snapshot.front_brake_bias,
                    )
                )
                snapshot.traction_control = int(
                    player.get(
                        "traction_control",
                        snapshot.traction_control,
                    )
                )
                snapshot.abs_enabled = bool(
                    player.get(
                        "anti_lock_brakes",
                        snapshot.abs_enabled,
                    )
                )

            elif parsed.kind == "car_damage":
                snapshot.tyre_wear_pct = list(
                    player.get(
                        "tyre_wear_pct",
                        snapshot.tyre_wear_pct,
                    )
                )
                snapshot.tyre_damage_pct = list(
                    player.get(
                        "tyre_damage_pct",
                        snapshot.tyre_damage_pct,
                    )
                )
                snapshot.wing_damage_pct = {
                    "fl": int(
                        player.get(
                            "front_left_wing_damage_pct",
                            snapshot.wing_damage_pct["fl"],
                        )
                    ),
                    "fr": int(
                        player.get(
                            "front_right_wing_damage_pct",
                            snapshot.wing_damage_pct["fr"],
                        )
                    ),
                    "rear": int(
                        player.get(
                            "rear_wing_damage_pct",
                            snapshot.wing_damage_pct["rear"],
                        )
                    ),
                }

                self._detect_damage_change_locked()

            elif parsed.kind == "motion":
                snapshot.world_position = list(
                    player.get(
                        "world_position",
                        snapshot.world_position,
                    )
                )
                snapshot.world_velocity = list(
                    player.get(
                        "world_velocity",
                        snapshot.world_velocity,
                    )
                )
                snapshot.g_force_lateral = float(
                    player.get(
                        "g_force_lateral",
                        snapshot.g_force_lateral,
                    )
                )
                snapshot.g_force_longitudinal = float(
                    player.get(
                        "g_force_longitudinal",
                        snapshot.g_force_longitudinal,
                    )
                )

                self._append_track_point_locked()

            elif parsed.kind == "session":
                snapshot.total_laps = int(
                    player.get(
                        "total_laps",
                        snapshot.total_laps,
                    )
                )

                track_length = int(
                    player.get(
                        "track_length_m",
                        snapshot.track_length_m or 0,
                    )
                )
                if track_length > 0:
                    snapshot.track_length_m = track_length

                if player.get("track_id") is not None:
                    snapshot.track_id = int(
                        player["track_id"]
                    )

                snapshot.session_type = int(
                    player.get(
                        "session_type",
                        snapshot.session_type or 0,
                    )
                )

            elif parsed.kind == "participants":
                self._apply_participants_locked(parsed)

            elif (
                parsed.kind == "event"
                and parsed.event
            ):
                self._apply_game_event_locked(
                    parsed.event,
                    parsed.header.player_car_index,
                )

            elif (
                parsed.kind
                == "final_classification"
            ):
                self._apply_final_classification_locked(
                    parsed
                )

            self._append_history_locked()

            return self._copy_snapshot_locked()

    def _apply_lap_data_locked(
        self,
        parsed: ParsedPacket,
    ) -> None:
        snapshot = self._snapshot
        player_index = parsed.header.player_car_index

        old_lap = snapshot.lap_number
        old_position = snapshot.position

        self._latest_lap_data = {
            int(car.get("car_index", index)): car
            for index, car in enumerate(parsed.cars)
        }

        player = parsed.player

        snapshot.last_lap_time_ms = int(
            player.get(
                "last_lap_time_ms",
                snapshot.last_lap_time_ms,
            )
        )
        snapshot.current_lap_time_ms = int(
            player.get(
                "current_lap_time_ms",
                snapshot.current_lap_time_ms,
            )
        )
        snapshot.lap_distance_m = float(
            player.get(
                "lap_distance_m",
                snapshot.lap_distance_m,
            )
        )
        snapshot.total_distance_m = float(
            player.get(
                "total_distance_m",
                snapshot.total_distance_m,
            )
        )
        snapshot.position = int(
            player.get(
                "position",
                snapshot.position,
            )
        )
        snapshot.grid_position = int(
            player.get(
                "grid_position",
                snapshot.grid_position,
            )
        )
        snapshot.lap_number = int(
            player.get(
                "lap_number",
                snapshot.lap_number,
            )
        )
        snapshot.sector = int(
            player.get(
                "sector",
                snapshot.sector,
            )
        )
        snapshot.lap_invalid = bool(
            player.get(
                "lap_invalid",
                snapshot.lap_invalid,
            )
        )
        snapshot.penalties_s = int(
            player.get(
                "penalties_s",
                snapshot.penalties_s,
            )
        )
        snapshot.warnings = int(
            player.get(
                "warnings",
                snapshot.warnings,
            )
        )
        snapshot.pit_status = int(
            player.get(
                "pit_status",
                snapshot.pit_status,
            )
        )
        snapshot.pit_stops = int(
            player.get(
                "pit_stops",
                snapshot.pit_stops,
            )
        )
        snapshot.driver_status = int(
            player.get(
                "driver_status",
                snapshot.driver_status,
            )
        )
        snapshot.result_status = int(
            player.get(
                "result_status",
                snapshot.result_status,
            )
        )
        snapshot.delta_to_car_ahead_s = float(
            player.get(
                "delta_to_car_ahead_s",
                snapshot.delta_to_car_ahead_s,
            )
        )
        snapshot.delta_to_leader_s = float(
            player.get(
                "delta_to_leader_s",
                snapshot.delta_to_leader_s,
            )
        )

        valid_cars = [
            car
            for car in parsed.cars
            if int(car.get("position", 0)) > 0
        ]

        snapshot.grid_size = len(valid_cars)

        self._update_classification_locked(
            player_index
        )

        if (
            snapshot.grid_position > 0
            and snapshot.position > 0
        ):
            snapshot.positions_gained = (
                snapshot.grid_position
                - snapshot.position
            )

        if (
            old_lap > 0
            and snapshot.lap_number > old_lap
            and snapshot.last_lap_time_ms > 0
        ):
            valid = not snapshot.lap_invalid

            lap = LapSummary(
                lap_number=old_lap,
                lap_time_ms=(
                    snapshot.last_lap_time_ms
                ),
                valid=valid,
                timestamp=time(),
                position=snapshot.position,
                tyre_compound=(
                    snapshot.tyre_compound
                ),
                tyre_age_laps=(
                    snapshot.tyre_age_laps
                ),
                fuel_remaining_laps=(
                    snapshot.fuel_remaining_laps
                ),
                ers_percent=(
                    snapshot.ers_percent
                ),
            ).to_dict()

            self._completed_laps.appendleft(lap)

            snapshot.completed_laps = list(
                self._completed_laps
            )

            if (
                valid
                and (
                    snapshot.best_lap_time_ms is None
                    or (
                        snapshot.last_lap_time_ms
                        < snapshot.best_lap_time_ms
                    )
                )
            ):
                snapshot.best_lap_time_ms = (
                    snapshot.last_lap_time_ms
                )

            self._add_event_locked(
                "lap_completed",
                "info",
                f"Lap {old_lap} completed",
                (
                    f"Completed lap {old_lap} in "
                    f"{snapshot.last_lap_time_ms / 1000.0:.3f} seconds."
                ),
                {"lap": lap},
                signature=f"lap:{old_lap}",
            )

        if (
            old_position > 0
            and snapshot.position > 0
            and old_position != snapshot.position
        ):
            self._record_position_change_locked(
                old_position,
                snapshot.position,
            )

        elif (
            self._last_position is not None
            and snapshot.position > 0
            and (
                self._last_position
                != snapshot.position
            )
        ):
            self._record_position_change_locked(
                self._last_position,
                snapshot.position,
            )

        if snapshot.position > 0:
            self._last_position = snapshot.position

    def _apply_participants_locked(
        self,
        parsed: ParsedPacket,
    ) -> None:
        for participant in parsed.cars:
            index = int(
                participant.get("car_index", -1)
            )

            if index >= 0:
                self._participants[index] = dict(
                    participant
                )

        player = self._participants.get(
            parsed.header.player_car_index
        )

        if player:
            self._snapshot.player_name = str(
                player.get("name") or "YOU"
            )

        self._update_classification_locked(
            parsed.header.player_car_index
        )

    def _apply_final_classification_locked(
        self,
        parsed: ParsedPacket,
    ) -> None:
        snapshot = self._snapshot
        rows: list[dict[str, Any]] = []

        for car in parsed.cars:
            index = int(
                car.get("car_index", -1)
            )
            participant = self._participants.get(
                index,
                {},
            )

            row = {
                **car,
                "name": participant.get(
                    "name",
                    f"Car {index + 1}",
                ),
            }

            rows.append(row)

        rows.sort(
            key=lambda item: int(
                item.get("position", 999)
            )
        )

        if rows:
            snapshot.classification = rows
            snapshot.grid_size = len(rows)

        player_index = (
            parsed.header.player_car_index
        )

        player = next(
            (
                row
                for row in rows
                if int(
                    row.get("car_index", -1)
                )
                == player_index
            ),
            None,
        )

        if player:
            snapshot.position = int(
                player.get(
                    "position",
                    snapshot.position,
                )
            )
            snapshot.result_status = int(
                player.get(
                    "result_status",
                    snapshot.result_status,
                )
            )
            snapshot.pit_stops = int(
                player.get(
                    "num_pit_stops",
                    snapshot.pit_stops,
                )
            )
            snapshot.penalties_s = int(
                player.get(
                    "penalties_s",
                    snapshot.penalties_s,
                )
            )

            best_lap = int(
                player.get(
                    "best_lap_time_ms",
                    0,
                )
            )

            if best_lap > 0:
                snapshot.best_lap_time_ms = (
                    best_lap
                )

        self._add_event_locked(
            "session_finished",
            "success",
            "Session finished",
            (
                "Final classification received. "
                f"Finished P{snapshot.position or '--'}."
            ),
            {"classification": rows},
            signature="session_finished",
        )

    def _update_classification_locked(
        self,
        player_index: int,
    ) -> None:
        rows: list[dict[str, Any]] = []

        for index, lap in (
            self._latest_lap_data.items()
        ):
            position = int(
                lap.get("position", 0)
            )

            if position <= 0:
                continue

            participant = self._participants.get(
                index,
                {},
            )

            name = str(
                participant.get("name")
                or (
                    "YOU"
                    if index == player_index
                    else f"Car {index + 1}"
                )
            )

            state = CarRaceState(
                car_index=index,
                name=name,
                position=position,
                lap_number=int(
                    lap.get("lap_number", 0)
                ),
                lap_distance_m=float(
                    lap.get("lap_distance_m", 0.0)
                ),
                total_distance_m=float(
                    lap.get(
                        "total_distance_m",
                        0.0,
                    )
                ),
                current_lap_time_ms=int(
                    lap.get(
                        "current_lap_time_ms",
                        0,
                    )
                ),
                last_lap_time_ms=int(
                    lap.get(
                        "last_lap_time_ms",
                        0,
                    )
                ),
                delta_to_leader_s=float(
                    lap.get(
                        "delta_to_leader_s",
                        0.0,
                    )
                ),
                delta_to_car_ahead_s=float(
                    lap.get(
                        "delta_to_car_ahead_s",
                        0.0,
                    )
                ),
                pit_status=int(
                    lap.get("pit_status", 0)
                ),
                pit_stops=int(
                    lap.get("pit_stops", 0)
                ),
                grid_position=int(
                    lap.get("grid_position", 0)
                ),
                driver_status=int(
                    lap.get("driver_status", 0)
                ),
                result_status=int(
                    lap.get("result_status", 0)
                ),
                penalties_s=int(
                    lap.get("penalties_s", 0)
                ),
                team_id=(
                    int(participant["team_id"])
                    if "team_id" in participant
                    else None
                ),
                driver_id=(
                    int(participant["driver_id"])
                    if "driver_id" in participant
                    else None
                ),
            ).to_dict()

            rows.append(state)

        rows.sort(
            key=lambda item: int(
                item["position"]
            )
        )

        snapshot = self._snapshot
        snapshot.classification = rows
        snapshot.grid_size = len(rows)
        snapshot.leader = (
            rows[0]
            if rows
            else None
        )

        player_row = next(
            (
                row
                for row in rows
                if int(row["car_index"])
                == player_index
            ),
            None,
        )

        if not player_row:
            snapshot.car_ahead = None
            snapshot.car_behind = None
            return

        player_position = int(
            player_row["position"]
        )

        snapshot.car_ahead = next(
            (
                row
                for row in rows
                if int(row["position"])
                == player_position - 1
            ),
            None,
        )

        snapshot.car_behind = next(
            (
                row
                for row in rows
                if int(row["position"])
                == player_position + 1
            ),
            None,
        )

    def _record_position_change_locked(
        self,
        old: int,
        new: int,
    ) -> None:
        if old <= 0 or new <= 0 or old == new:
            return

        gained = old - new

        if gained > 0:
            title = "Position gained"
            description = (
                f"Moved from P{old} to P{new}."
            )
            event_type = "overtake"
            severity = "success"
        else:
            title = "Position lost"
            description = (
                f"Dropped from P{old} to P{new}."
            )
            event_type = "position_lost"
            severity = "warning"

        self._add_event_locked(
            event_type,
            severity,
            title,
            description,
            {
                "from_position": old,
                "to_position": new,
                "change": gained,
            },
            signature=(
                f"position:{old}:{new}:"
                f"{self._snapshot.lap_number}"
            ),
            dedupe_seconds=3.0,
        )

    def _apply_game_event_locked(
        self,
        event: dict[str, Any],
        player_index: int,
    ) -> None:
        code = str(event.get("code", ""))

        names = {
            "SSTA": (
                "session_started",
                "info",
                "Session started",
            ),
            "SEND": (
                "session_ended",
                "success",
                "Session ended",
            ),
            "CHQF": (
                "chequered_flag",
                "success",
                "Chequered flag",
            ),
            "FTLP": (
                "fastest_lap",
                "success",
                "Fastest lap",
            ),
            "PENA": (
                "penalty",
                "warning",
                "Penalty issued",
            ),
            "SPTP": (
                "speed_trap",
                "info",
                "Speed trap",
            ),
            "RTMT": (
                "retirement",
                "danger",
                "Retirement",
            ),
            "COLL": (
                "collision",
                "danger",
                "Contact detected",
            ),
            "OVTK": (
                "overtake",
                "success",
                "Overtake",
            ),
        }

        event_type, severity, title = names.get(
            code,
            (
                "game_event",
                "info",
                f"Game event {code}",
            ),
        )

        relevant = True

        if code == "COLL":
            relevant = player_index in {
                int(
                    event.get(
                        "vehicle_1_index",
                        -1,
                    )
                ),
                int(
                    event.get(
                        "vehicle_2_index",
                        -1,
                    )
                ),
            }

        elif code == "OVTK":
            overtaker = int(
                event.get(
                    "overtaking_vehicle_index",
                    -1,
                )
            )
            overtaken = int(
                event.get(
                    "being_overtaken_vehicle_index",
                    -1,
                )
            )

            relevant = player_index in {
                overtaker,
                overtaken,
            }

            if (
                relevant
                and overtaken == player_index
            ):
                event_type = "position_lost"
                severity = "warning"
                title = "Overtaken"

        elif "vehicle_index" in event:
            relevant = (
                int(
                    event.get(
                        "vehicle_index",
                        -1,
                    )
                )
                == player_index
            )

        if not relevant:
            return

        description = title

        if code == "COLL":
            description = (
                "The game reported contact "
                "involving the player car."
            )

        elif code == "PENA":
            description = (
                "Penalty event: "
                f"{int(event.get('time_s', 0))} "
                "second(s)."
            )

        elif code == "FTLP":
            description = (
                "Fastest lap recorded: "
                f"{float(event.get('lap_time_s', 0.0)):.3f}s."
            )

        elif code == "SPTP":
            description = (
                "Speed trap: "
                f"{float(event.get('speed_kph', 0.0)):.1f} km/h."
            )

        self._add_event_locked(
            event_type,
            severity,
            title,
            description,
            dict(event),
            signature=f"game:{code}:{event}",
            dedupe_seconds=2.0,
        )

    def _detect_damage_change_locked(
        self,
    ) -> None:
        snapshot = self._snapshot

        total = (
            int(sum(snapshot.tyre_damage_pct))
            + sum(
                int(value)
                for value in (
                    snapshot.wing_damage_pct.values()
                )
            )
        )

        increase = (
            total
            - self._last_damage_total
        )

        if (
            self._last_damage_total > 0
            and increase >= 5
            and (
                time() - self._last_incident_ts
                > 8.0
            )
        ):
            self._last_incident_ts = time()

            self._add_event_locked(
                "damage_increase",
                "danger",
                "Damage increased",
                (
                    "Vehicle damage increased by "
                    f"approximately {increase} points."
                ),
                {
                    "increase": increase,
                    "wing_damage_pct": dict(
                        snapshot.wing_damage_pct
                    ),
                    "tyre_damage_pct": list(
                        snapshot.tyre_damage_pct
                    ),
                },
                signature=(
                    f"damage:"
                    f"{snapshot.lap_number}:"
                    f"{total}"
                ),
                dedupe_seconds=8.0,
            )

        self._last_damage_total = total

    def _detect_sudden_stop_locked(
        self,
    ) -> None:
        now_timestamp = time()
        snapshot = self._snapshot
        previous = self._last_speed_sample

        self._last_speed_sample = (
            now_timestamp,
            snapshot.speed_kph,
        )

        if not previous:
            return

        elapsed = now_timestamp - previous[0]
        speed_drop = (
            previous[1]
            - snapshot.speed_kph
        )

        if (
            0 < elapsed <= 1.5
            and speed_drop >= 90
            and previous[1] >= 130
            and (
                abs(
                    snapshot.g_force_longitudinal
                )
                >= 3.0
            )
            and (
                now_timestamp
                - self._last_incident_ts
                > 10.0
            )
        ):
            self._last_incident_ts = (
                now_timestamp
            )

            self._add_event_locked(
                "possible_incident",
                "warning",
                "Possible incident",
                (
                    f"Speed dropped by {speed_drop} "
                    f"km/h in {elapsed:.1f}s."
                ),
                {
                    "speed_drop_kph": speed_drop,
                    "longitudinal_g": round(
                        snapshot.g_force_longitudinal,
                        2,
                    ),
                },
                signature=(
                    f"stop:"
                    f"{snapshot.lap_number}:"
                    f"{round(snapshot.lap_distance_m, -1)}"
                ),
                dedupe_seconds=10.0,
            )

    def _add_event_locked(
        self,
        event_type: str,
        severity: str,
        title: str,
        description: str,
        data: dict[str, Any],
        *,
        signature: str | None = None,
        dedupe_seconds: float = 0.0,
    ) -> dict[str, Any]:
        now_timestamp = time()

        key = (
            signature
            or (
                f"{event_type}:"
                f"{title}:"
                f"{self._snapshot.lap_number}"
            )
        )

        if (
            dedupe_seconds > 0
            and (
                now_timestamp
                - self._last_event_signature.get(
                    key,
                    0.0,
                )
                < dedupe_seconds
            )
        ):
            return {}

        self._last_event_signature[key] = (
            now_timestamp
        )

        self._event_id += 1

        event = RaceEvent(
            id=self._event_id,
            timestamp=now_timestamp,
            session_time=(
                self._snapshot.session_time
            ),
            lap_number=(
                self._snapshot.lap_number
            ),
            event_type=event_type,
            severity=severity,
            title=title,
            description=description,
            data=data,
        ).to_dict()

        self._race_events.appendleft(event)

        self._snapshot.race_events = list(
            self._race_events
        )

        return event

    def _append_history_locked(self) -> None:
        snapshot = self._snapshot

        last = (
            self._history[-1]
            if self._history
            else None
        )

        last_session_time = (
            float(
                last.get(
                    "session_time",
                    0.0,
                )
            )
            if last
            else None
        )

        lap_changed = bool(
            last
            and (
                snapshot.lap_number
                != int(
                    last.get(
                        "lap_number",
                        snapshot.lap_number,
                    )
                )
            )
        )

        time_changed = (
            last_session_time is None
            or (
                snapshot.session_time
                - last_session_time
                >= 0.20
            )
        )

        if (
            last
            and not lap_changed
            and not time_changed
        ):
            return

        self._history.append({
            "t": time(),
            "session_time": snapshot.session_time,
            "speed_kph": snapshot.speed_kph,
            "throttle": snapshot.throttle,
            "brake": snapshot.brake,
            "steer": snapshot.steer,
            "gear": snapshot.gear,
            "rpm": snapshot.rpm,
            "lap_distance_m": (
                snapshot.lap_distance_m
            ),
            "lap_number": snapshot.lap_number,
            "position": snapshot.position,
            "ers_percent": snapshot.ers_percent,
            "fuel_remaining_laps": (
                snapshot.fuel_remaining_laps
            ),
            "tyre_wear_pct": list(
                snapshot.tyre_wear_pct
            ),
            "tyre_surface_temps_c": list(
                snapshot.tyre_surface_temps_c
            ),
            "world_position": list(
                snapshot.world_position
            ),
            "world_velocity": list(
                snapshot.world_velocity
            ),
            "g_force_lateral": (
                snapshot.g_force_lateral
            ),
            "g_force_longitudinal": (
                snapshot.g_force_longitudinal
            ),
        })

        snapshot.history = list(
            self._history
        )

    def _append_track_point_locked(
        self,
    ) -> None:
        snapshot = self._snapshot

        if len(snapshot.world_position) < 3:
            return

        x, y, z = snapshot.world_position[:3]

        if not all(
            isfinite(value)
            for value in (x, y, z)
        ):
            return

        if abs(x) < 0.001 and abs(z) < 0.001:
            return

        current = {
            "t": time(),
            "session_time": snapshot.session_time,
            "lap_number": snapshot.lap_number,
            "lap_distance_m": (
                snapshot.lap_distance_m
            ),
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "speed_kph": snapshot.speed_kph,
        }

        if self._last_track_point:
            distance = hypot(
                (
                    current["x"]
                    - self._last_track_point["x"]
                ),
                (
                    current["z"]
                    - self._last_track_point["z"]
                ),
            )

            if (
                distance < 2.5
                and (
                    current["lap_number"]
                    == self._last_track_point[
                        "lap_number"
                    ]
                )
            ):
                return

        self._track_points.append(current)
        self._last_track_point = current

        snapshot.track_points = list(
            self._track_points
        )

    def _copy_snapshot_locked(
        self,
    ) -> LiveTelemetrySnapshot:
        result = deepcopy(self._snapshot)

        result.history = list(self._history)
        result.track_points = list(
            self._track_points
        )
        result.recent_messages = list(
            self._messages
        )
        result.race_events = list(
            self._race_events
        )
        result.completed_laps = list(
            self._completed_laps
        )

        result.last_packet_age_s = (
            None
            if self._last_packet_ts is None
            else max(
                0.0,
                time() - self._last_packet_ts,
            )
        )

        return result

    def snapshot(
        self,
    ) -> LiveTelemetrySnapshot:
        with self._lock:
            return self._copy_snapshot_locked()

    def messages(
        self,
    ) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._messages)

    def events(
        self,
    ) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._race_events)

    def completed_laps(
        self,
    ) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._completed_laps)