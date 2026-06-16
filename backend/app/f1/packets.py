from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import struct

from app.f1.constants import PacketId, PACKET_NAMES

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


def max_cars_for_format(packet_format: int) -> int:
    # F1 25 spec uses 22 cars; 2026 Season Pack spec uses 24.
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
            return PACKET_NAMES.get(PacketId(self.packet_id), f"unknown_{self.packet_id}")
        except ValueError:
            return f"unknown_{self.packet_id}"


@dataclass(slots=True)
class ParsedPacket:
    header: PacketHeader
    kind: str
    player: dict[str, Any]
    raw_size: int


class PacketParseError(ValueError):
    pass


def _require_size(data: bytes, minimum: int, packet_name: str) -> None:
    if len(data) < minimum:
        raise PacketParseError(f"{packet_name}: expected at least {minimum} bytes, got {len(data)}")


def parse_header(data: bytes) -> PacketHeader:
    _require_size(data, HEADER_SIZE, "header")
    values = struct.unpack_from(HEADER_FMT, data, 0)
    return PacketHeader(*values)


def _player_index(header: PacketHeader) -> int:
    cars = max_cars_for_format(header.packet_format)
    if 0 <= header.player_car_index < cars:
        return header.player_car_index
    return 0


def parse_packet(data: bytes) -> ParsedPacket:
    header = parse_header(data)
    kind = header.packet_name
    player: dict[str, Any] = {}

    if header.packet_id == PacketId.CAR_TELEMETRY:
        player = parse_car_telemetry(data, header)
    elif header.packet_id == PacketId.LAP_DATA:
        player = parse_lap_data(data, header)
    elif header.packet_id == PacketId.CAR_STATUS:
        player = parse_car_status(data, header)
    elif header.packet_id == PacketId.CAR_DAMAGE:
        player = parse_car_damage(data, header)
    elif header.packet_id == PacketId.MOTION:
        player = parse_motion(data, header)
    elif header.packet_id == PacketId.SESSION:
        player = parse_session(data, header)
    else:
        # Not used by the MVP dashboard; still return header info so packet counters work.
        player = {}

    return ParsedPacket(header=header, kind=kind, player=player, raw_size=len(data))


def parse_car_telemetry(data: bytes, header: PacketHeader) -> dict[str, Any]:
    cars = max_cars_for_format(header.packet_format)
    needed = HEADER_SIZE + cars * CAR_TELEMETRY_SIZE + 3
    _require_size(data, min(needed, len(data)), "car_telemetry")
    idx = _player_index(header)
    offset = HEADER_SIZE + idx * CAR_TELEMETRY_SIZE
    values = struct.unpack_from(CAR_TELEMETRY_FMT, data, offset)

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
        "brake_temps_c": [int(x) for x in values[10:14]],
        "tyre_surface_temps_c": [int(x) for x in values[14:18]],
        "tyre_inner_temps_c": [int(x) for x in values[18:22]],
        "engine_temp_c": int(values[22]),
        "tyre_pressures_psi": [float(x) for x in values[23:27]],
        "surface_type": [int(x) for x in values[27:31]],
    }


def parse_lap_data(data: bytes, header: PacketHeader) -> dict[str, Any]:
    cars = max_cars_for_format(header.packet_format)
    needed = HEADER_SIZE + cars * LAP_DATA_SIZE + 2
    _require_size(data, min(needed, len(data)), "lap_data")
    idx = _player_index(header)
    offset = HEADER_SIZE + idx * LAP_DATA_SIZE
    v = struct.unpack_from(LAP_DATA_FMT, data, offset)

    return {
        "last_lap_time_ms": int(v[0]),
        "current_lap_time_ms": int(v[1]),
        "sector1_ms_part": int(v[2]),
        "sector1_min_part": int(v[3]),
        "sector2_ms_part": int(v[4]),
        "sector2_min_part": int(v[5]),
        "delta_car_front_ms_part": int(v[6]),
        "delta_car_front_min_part": int(v[7]),
        "delta_leader_ms_part": int(v[8]),
        "delta_leader_min_part": int(v[9]),
        "lap_distance_m": float(v[10]),
        "total_distance_m": float(v[11]),
        "safety_car_delta_s": float(v[12]),
        "position": int(v[13]),
        "lap_number": int(v[14]),
        "pit_status": int(v[15]),
        "pit_stops": int(v[16]),
        "sector": int(v[17]) + 1,
        "lap_invalid": bool(v[18]),
        "penalties_s": int(v[19]),
        "warnings": int(v[20]),
        "corner_cutting_warnings": int(v[21]),
        "drive_through_pens": int(v[22]),
        "stop_go_pens": int(v[23]),
        "grid_position": int(v[24]),
        "driver_status": int(v[25]),
        "result_status": int(v[26]),
        "pit_lane_timer_active": bool(v[27]),
        "pit_lane_time_ms": int(v[28]),
        "pit_stop_timer_ms": int(v[29]),
        "pit_stop_should_serve_penalty": bool(v[30]),
        "speed_trap_fastest_kph": float(v[31]),
        "speed_trap_fastest_lap": int(v[32]),
    }


