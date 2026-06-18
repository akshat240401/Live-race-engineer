from __future__ import annotations

from dataclasses import dataclass, field
import struct
from typing import Any

from app.f1.constants import PACKET_NAMES, PacketId

HEADER_FMT = "<HBBBBBQfIIBB"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

CAR_TELEMETRY_FMT = "<HfffBbHBBH4H4B4BH4f4B"
CAR_TELEMETRY_SIZE = struct.calcsize(CAR_TELEMETRY_FMT)

LAP_DATA_FMT = "<IIHBHBHBHBfffBBBBBBBBBBBBBBBHHBfB"
LAP_DATA_SIZE = struct.calcsize(LAP_DATA_FMT)

CAR_STATUS_FMT = "<BBBBBfffHHBBHBBBbfffBfffB"
CAR_STATUS_SIZE = struct.calcsize(CAR_STATUS_FMT)

CAR_DAMAGE_FMT = "<4f4B4B4B18B"
CAR_DAMAGE_SIZE = struct.calcsize(CAR_DAMAGE_FMT)

MOTION_2025_FMT = "<ffffffhhhhhhffffff"
MOTION_2025_SIZE = struct.calcsize(MOTION_2025_FMT)

MOTION_2026_FMT = "<ffffffhhhhhhhhhfff"
MOTION_2026_SIZE = struct.calcsize(MOTION_2026_FMT)

SESSION_PREFIX_FMT = "<BbbBHBbBHH"
SESSION_PREFIX_SIZE = struct.calcsize(SESSION_PREFIX_FMT)

PARTICIPANT_MIN_SIZE = 39

FINAL_CLASSIFICATION_FMT = "<6BId3B8B8B8B"
FINAL_CLASSIFICATION_SIZE = struct.calcsize(
    FINAL_CLASSIFICATION_FMT
)


def max_cars_for_format(packet_format: int) -> int:
    return 24 if packet_format >= 2026 else 22


@dataclass(slots=True)
class PacketHeader:
    packet_format: int
    game_year: int
    game_major_version: int
    game_minor_version: int
    packet_version: int
    packet_id: int
    session_uid: int
    session_time: float
    frame_identifier: int
    overall_frame_identifier: int
    player_car_index: int
    secondary_player_car_index: int

    @property
    def packet_name(self) -> str:
        try:
            return PACKET_NAMES.get(
                PacketId(self.packet_id),
                f"unknown_{self.packet_id}",
            )
        except ValueError:
            return f"unknown_{self.packet_id}"


@dataclass(slots=True)
class ParsedPacket:
    header: PacketHeader
    kind: str
    player: dict[str, Any]
    raw_size: int
    cars: list[dict[str, Any]] = field(default_factory=list)
    event: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

class PacketParseError(ValueError):
    pass

def _require_size(
    data: bytes,
    minimum: int,
    packet_name: str,
) -> None:
    if len(data) < minimum:
        raise PacketParseError(
            f"{packet_name}: expected at least "
            f"{minimum} bytes, got {len(data)}"
        )

def parse_header(data: bytes) -> PacketHeader:
    _require_size(data, HEADER_SIZE, "header")
    return PacketHeader(
        *struct.unpack_from(HEADER_FMT, data, 0)
    )

def _player_index(header: PacketHeader) -> int:
    cars = max_cars_for_format(header.packet_format)
    if 0 <= header.player_car_index < cars:
        return header.player_car_index
    return 0

def _combine_min_ms(
    minutes: int,
    milliseconds: int,
) -> float:
    if minutes == 255 or milliseconds == 65535:
        return 0.0
    return float(minutes * 60) + float(milliseconds) / 1000.0

