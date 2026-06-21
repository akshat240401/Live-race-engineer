from __future__ import annotations

import argparse
import math
import random
import socket
import struct
import time
from dataclasses import dataclass
from typing import Iterable

# F1 25 packet formats used by the project's parser.
HEADER_FMT = "<HBBBBBQfIIBB"
CAR_TELEMETRY_FMT = "<HfffBbHBBH4H4B4BH4f4B"
LAP_DATA_FMT = "<IIHBHBHBHBfffBBBBBBBBBBBBBBBHHBfB"
CAR_STATUS_FMT = "<BBBBBfffHHBBHBBBbfffBfffB"
CAR_DAMAGE_FMT = "<4f4B4B4B18B"
MOTION_2025_FMT = "<ffffffhhhhhhffffff"
SESSION_PREFIX_FMT = "<BbbBHBbBHH"

PACKET_MOTION = 0
PACKET_SESSION = 1
PACKET_LAP_DATA = 2
PACKET_EVENT = 3
PACKET_PARTICIPANTS = 4
PACKET_CAR_TELEMETRY = 6
PACKET_CAR_STATUS = 7
PACKET_CAR_DAMAGE = 10

MAX_CARS = 22
ACTIVE_CARS = 20
PLAYER_INDEX = 0
TRACK_LENGTH_M = 5000.0
DEFAULT_LAP_DURATION_S = 78.0

DRIVER_NAMES = [
    "YOU",
    "ALEX HART",
    "MAYA CHEN",
    "NOAH KING",
    "SOFIA REYES",
    "LIAM BROOKS",
    "EMMA CLARKE",
    "LEO MARTIN",
    "NORA PATEL",
    "OSCAR BELL",
    "AVA SINGH",
    "ETHAN WARD",
    "MIA FOSTER",
    "LUCAS PRICE",
    "ISLA MORGAN",
    "JACK TURNER",
    "ZOE CARTER",
    "FINN EVANS",
    "LILY COOPER",
    "MAX BENNETT",
]


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    player_position: int
    gap_ahead_start: float
    gap_ahead_end: float
    gap_behind_start: float
    gap_behind_end: float
    ers_start: float
    ers_end: float
    wear_start: float
    wear_end: float
    tyre_age_laps: int
    start_lap: int
    total_laps: int = 15
    player_last_lap_ms: int = 78_400
    ahead_last_lap_delta_ms: int = 150
    behind_last_lap_delta_ms: int = 250
    player_pit_status: int = 0
    player_pit_stops: int = 0
    ahead_pit_status: int = 0
    wing_damage_pct: int = 0
    tyre_damage_pct: int = 0
    hottest_tyre_c: int = 102
    traffic_rejoin: bool = False
    fuel_margin_laps: float = 0.6