def parse_car_status(data: bytes, header: PacketHeader) -> dict[str, Any]:
    cars = max_cars_for_format(header.packet_format)
    needed = HEADER_SIZE + cars * CAR_STATUS_SIZE
    _require_size(data, min(needed, len(data)), "car_status")
    idx = _player_index(header)
    offset = HEADER_SIZE + idx * CAR_STATUS_SIZE
    v = struct.unpack_from(CAR_STATUS_FMT, data, offset)

    return {
        "traction_control": int(v[0]),
        "anti_lock_brakes": bool(v[1]),
        "fuel_mix": int(v[2]),
        "front_brake_bias": int(v[3]),
        "pit_limiter": bool(v[4]),
        "fuel_in_tank_kg": float(v[5]),
        "fuel_capacity_kg": float(v[6]),
        "fuel_remaining_laps": float(v[7]),
        "max_rpm": int(v[8]),
        "idle_rpm": int(v[9]),
        "max_gears": int(v[10]),
        "drs_allowed": bool(v[11]),
        "drs_activation_distance_m": int(v[12]),
        "actual_tyre_compound": int(v[13]),
        "visual_tyre_compound": int(v[14]),
        "tyre_age_laps": int(v[15]),
        "fia_flag": int(v[16]),
        "engine_power_ice_w": float(v[17]),
        "engine_power_mguk_w": float(v[18]),
        "ers_store_j": float(v[19]),
        "ers_deploy_mode": int(v[20]),
        "ers_harvested_mguk_j": float(v[21]),
        "ers_harvested_mguh_j": float(v[22]),
        "ers_deployed_this_lap_j": float(v[23]),
        "network_paused": bool(v[24]),
    }


def parse_car_damage(data: bytes, header: PacketHeader) -> dict[str, Any]:
    cars = max_cars_for_format(header.packet_format)
    needed = HEADER_SIZE + cars * CAR_DAMAGE_SIZE
    _require_size(data, min(needed, len(data)), "car_damage")
    idx = _player_index(header)
    offset = HEADER_SIZE + idx * CAR_DAMAGE_SIZE
    v = struct.unpack_from(CAR_DAMAGE_FMT, data, offset)

    tail = [int(x) for x in v[16:34]]
    return {
        "tyre_wear_pct": [float(x) for x in v[0:4]],
        "tyre_damage_pct": [int(x) for x in v[4:8]],
        "brake_damage_pct": [int(x) for x in v[8:12]],
        "tyre_blisters_pct": [int(x) for x in v[12:16]],
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


def parse_motion(data: bytes, header: PacketHeader) -> dict[str, Any]:
    idx = _player_index(header)
    if header.packet_format >= 2026:
        fmt = MOTION_2026_FMT
        size = MOTION_2026_SIZE
        offset = HEADER_SIZE + idx * size
        _require_size(data, offset + size, "motion_2026")
        v = struct.unpack_from(fmt, data, offset)
        return {
            "world_position": [float(v[0]), float(v[1]), float(v[2])],
            "world_velocity": [float(v[3]), float(v[4]), float(v[5])],
            "g_force_lateral": float(v[12]) / 1000.0,
            "g_force_longitudinal": float(v[13]) / 1000.0,
            "g_force_vertical": float(v[14]) / 1000.0,
            "yaw": float(v[15]),
            "pitch": float(v[16]),
            "roll": float(v[17]),
        }

    fmt = MOTION_2025_FMT
    size = MOTION_2025_SIZE
    offset = HEADER_SIZE + idx * size
    _require_size(data, offset + size, "motion_2025")
    v = struct.unpack_from(fmt, data, offset)
    return {
        "world_position": [float(v[0]), float(v[1]), float(v[2])],
        "world_velocity": [float(v[3]), float(v[4]), float(v[5])],
        "g_force_lateral": float(v[12]),
        "g_force_longitudinal": float(v[13]),
        "g_force_vertical": float(v[14]),
        "yaw": float(v[15]),
        "pitch": float(v[16]),
        "roll": float(v[17]),
    }


def parse_session(data: bytes, header: PacketHeader) -> dict[str, Any]:
    offset = HEADER_SIZE
    _require_size(data, offset + SESSION_PREFIX_SIZE, "session")
    v = struct.unpack_from(SESSION_PREFIX_FMT, data, offset)
    return {
        "weather": int(v[0]),
        "track_temp_c": int(v[1]),
        "air_temp_c": int(v[2]),
        "total_laps": int(v[3]),
        "track_length_m": int(v[4]),
        "session_type": int(v[5]),
        "track_id": int(v[6]),
        "formula": int(v[7]),
        "session_time_left_s": int(v[8]),
        "session_duration_s": int(v[9]),
    }