def parse_packet(data: bytes) -> ParsedPacket:
    header = parse_header(data)
    kind = header.packet_name

    player: dict[str, Any] = {}
    cars: list[dict[str, Any]] = []
    event: dict[str, Any] | None = None
    meta: dict[str, Any] = {}

    if header.packet_id == PacketId.CAR_TELEMETRY:
        player = parse_car_telemetry(data, header)

    elif header.packet_id == PacketId.LAP_DATA:
        cars = parse_lap_data_all(data, header)
        index = _player_index(header)
        player = cars[index] if index < len(cars) else {}

    elif header.packet_id == PacketId.CAR_STATUS:
        player = parse_car_status(data, header)

    elif header.packet_id == PacketId.CAR_DAMAGE:
        player = parse_car_damage(data, header)

    elif header.packet_id == PacketId.MOTION:
        player = parse_motion(data, header)

    elif header.packet_id == PacketId.SESSION:
        player = parse_session(data, header)

    elif header.packet_id == PacketId.PARTICIPANTS:
        cars, meta = parse_participants(data, header)
        index = _player_index(header)
        player = cars[index] if index < len(cars) else {}

    elif header.packet_id == PacketId.FINAL_CLASSIFICATION:
        cars, meta = parse_final_classification(
            data,
            header,
        )
        index = _player_index(header)
        player = cars[index] if index < len(cars) else {}

    elif header.packet_id == PacketId.EVENT:
        event = parse_event(data, header)

    return ParsedPacket(
        header=header,
        kind=kind,
        player=player,
        raw_size=len(data),
        cars=cars,
        event=event,
        meta=meta,
    )

def parse_car_telemetry(
    data: bytes,
    header: PacketHeader,
) -> dict[str, Any]:
    index = _player_index(header)
    offset = HEADER_SIZE + index * CAR_TELEMETRY_SIZE

    _require_size(
        data,
        offset + CAR_TELEMETRY_SIZE,
        "car_telemetry",
    )

    values = struct.unpack_from(
        CAR_TELEMETRY_FMT,
        data,
        offset,
    )

    return {
        "speed_kph": int(values[0]),
        "throttle": float(values[1]),
        "steer": float(values[2]),
        "brake": float(values[3]),
        "clutch": int(values[4]),
        "gear": int(values[5]),
        "rpm": int(values[6]),
        "drs": bool(values[7]),
        "rev_lights_percent": int(values[8]),
        "rev_lights_bit_value": int(values[9]),
        "brake_temps_c": [
            int(value)
            for value in values[10:14]
        ],
        "tyre_surface_temps_c": [
            int(value)
            for value in values[14:18]
        ],
        "tyre_inner_temps_c": [
            int(value)
            for value in values[18:22]
        ],
        "engine_temp_c": int(values[22]),
        "tyre_pressures_psi": [
            float(value)
            for value in values[23:27]
        ],
        "surface_type": [
            int(value)
            for value in values[27:31]
        ],
    }

def _lap_data_to_dict(
    values: tuple[Any, ...],
    car_index: int,
) -> dict[str, Any]:
    return {
        "car_index": car_index,
        "last_lap_time_ms": int(values[0]),
        "current_lap_time_ms": int(values[1]),
        "sector1_ms_part": int(values[2]),
        "sector1_min_part": int(values[3]),
        "sector2_ms_part": int(values[4]),
        "sector2_min_part": int(values[5]),
        "delta_car_front_ms_part": int(values[6]),
        "delta_car_front_min_part": int(values[7]),
        "delta_leader_ms_part": int(values[8]),
        "delta_leader_min_part": int(values[9]),
        "delta_to_car_ahead_s": _combine_min_ms(
            int(values[7]),
            int(values[6]),
        ),
        "delta_to_leader_s": _combine_min_ms(
            int(values[9]),
            int(values[8]),
        ),
        "lap_distance_m": float(values[10]),
        "total_distance_m": float(values[11]),
        "safety_car_delta_s": float(values[12]),
        "position": int(values[13]),
        "lap_number": int(values[14]),
        "pit_status": int(values[15]),
        "pit_stops": int(values[16]),
        "sector": int(values[17]) + 1,
        "lap_invalid": bool(values[18]),
        "penalties_s": int(values[19]),
        "warnings": int(values[20]),
        "corner_cutting_warnings": int(values[21]),
        "drive_through_pens": int(values[22]),
        "stop_go_pens": int(values[23]),
        "grid_position": int(values[24]),
        "driver_status": int(values[25]),
        "result_status": int(values[26]),
        "pit_lane_timer_active": bool(values[27]),
        "pit_lane_time_ms": int(values[28]),
        "pit_stop_timer_ms": int(values[29]),
        "pit_stop_should_serve_penalty": bool(
            values[30]
        ),
        "speed_trap_fastest_kph": float(values[31]),
        "speed_trap_fastest_lap": int(values[32]),
    }