SCENARIOS: dict[str, Scenario] = {
    "clear": Scenario(
        name="clear",
        description="Clear air, balanced battery, healthy tyres.",
        player_position=7,
        gap_ahead_start=3.8,
        gap_ahead_end=3.2,
        gap_behind_start=3.5,
        gap_behind_end=3.8,
        ers_start=62,
        ers_end=58,
        wear_start=34,
        wear_end=38,
        tyre_age_laps=6,
        start_lap=6,
    ),
    "attack": Scenario(
        name="attack",
        description="Player is closing into DRS with strong battery.",
        player_position=6,
        gap_ahead_start=1.35,
        gap_ahead_end=0.62,
        gap_behind_start=2.8,
        gap_behind_end=3.2,
        ers_start=78,
        ers_end=66,
        wear_start=41,
        wear_end=45,
        tyre_age_laps=7,
        start_lap=7,
        player_last_lap_ms=77_900,
        ahead_last_lap_delta_ms=250,
        behind_last_lap_delta_ms=550,
    ),
    "defend": Scenario(
        name="defend",
        description="Car behind closes into DRS while battery is limited.",
        player_position=5,
        gap_ahead_start=4.2,
        gap_ahead_end=4.8,
        gap_behind_start=1.05,
        gap_behind_end=0.48,
        ers_start=46,
        ers_end=34,
        wear_start=48,
        wear_end=53,
        tyre_age_laps=8,
        start_lap=8,
        player_last_lap_ms=78_800,
        ahead_last_lap_delta_ms=-350,
        behind_last_lap_delta_ms=-420,
    ),
    "box": Scenario(
        name="box",
        description="High wear plus a realistic undercut opportunity and acceptable rejoin.",
        player_position=6,
        gap_ahead_start=1.55,
        gap_ahead_end=1.10,
        gap_behind_start=3.4,
        gap_behind_end=3.8,
        ers_start=59,
        ers_end=52,
        wear_start=68,
        wear_end=75,
        tyre_age_laps=11,
        start_lap=9,
        player_last_lap_ms=80_200,
        ahead_last_lap_delta_ms=350,
        behind_last_lap_delta_ms=800,
        hottest_tyre_c=109,
    ),
    "traffic": Scenario(
        name="traffic",
        description="Tyres are marginal, but a stop would rejoin into a dense traffic train.",
        player_position=6,
        gap_ahead_start=2.1,
        gap_ahead_end=1.8,
        gap_behind_start=17.5,
        gap_behind_end=18.0,
        ers_start=55,
        ers_end=50,
        wear_start=61,
        wear_end=68,
        tyre_age_laps=10,
        start_lap=8,
        player_last_lap_ms=79_900,
        ahead_last_lap_delta_ms=100,
        behind_last_lap_delta_ms=300,
        traffic_rejoin=True,
        hottest_tyre_c=106,
    ),
    "overcut": Scenario(
        name="overcut",
        description="Car ahead enters the pits while the player's tyres remain stable.",
        player_position=6,
        gap_ahead_start=1.8,
        gap_ahead_end=1.4,
        gap_behind_start=4.0,
        gap_behind_end=4.3,
        ers_start=64,
        ers_end=58,
        wear_start=43,
        wear_end=47,
        tyre_age_laps=7,
        start_lap=8,
        player_last_lap_ms=78_300,
        ahead_last_lap_delta_ms=450,
        behind_last_lap_delta_ms=700,
        ahead_pit_status=1,
    ),
    "harvest": Scenario(
        name="harvest",
        description="No immediate battle and critically low battery.",
        player_position=8,
        gap_ahead_start=5.2,
        gap_ahead_end=4.8,
        gap_behind_start=4.5,
        gap_behind_end=4.8,
        ers_start=19,
        ers_end=11,
        wear_start=38,
        wear_end=41,
        tyre_age_laps=6,
        start_lap=6,
    ),
    "late": Scenario(
        name="late",
        description="Two laps remaining: track position should usually be protected.",
        player_position=4,
        gap_ahead_start=1.25,
        gap_ahead_end=0.95,
        gap_behind_start=0.95,
        gap_behind_end=0.75,
        ers_start=42,
        ers_end=31,
        wear_start=58,
        wear_end=63,
        tyre_age_laps=12,
        start_lap=14,
        total_laps=15,
        player_last_lap_ms=79_200,
        ahead_last_lap_delta_ms=80,
        behind_last_lap_delta_ms=-120,
    ),
    "damage": Scenario(
        name="damage",
        description="Severe front-wing damage forces an immediate box decision.",
        player_position=9,
        gap_ahead_start=2.5,
        gap_ahead_end=2.2,
        gap_behind_start=2.0,
        gap_behind_end=2.2,
        ers_start=48,
        ers_end=43,
        wear_start=49,
        wear_end=52,
        tyre_age_laps=8,
        start_lap=8,
        wing_damage_pct=62,
    ),
}

MIXED_PHASES: list[tuple[str, float]] = [
    ("clear", 20.0),
    ("attack", 30.0),
    ("defend", 30.0),
    ("box", 35.0),
    ("overcut", 25.0),
    ("harvest", 25.0),
]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(start: float, end: float, progress: float) -> float:
    return start + (end - start) * clamp(progress, 0.0, 1.0)