def parse_lap_data_all(
    data: bytes,
    header: PacketHeader,
) -> list[dict[str, Any]]:
    max_cars = max_cars_for_format(
        header.packet_format
    )

    available = max(
        0,
        (len(data) - HEADER_SIZE) // LAP_DATA_SIZE,
    )

    count = min(max_cars, available)
    cars: list[dict[str, Any]] = []

    for index in range(count):
        offset = HEADER_SIZE + index * LAP_DATA_SIZE
        values = struct.unpack_from(
            LAP_DATA_FMT,
            data,
            offset,
        )
        cars.append(
            _lap_data_to_dict(values, index)
        )

    return cars

def parse_car_status(
    data: bytes,
    header: PacketHeader,
) -> dict[str, Any]:
    index = _player_index(header)
    offset = HEADER_SIZE + index * CAR_STATUS_SIZE

    _require_size(
        data,
        offset + CAR_STATUS_SIZE,
        "car_status",
    )

    values = struct.unpack_from(
        CAR_STATUS_FMT,
        data,
        offset,
    )

    return {
        "traction_control": int(values[0]),
        "anti_lock_brakes": bool(values[1]),
        "fuel_mix": int(values[2]),
        "front_brake_bias": int(values[3]),
        "pit_limiter": bool(values[4]),
        "fuel_in_tank_kg": float(values[5]),
        "fuel_capacity_kg": float(values[6]),
        "fuel_remaining_laps": float(values[7]),
        "max_rpm": int(values[8]),
        "idle_rpm": int(values[9]),
        "max_gears": int(values[10]),
        "drs_allowed": bool(values[11]),
        "drs_activation_distance_m": int(values[12]),
        "actual_tyre_compound": int(values[13]),
        "visual_tyre_compound": int(values[14]),
        "tyre_age_laps": int(values[15]),
        "fia_flag": int(values[16]),
        "engine_power_ice_w": float(values[17]),
        "engine_power_mguk_w": float(values[18]),
        "ers_store_j": float(values[19]),
        "ers_deploy_mode": int(values[20]),
        "ers_harvested_mguk_j": float(values[21]),
        "ers_harvested_mguh_j": float(values[22]),
        "ers_deployed_this_lap_j": float(values[23]),
        "network_paused": bool(values[24]),
    }


def parse_car_damage(
    data: bytes,
    header: PacketHeader,
) -> dict[str, Any]:
    index = _player_index(header)
    offset = HEADER_SIZE + index * CAR_DAMAGE_SIZE

    _require_size(
        data,
        offset + CAR_DAMAGE_SIZE,
        "car_damage",
    )

    values = struct.unpack_from(
        CAR_DAMAGE_FMT,
        data,
        offset,
    )

    tail = [
        int(value)
        for value in values[16:34]
    ]

    return {
        "tyre_wear_pct": [
            float(value)
            for value in values[0:4]
        ],
        "tyre_damage_pct": [
            int(value)
            for value in values[4:8]
        ],
        "brake_damage_pct": [
            int(value)
            for value in values[8:12]
        ],
        "tyre_blisters_pct": [
            int(value)
            for value in values[12:16]
        ],
        "front_left_wing_damage_pct": tail[0],
        "front_right_wing_damage_pct": tail[1],
        "rear_wing_damage_pct": tail[2],
        "floor_damage_pct": tail[3],
        "diffuser_damage_pct": tail[4],
        "sidepod_damage_pct": tail[5],
        "drs_fault": bool(tail[6]),
        "ers_fault": bool(tail[7]),
        "gearbox_damage_pct": tail[8],
        "engine_damage_pct": tail[9],
        "engine_wear": {
            "mguh": tail[10],
            "es": tail[11],
            "ce": tail[12],
            "ice": tail[13],
            "mguk": tail[14],
            "tc": tail[15],
        },
        "engine_blown": bool(tail[16]),
        "engine_seized": bool(tail[17]),
    }


def parse_motion(
    data: bytes,
    header: PacketHeader,
) -> dict[str, Any]:
    index = _player_index(header)

    if header.packet_format >= 2026:
        size = MOTION_2026_SIZE
        offset = HEADER_SIZE + index * size

        _require_size(
            data,
            offset + size,
            "motion_2026",
        )

        values = struct.unpack_from(
            MOTION_2026_FMT,
            data,
            offset,
        )

        return {
            "world_position": [
                float(values[0]),
                float(values[1]),
                float(values[2]),
            ],
            "world_velocity": [
                float(values[3]),
                float(values[4]),
                float(values[5]),
            ],
            "g_force_lateral": float(values[12]) / 1000.0,
            "g_force_longitudinal": float(values[13]) / 1000.0,
            "g_force_vertical": float(values[14]) / 1000.0,
            "yaw": float(values[15]),
            "pitch": float(values[16]),
            "roll": float(values[17]),
        }

    size = MOTION_2025_SIZE
    offset = HEADER_SIZE + index * size

    _require_size(
        data,
        offset + size,
        "motion_2025",
    )

    values = struct.unpack_from(
        MOTION_2025_FMT,
        data,
        offset,
    )

    return {
        "world_position": [
            float(values[0]),
            float(values[1]),
            float(values[2]),
        ],
        "world_velocity": [
            float(values[3]),
            float(values[4]),
            float(values[5]),
        ],
        "g_force_lateral": float(values[12]),
        "g_force_longitudinal": float(values[13]),
        "g_force_vertical": float(values[14]),
        "yaw": float(values[15]),
        "pitch": float(values[16]),
        "roll": float(values[17]),
    }


def parse_session(
    data: bytes,
    header: PacketHeader,
) -> dict[str, Any]:
    offset = HEADER_SIZE

    _require_size(
        data,
        offset + SESSION_PREFIX_SIZE,
        "session",
    )

    values = struct.unpack_from(
        SESSION_PREFIX_FMT,
        data,
        offset,
    )

    return {
        "weather": int(values[0]),
        "track_temp_c": int(values[1]),
        "air_temp_c": int(values[2]),
        "total_laps": int(values[3]),
        "track_length_m": int(values[4]),
        "session_type": int(values[5]),
        "track_id": int(values[6]),
        "formula": int(values[7]),
        "session_time_left_s": int(values[8]),
        "session_duration_s": int(values[9]),
    }