def seconds_parts(seconds: float) -> tuple[int, int]:
    seconds = max(0.0, float(seconds))
    minutes = min(254, int(seconds // 60.0))
    milliseconds = int(round((seconds - minutes * 60.0) * 1000.0))
    if milliseconds >= 60_000:
        minutes = min(254, minutes + 1)
        milliseconds = 0
    return min(65_534, milliseconds), minutes


def header(packet_id: int, session_uid: int, session_time: float, frame: int) -> bytes:
    return struct.pack(
        HEADER_FMT,
        2025,
        25,
        1,
        0,
        1,
        packet_id,
        session_uid,
        float(session_time),
        frame,
        frame,
        PLAYER_INDEX,
        255,
    )


def pack_session(
    session_uid: int,
    session_time: float,
    frame: int,
    total_laps: int,
    track_length_m: int,
) -> bytes:
    body = struct.pack(
        SESSION_PREFIX_FMT,
        0,       # clear weather
        31,      # track temperature
        24,      # air temperature
        total_laps,
        track_length_m,
        10,      # race session
        0,       # track id
        0,       # F1 formula
        max(0, int((total_laps * DEFAULT_LAP_DURATION_S) - session_time)),
        int(total_laps * DEFAULT_LAP_DURATION_S),
    )
    return header(PACKET_SESSION, session_uid, session_time, frame) + body


def participant_record(index: int, active: bool) -> bytes:
    record = bytearray(48)
    if not active:
        return bytes(record)
    name = DRIVER_NAMES[index].encode("utf-8")[:31]
    record[0] = 0 if index == PLAYER_INDEX else 1  # AI controlled
    record[1] = index % 32
    record[2] = index
    record[3] = index % 10
    record[4] = 0
    record[5] = (11 + index) % 100
    record[6] = 1 + (index % 20)
    record[7:7 + len(name)] = name
    record[39] = 1
    return bytes(record)


def pack_participants(session_uid: int, session_time: float, frame: int) -> bytes:
    records = [participant_record(index, index < ACTIVE_CARS) for index in range(MAX_CARS)]
    return (
        header(PACKET_PARTICIPANTS, session_uid, session_time, frame)
        + bytes([ACTIVE_CARS])
        + b"".join(records)
    )


def pack_event(
    session_uid: int,
    session_time: float,
    frame: int,
    code: str,
    details: bytes = b"",
) -> bytes:
    event_code = code.encode("ascii")[:4].ljust(4, b" ")
    return header(PACKET_EVENT, session_uid, session_time, frame) + event_code + details


def order_for_player_position(player_position: int) -> list[int]:
    others = list(range(1, ACTIVE_CARS))
    insert_at = clamp(player_position - 1, 0, len(others))
    order = others.copy()
    order.insert(int(insert_at), PLAYER_INDEX)
    return order


def build_gap_chain(
    scenario: Scenario,
    progress: float,
) -> tuple[list[int], dict[int, float], dict[int, float]]:
    order = order_for_player_position(scenario.player_position)
    gap_ahead = lerp(scenario.gap_ahead_start, scenario.gap_ahead_end, progress)
    gap_behind = lerp(scenario.gap_behind_start, scenario.gap_behind_end, progress)

    per_position_gap: dict[int, float] = {1: 0.0}
    for position in range(2, ACTIVE_CARS + 1):
        # A varied but stable field spread.
        per_position_gap[position] = 1.45 + 0.30 * math.sin(position * 1.7)

    player_position = scenario.player_position
    if player_position > 1:
        per_position_gap[player_position] = gap_ahead
    if player_position < ACTIVE_CARS:
        per_position_gap[player_position + 1] = gap_behind

    if scenario.traffic_rejoin:
        # The player is isolated, but a train sits around the estimated +22 s rejoin point.
        for position, value in {
            player_position + 1: 17.5,
            player_position + 2: 1.0,
            player_position + 3: 1.0,
            player_position + 4: 1.0,
            player_position + 5: 1.0,
            player_position + 6: 1.0,
        }.items():
            if 2 <= position <= ACTIVE_CARS:
                per_position_gap[position] = value

    cumulative: dict[int, float] = {}
    running = 0.0
    for position in range(1, ACTIVE_CARS + 1):
        if position > 1:
            running += per_position_gap[position]
        car_index = order[position - 1]
        cumulative[car_index] = running

    return order, per_position_gap, cumulative


def track_controls(lap_distance_m: float) -> tuple[int, float, float, float, int, int, float, float]:
    phase = (lap_distance_m / TRACK_LENGTH_M) % 1.0
    angle = phase * 2.0 * math.pi

    # Multiple braking zones create more realistic traces than a perfect circle.
    braking = 0.0
    for center, width, strength in [
        (0.08, 0.025, 1.0),
        (0.24, 0.035, 0.70),
        (0.43, 0.028, 0.95),
        (0.63, 0.040, 0.78),
        (0.82, 0.030, 1.0),
    ]:
        distance = min(abs(phase - center), 1.0 - abs(phase - center))
        braking = max(braking, strength * math.exp(-((distance / width) ** 2)))

    steer = (
        0.45 * math.sin(angle * 5.0)
        + 0.20 * math.sin(angle * 9.0 + 0.7)
    )
    steer *= 0.35 + 0.65 * braking
    brake = clamp((braking - 0.18) * 1.15, 0.0, 1.0)
    throttle = clamp(1.0 - brake * 1.25 - abs(steer) * 0.18, 0.0, 1.0)
    speed = int(clamp(325.0 - brake * 205.0 - abs(steer) * 48.0, 72.0, 334.0))
    gear = int(clamp(round(speed / 42.0) + 1, 1, 8))
    rpm = int(clamp(4400 + throttle * 7100 + speed * 5.0, 4000, 12_000))
    lateral_g = steer * (speed / 150.0) * 2.2
    longitudinal_g = -brake * 4.3 + throttle * 0.45
    return speed, throttle, brake, steer, gear, rpm, lateral_g, longitudinal_g


def pack_motion(
    session_uid: int,
    session_time: float,
    frame: int,
    lap_distance_m: float,
    speed_kph: int,
    steer: float,
    lateral_g: float,
    longitudinal_g: float,
) -> bytes:
    phase = (lap_distance_m / TRACK_LENGTH_M) * 2.0 * math.pi
    radius_x = 840.0 + 110.0 * math.sin(phase * 3.0)
    radius_z = 610.0 + 70.0 * math.cos(phase * 2.0)
    x = math.cos(phase) * radius_x
    z = math.sin(phase) * radius_z
    vx = -math.sin(phase) * speed_kph / 3.6
    vz = math.cos(phase) * speed_kph / 3.6

    records: list[bytes] = []
    for index in range(MAX_CARS):
        offset = 3.0 * index
        records.append(
            struct.pack(
                MOTION_2025_FMT,
                float(x + offset),
                0.0,
                float(z + offset),
                float(vx),
                0.0,
                float(vz),
                0,
                0,
                0,
                0,
                0,
                0,
                float(lateral_g),
                float(longitudinal_g),
                1.0,
                float(phase),
                0.0,
                float(steer * 0.05),
            )
        )
    return header(PACKET_MOTION, session_uid, session_time, frame) + b"".join(records)


def pack_telemetry(
    session_uid: int,
    session_time: float,
    frame: int,
    speed: int,
    throttle: float,
    brake: float,
    steer: float,
    gear: int,
    rpm: int,
    drs: bool,
    hottest_tyre_c: int,
) -> bytes:
    records: list[bytes] = []
    for index in range(MAX_CARS):
        player = index == PLAYER_INDEX
        car_speed = speed if player else max(80, speed + ((index % 5) - 2) * 2)
        car_throttle = throttle if player else clamp(throttle * 0.95, 0.0, 1.0)
        car_brake = brake if player else clamp(brake * 0.9, 0.0, 1.0)
        car_steer = steer if player else steer * 0.85
        brake_temps = [610 + int(car_brake * 330)] * 4
        tyre_surface = [
            hottest_tyre_c - 2,
            hottest_tyre_c,
            hottest_tyre_c - 5,
            hottest_tyre_c - 4,
        ]
        tyre_inner = [value - 6 for value in tyre_surface]
        pressures = [22.8, 22.9, 23.1, 23.0]
        records.append(
            struct.pack(
                CAR_TELEMETRY_FMT,
                int(car_speed),
                float(car_throttle),
                float(car_steer),
                float(car_brake),
                0,
                int(gear),
                int(rpm),
                1 if player and drs else 0,
                min(100, int(rpm / 12_000 * 100)),
                0,
                *brake_temps,
                *tyre_surface,
                *tyre_inner,
                99,
                *pressures,
                0,
                0,
                0,
                0,
            )
        )
    return (
        header(PACKET_CAR_TELEMETRY, session_uid, session_time, frame)
        + b"".join(records)
        + struct.pack("<BBb", 255, 255, 0)
    )


def car_absolute_distance(
    player_absolute_distance: float,
    player_delta_to_leader_s: float,
    car_delta_to_leader_s: float,
    reference_speed_mps: float,
) -> float:
    leader_absolute = player_absolute_distance + player_delta_to_leader_s * reference_speed_mps
    return leader_absolute - car_delta_to_leader_s * reference_speed_mps


def pack_lap_data(
    session_uid: int,
    session_time: float,
    frame: int,
    scenario: Scenario,
    progress: float,
    player_absolute_distance: float,
    lap_duration_s: float,
    speed_kph: int,
) -> bytes:
    order, per_position_gap, cumulative = build_gap_chain(scenario, progress)
    position_by_index = {car_index: position for position, car_index in enumerate(order, start=1)}
    player_delta = cumulative[PLAYER_INDEX]
    reference_speed_mps = max(55.0, speed_kph / 3.6)

    records: list[bytes] = []
    for index in range(MAX_CARS):
        if index >= ACTIVE_CARS:
            records.append(struct.pack(LAP_DATA_FMT, *([0] * 10), 0.0, 0.0, 0.0, *([0] * 18), 0.0, 255))
            continue

        position = position_by_index[index]
        delta_leader = cumulative[index]
        delta_front = per_position_gap[position] if position > 1 else 0.0
        absolute = car_absolute_distance(
            player_absolute_distance,
            player_delta,
            delta_leader,
            reference_speed_mps,
        )
        lap_number = max(1, int(absolute // TRACK_LENGTH_M) + 1)
        lap_distance = absolute % TRACK_LENGTH_M
        current_lap_ms = int((lap_distance / TRACK_LENGTH_M) * lap_duration_s * 1000.0)

        relative_position = position - scenario.player_position
        last_lap = scenario.player_last_lap_ms + relative_position * 140
        if position == scenario.player_position - 1:
            last_lap = scenario.player_last_lap_ms + scenario.ahead_last_lap_delta_ms
        elif position == scenario.player_position + 1:
            last_lap = scenario.player_last_lap_ms + scenario.behind_last_lap_delta_ms
        last_lap = max(65_000, last_lap)

        delta_front_ms, delta_front_min = seconds_parts(delta_front)
        delta_leader_ms, delta_leader_min = seconds_parts(delta_leader)
        sector = 0 if lap_distance < TRACK_LENGTH_M / 3 else 1 if lap_distance < 2 * TRACK_LENGTH_M / 3 else 2

        pit_status = 0
        pit_stops = 0
        if index == PLAYER_INDEX:
            pit_status = scenario.player_pit_status
            pit_stops = scenario.player_pit_stops
        elif position == scenario.player_position - 1:
            pit_status = scenario.ahead_pit_status
            pit_stops = 1 if scenario.ahead_pit_status else 0

        records.append(
            struct.pack(
                LAP_DATA_FMT,
                int(last_lap),
                int(current_lap_ms),
                25_000,
                0,
                52_000,
                0,
                delta_front_ms,
                delta_front_min,
                delta_leader_ms,
                delta_leader_min,
                float(lap_distance),
                float(absolute),
                0.0,
                position,
                min(255, lap_number),
                pit_status,
                pit_stops,
                sector,
                0,
                0,
                0,
                0,
                0,
                0,
                position,
                4,
                2,
                1 if pit_status else 0,
                0,
                0,
                0,
                float(324.0 - position * 0.35),
                min(254, lap_number),
            )
        )

    return (
        header(PACKET_LAP_DATA, session_uid, session_time, frame)
        + b"".join(records)
        + struct.pack("<BB", 255, 255)
    )


def pack_status(
    session_uid: int,
    session_time: float,
    frame: int,
    scenario: Scenario,
    ers_percent: float,
    tyre_age_laps: int,
    fuel_remaining_laps: float,
    drs_allowed: bool,
) -> bytes:
    records: list[bytes] = []
    for index in range(MAX_CARS):
        player = index == PLAYER_INDEX
        battery = ers_percent if player else 55.0 + (index % 5) * 3.0
        ers_j = clamp(battery, 0.0, 100.0) / 100.0 * 4_000_000.0
        records.append(
            struct.pack(
                CAR_STATUS_FMT,
                0,
                0,
                1,
                56,
                0,
                38.5,
                110.0,
                float(fuel_remaining_laps if player else fuel_remaining_laps + 0.5),
                12_000,
                4_000,
                8,
                1 if player and drs_allowed else 0,
                80,
                17,
                17,
                max(0, min(120, tyre_age_laps if player else 6 + index % 4)),
                0,
                720_000.0,
                120_000.0,
                float(ers_j),
                2,
                35_000.0,
                0.0,
                900_000.0,
                0,
            )
        )
    return header(PACKET_CAR_STATUS, session_uid, session_time, frame) + b"".join(records)


def pack_damage(
    session_uid: int,
    session_time: float,
    frame: int,
    scenario: Scenario,
    wear: float,
) -> bytes:
    records: list[bytes] = []
    for index in range(MAX_CARS):
        if index == PLAYER_INDEX:
            wear_values = [wear + 1.0, wear + 0.5, wear - 1.5, wear - 1.0]
            tyre_damage = scenario.tyre_damage_pct
            wing = scenario.wing_damage_pct
        else:
            base = 30.0 + (index % 5) * 3.0
            wear_values = [base + 1.0, base, base - 1.0, base - 0.5]
            tyre_damage = 0
            wing = 0

        tail = [
            wing,
            wing,
            0,
            0,
            0,
            0,
            0,
            0,
            3,
            2,
            5,
            5,
            4,
            5,
            4,
            5,
            0,
            0,
        ]
        records.append(
            struct.pack(
                CAR_DAMAGE_FMT,
                *[float(clamp(value, 0.0, 100.0)) for value in wear_values],
                tyre_damage,
                tyre_damage,
                tyre_damage,
                tyre_damage,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                *tail,
            )
        )
    return header(PACKET_CAR_DAMAGE, session_uid, session_time, frame) + b"".join(records)


def scenario_for_mixed(elapsed: float) -> tuple[Scenario, float, int]:
    cycle_duration = sum(duration for _, duration in MIXED_PHASES)
    local = elapsed % cycle_duration
    cursor = 0.0
    for phase_index, (name, duration) in enumerate(MIXED_PHASES):
        if local < cursor + duration:
            progress = (local - cursor) / duration
            return SCENARIOS[name], progress, phase_index
        cursor += duration
    return SCENARIOS[MIXED_PHASES[-1][0]], 1.0, len(MIXED_PHASES) - 1


def print_help_for_scenario(name: str) -> None:
    questions = {
        "attack": ["Can I attack?", "When should I deploy?", "Who is ahead?", "Am I gaining?"],
        "defend": ["Should I defend?", "How much battery should I keep?", "Who is behind?"],
        "box": ["Should I box?", "Can I undercut the car ahead?", "Will I lose position if I box?"],
        "traffic": ["Should I box?", "Will I rejoin in traffic?", "Can these tyres finish?"],
        "overcut": ["Should I box?", "Can I overcut?", "What should I do this lap?"],
        "harvest": ["When should I deploy?", "How much battery should I save?", "Can I attack?"],
        "late": ["Should I box?", "Can these tyres finish?", "Can I attack?"],
        "damage": ["Should I box?", "Do I have damage?"],
        "clear": ["Give me a strategy update.", "What should I focus on this lap?"],
        "mixed": ["Give me a strategy update.", "Can I attack?", "Should I box?", "When should I deploy?"],
    }
    print("Suggested voice tests:")
    for question in questions.get(name, questions["mixed"]):
        print(f"  - Engineer -> {question}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-car F1 25 UDP race scenario simulator for the Live Race Engineer project."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=20777)
    parser.add_argument("--hz", type=float, default=30.0)
    parser.add_argument(
        "--scenario",
        choices=["mixed", *SCENARIOS.keys()],
        default="mixed",
        help="Race situation to simulate.",
    )
    parser.add_argument(
        "--lap-seconds",
        type=float,
        default=DEFAULT_LAP_DURATION_S,
        help="Synthetic lap duration. Lower values advance laps faster.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=25,
        help="Random seed used for repeatable packet variation.",
    )
    args = parser.parse_args()

    if args.hz <= 0:
        raise SystemExit("--hz must be greater than zero")
    if args.lap_seconds < 20:
        raise SystemExit("--lap-seconds must be at least 20")

    random.seed(args.seed)
    session_uid = random.randint(10_000_000, 9_999_999_999)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.host, args.port)
    dt = 1.0 / args.hz
    started = time.monotonic()
    frame = 0
    last_print = -999.0
    last_phase_index: int | None = None
    previous_player_position: int | None = None

    initial = SCENARIOS["clear"] if args.scenario == "mixed" else SCENARIOS[args.scenario]
    print("=" * 72)
    print("Live Race Engineer - multi-car strategy simulator")
    print(f"Target: {args.host}:{args.port} at {args.hz:.1f} Hz")
    print(f"Scenario: {args.scenario}")
    print(f"Session UID: {session_uid}")
    print(f"Grid: {ACTIVE_CARS} cars | Player index: {PLAYER_INDEX}")
    print(f"Initial description: {initial.description}")
    print_help_for_scenario(args.scenario)
    print("Press Ctrl+C to stop.")
    print("=" * 72)

    # Send metadata and a session-start event immediately.
    sock.sendto(pack_session(session_uid, 0.0, frame, initial.total_laps, int(TRACK_LENGTH_M)), target)
    sock.sendto(pack_participants(session_uid, 0.0, frame), target)
    sock.sendto(pack_event(session_uid, 0.0, frame, "SSTA"), target)

    try:
        while True:
            loop_started = time.monotonic()
            elapsed = loop_started - started

            if args.scenario == "mixed":
                scenario, phase_progress, phase_index = scenario_for_mixed(elapsed)
            else:
                scenario = SCENARIOS[args.scenario]
                phase_progress = (elapsed % 40.0) / 40.0
                phase_index = 0

            if phase_index != last_phase_index:
                print(f"\n>>> Phase: {scenario.name.upper()} - {scenario.description}")
                print_help_for_scenario(scenario.name)
                last_phase_index = phase_index

            # Each scenario starts at a meaningful race lap but still progresses naturally.
            player_absolute = (
                (scenario.start_lap - 1) * TRACK_LENGTH_M
                + ((elapsed % (args.lap_seconds * 3.0)) / args.lap_seconds) * TRACK_LENGTH_M
            )
            player_lap = int(player_absolute // TRACK_LENGTH_M) + 1
            player_lap_distance = player_absolute % TRACK_LENGTH_M

            gap_ahead = lerp(scenario.gap_ahead_start, scenario.gap_ahead_end, phase_progress)
            gap_behind = lerp(scenario.gap_behind_start, scenario.gap_behind_end, phase_progress)
            ers = lerp(scenario.ers_start, scenario.ers_end, phase_progress)
            wear = lerp(scenario.wear_start, scenario.wear_end, phase_progress)
            tyre_age = scenario.tyre_age_laps + max(0, player_lap - scenario.start_lap)
            laps_remaining = max(0, scenario.total_laps - player_lap + 1)
            fuel_remaining = max(0.2, laps_remaining + scenario.fuel_margin_laps)

            speed, throttle, brake, steer, gear, rpm, lat_g, long_g = track_controls(player_lap_distance)
            drs_allowed = player_lap > 2 and gap_ahead <= 1.0
            straight = throttle > 0.90 and brake < 0.05 and abs(steer) < 0.16 and speed > 210
            drs_open = drs_allowed and straight

            packets: list[bytes] = [
                pack_motion(
                    session_uid,
                    elapsed,
                    frame,
                    player_lap_distance,
                    speed,
                    steer,
                    lat_g,
                    long_g,
                ),
                pack_telemetry(
                    session_uid,
                    elapsed,
                    frame,
                    speed,
                    throttle,
                    brake,
                    steer,
                    gear,
                    rpm,
                    drs_open,
                    scenario.hottest_tyre_c,
                ),
                pack_lap_data(
                    session_uid,
                    elapsed,
                    frame,
                    scenario,
                    phase_progress,
                    player_absolute,
                    args.lap_seconds,
                    speed,
                ),
                pack_status(
                    session_uid,
                    elapsed,
                    frame,
                    scenario,
                    ers,
                    tyre_age,
                    fuel_remaining,
                    drs_allowed,
                ),
            ]

            if frame % max(1, int(args.hz * 0.5)) == 0:
                packets.append(pack_damage(session_uid, elapsed, frame, scenario, wear))
            if frame % max(1, int(args.hz * 1.0)) == 0:
                packets.append(
                    pack_session(
                        session_uid,
                        elapsed,
                        frame,
                        scenario.total_laps,
                        int(TRACK_LENGTH_M),
                    )
                )
            if frame % max(1, int(args.hz * 3.0)) == 0:
                packets.append(pack_participants(session_uid, elapsed, frame))

            current_position = scenario.player_position
            if previous_player_position is not None and current_position != previous_player_position:
                order = order_for_player_position(current_position)
                if current_position < previous_player_position:
                    overtaken_index = order[current_position] if current_position < len(order) else 1
                    packets.append(
                        pack_event(
                            session_uid,
                            elapsed,
                            frame,
                            "OVTK",
                            bytes([PLAYER_INDEX, overtaken_index]),
                        )
                    )
                else:
                    overtaker_index = order[current_position - 2] if current_position >= 2 else 1
                    packets.append(
                        pack_event(
                            session_uid,
                            elapsed,
                            frame,
                            "OVTK",
                            bytes([overtaker_index, PLAYER_INDEX]),
                        )
                    )
            previous_player_position = current_position

            for packet in packets:
                sock.sendto(packet, target)

            if elapsed - last_print >= 1.0:
                print(
                    f"[{scenario.name:7}] "
                    f"Lap {player_lap}/{scenario.total_laps} "
                    f"P{scenario.player_position}/{ACTIVE_CARS} | "
                    f"ahead {gap_ahead:4.2f}s | behind {gap_behind:4.2f}s | "
                    f"ERS {ers:4.0f}% | wear {wear:4.0f}% | "
                    f"DRS {'YES' if drs_allowed else 'NO '} | "
                    f"speed {speed:3d}"
                )
                last_print = elapsed

            frame += 1
            remaining = dt - (time.monotonic() - loop_started)
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