def parse_participants(
    data: bytes,
    header: PacketHeader,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _require_size(
        data,
        HEADER_SIZE + 1,
        "participants",
    )

    active_cars = int(data[HEADER_SIZE])
    max_cars = max_cars_for_format(
        header.packet_format
    )

    body_offset = HEADER_SIZE + 1
    remaining = len(data) - body_offset
    stride = remaining // max_cars if max_cars else 0

    if stride < PARTICIPANT_MIN_SIZE:
        return [], {
            "num_active_cars": active_cars,
        }

    cars: list[dict[str, Any]] = []

    count = min(
        max_cars,
        active_cars or max_cars,
    )

    for index in range(count):
        offset = body_offset + index * stride

        if offset + PARTICIPANT_MIN_SIZE > len(data):
            break

        name_raw = data[
            offset + 7:
            offset + 39
        ]

        name = (
            name_raw
            .split(b"\x00", 1)[0]
            .decode("utf-8", errors="replace")
            .strip()
        )

        cars.append({
            "car_index": index,
            "ai_controlled": int(data[offset]),
            "driver_id": int(data[offset + 1]),
            "network_id": int(data[offset + 2]),
            "team_id": int(data[offset + 3]),
            "my_team": bool(data[offset + 4]),
            "race_number": int(data[offset + 5]),
            "nationality": int(data[offset + 6]),
            "name": name or f"Car {index + 1}",
            "your_telemetry": (
                int(data[offset + 39])
                if stride > 39
                else 0
            ),
        })

    return cars, {
        "num_active_cars": active_cars,
    }


def parse_final_classification(
    data: bytes,
    header: PacketHeader,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _require_size(
        data,
        HEADER_SIZE + 1,
        "final_classification",
    )

    number_of_cars = int(data[HEADER_SIZE])
    body_offset = HEADER_SIZE + 1
    remaining = len(data) - body_offset

    stride = remaining // max(
        1,
        max_cars_for_format(header.packet_format),
    )

    if stride < FINAL_CLASSIFICATION_SIZE:
        stride = FINAL_CLASSIFICATION_SIZE

    cars: list[dict[str, Any]] = []

    for index in range(number_of_cars):
        offset = body_offset + index * stride

        if (
            offset + FINAL_CLASSIFICATION_SIZE
            > len(data)
        ):
            break

        values = struct.unpack_from(
            FINAL_CLASSIFICATION_FMT,
            data,
            offset,
        )

        cars.append({
            "car_index": index,
            "position": int(values[0]),
            "num_laps": int(values[1]),
            "grid_position": int(values[2]),
            "points": int(values[3]),
            "num_pit_stops": int(values[4]),
            "result_status": int(values[5]),
            "best_lap_time_ms": int(values[6]),
            "total_race_time_s": float(values[7]),
            "penalties_s": int(values[8]),
            "num_penalties": int(values[9]),
            "num_tyre_stints": int(values[10]),
            "tyre_stints_actual": [
                int(value)
                for value in values[11:19]
            ],
            "tyre_stints_visual": [
                int(value)
                for value in values[19:27]
            ],
            "tyre_stints_end_laps": [
                int(value)
                for value in values[27:35]
            ],
        })

    return cars, {
        "num_cars": number_of_cars,
    }

def parse_event(
    data: bytes,
    header: PacketHeader,
) -> dict[str, Any]:
    _require_size(
        data,
        HEADER_SIZE + 4,
        "event",
    )

    code = (
        data[HEADER_SIZE:HEADER_SIZE + 4]
        .decode("ascii", errors="replace")
    )

    details = data[HEADER_SIZE + 4:]
    result: dict[str, Any] = {
        "code": code,
    }

    try:
        if code in {
            "SSTA",
            "SEND",
            "CHQF",
            "RCWN",
        }:
            pass

        elif (
            code in {
                "RTMT",
                "TMPT",
                "DTSV",
                "SGSV",
            }
            and len(details) >= 1
        ):
            result["vehicle_index"] = int(details[0])

        elif code == "FTLP" and len(details) >= 5:
            result["vehicle_index"] = int(details[0])
            result["lap_time_s"] = float(
                struct.unpack_from(
                    "<f",
                    details,
                    1,
                )[0]
            )

        elif code == "SPTP" and len(details) >= 5:
            result["vehicle_index"] = int(details[0])
            result["speed_kph"] = float(
                struct.unpack_from(
                    "<f",
                    details,
                    1,
                )[0]
            )

        elif code == "COLL" and len(details) >= 2:
            result["vehicle_1_index"] = int(details[0])
            result["vehicle_2_index"] = int(details[1])

        elif code == "PENA" and len(details) >= 7:
            result.update({
                "penalty_type": int(details[0]),
                "infringement_type": int(details[1]),
                "vehicle_index": int(details[2]),
                "other_vehicle_index": int(details[3]),
                "time_s": int(details[4]),
                "lap_number": int(details[5]),
                "places_gained": int(details[6]),
            })

        elif code == "OVTK" and len(details) >= 2:
            result["overtaking_vehicle_index"] = int(
                details[0]
            )
            result["being_overtaken_vehicle_index"] = int(
                details[1]
            )

    except (IndexError, struct.error):
        result["parse_warning"] = (
            "Event details were shorter than expected"
        )

    return result