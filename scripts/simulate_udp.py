from __future__ import annotations

import argparse
import math
import socket
import struct
import time

HEADER_FMT = "<HBBBBBQfIIBB"
CAR_TELEMETRY_FMT = "<HfffBbHBBH4H4B4BH4f4B"
LAP_DATA_FMT = "<IIHBHBHBHBfffBBBBBBBBBBBBBBBHHBfB"
CAR_STATUS_FMT = "<BBBBBfffHHBBHBBBbfffBfffB"
CAR_DAMAGE_FMT = "<4f4B4B4B18B"
MOTION_2025_FMT = "<ffffffhhhhhhffffff"

MAX_CARS = 22
PLAYER_INDEX = 0
SESSION_UID = 123456789
TRACK_LENGTH_M = 5000.0


def header(packet_id: int, session_time: float, frame: int) -> bytes:
    return struct.pack(
        HEADER_FMT,
        2025,
        25,
        1,
        0,
        1,
        packet_id,
        SESSION_UID,
        float(session_time),
        frame,
        frame,
        PLAYER_INDEX,
        255,
    )


def pack_telemetry(session_time: float, frame: int, speed: int, throttle: float, brake: float, steer: float, gear: int, rpm: int) -> bytes:
    cars = []
    for idx in range(MAX_CARS):
        v_speed = speed if idx == PLAYER_INDEX else max(0, speed - 15 + idx)
        v_throttle = throttle if idx == PLAYER_INDEX else 0.55
        v_brake = brake if idx == PLAYER_INDEX else 0.0
        v_steer = steer if idx == PLAYER_INDEX else 0.0
        brake_temps = [620 + int(brake * 300)] * 4
        tyre_surface = [92 + int(throttle * 10), 94 + int(throttle * 11), 90 + int(abs(steer) * 12), 91 + int(abs(steer) * 12)]
        tyre_inner = [88, 88, 86, 86]
        pressures = [22.8, 22.9, 23.1, 23.0]
        surfaces = [0, 0, 0, 0]
        cars.append(struct.pack(
            CAR_TELEMETRY_FMT,
            v_speed,
            float(v_throttle),
            float(v_steer),
            float(v_brake),
            0,
            int(gear),
            int(rpm),
            1 if speed > 240 and abs(steer) < 0.1 else 0,
            min(100, int(rpm / 12000 * 100)),
            0,
            *brake_temps,
            *tyre_surface,
            *tyre_inner,
            98,
            *pressures,
            *surfaces,
        ))
    return header(6, session_time, frame) + b"".join(cars) + struct.pack("<BBb", 255, 255, 0)


def pack_lap(session_time: float, frame: int, lap_num: int, current_lap_time_ms: int, last_lap_ms: int, distance: float, invalid: bool) -> bytes:
    cars = []
    sector = 0 if distance < TRACK_LENGTH_M / 3 else 1 if distance < 2 * TRACK_LENGTH_M / 3 else 2
    for idx in range(MAX_CARS):
        cars.append(struct.pack(
            LAP_DATA_FMT,
            last_lap_ms if idx == PLAYER_INDEX else max(0, last_lap_ms + idx * 120),
            current_lap_time_ms,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            float(distance),
            float((lap_num - 1) * TRACK_LENGTH_M + distance),
            0.0,
            1 + idx,
            lap_num,
            0,
            0,
            sector,
            1 if invalid else 0,
            0,
            1 if invalid else 0,
            1 if invalid else 0,
            0,
            0,
            1,
            4,
            2,
            0,
            0,
            0,
            0,
            float(315.0),
            255,
        ))
    return header(2, session_time, frame) + b"".join(cars) + struct.pack("<BB", 255, 255)


def pack_status(session_time: float, frame: int, ers_percent: float, fuel_delta: float, tyre_age: int) -> bytes:
    cars = []
    ers_j = max(0.0, min(4_000_000.0, ers_percent / 100.0 * 4_000_000.0))
    for idx in range(MAX_CARS):
        cars.append(struct.pack(
            CAR_STATUS_FMT,
            0,
            0,
            1,
            56,
            0,
            38.5,
            110.0,
            float(fuel_delta),
            12000,
            4000,
            8,
            1,
            80,
            18,
            17,
            tyre_age,
            0,
            720000.0,
            120000.0,
            ers_j,
            2,
            35000.0,
            0.0,
            900000.0,
            0,
        ))
    return header(7, session_time, frame) + b"".join(cars)


def pack_damage(session_time: float, frame: int, lap_num: int) -> bytes:
    cars = []
    wear = min(75.0, lap_num * 3.2)
    for idx in range(MAX_CARS):
        cars.append(struct.pack(
            CAR_DAMAGE_FMT,
            wear + 1.2,
            wear + 1.0,
            wear * 0.85,
            wear * 0.9,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            *([0] * 18),
        ))
    return header(10, session_time, frame) + b"".join(cars)


def pack_motion(session_time: float, frame: int, distance: float, speed_kph: int, steer: float) -> bytes:
    cars = []
    angle = distance / TRACK_LENGTH_M * 2 * math.pi
    radius = 900.0
    x = math.cos(angle) * radius
    z = math.sin(angle) * radius
    vx = -math.sin(angle) * speed_kph / 3.6
    vz = math.cos(angle) * speed_kph / 3.6
    for idx in range(MAX_CARS):
        cars.append(struct.pack(
            MOTION_2025_FMT,
            float(x + idx * 3),
            0.0,
            float(z + idx * 3),
            float(vx),
            0.0,
            float(vz),
            0,
            0,
            0,
            0,
            0,
            0,
            float(steer * 2.0),
            float(-0.5 if speed_kph > 100 else 0.0),
            1.0,
            float(angle),
            0.0,
            float(steer * 0.04),
        ))
    return header(0, session_time, frame) + b"".join(cars)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=20777)
    parser.add_argument("--hz", type=float, default=30.0)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.host, args.port)
    dt = 1.0 / args.hz
    session_time = 0.0
    frame = 0
    lap_num = 1
    distance = 0.0
    lap_start_time = 0.0
    last_lap_ms = 0

    print(f"Sending simulated F1 25 UDP packets to {args.host}:{args.port} at {args.hz} Hz")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            phase = (distance / TRACK_LENGTH_M) * 2 * math.pi
            corner = (math.sin(phase * 8) + 1.0) / 2.0
            brake = max(0.0, min(1.0, (corner - 0.72) * 3.2))
            throttle = max(0.0, min(1.0, 1.0 - brake * 1.15))
            steer = math.sin(phase * 8) * 0.55 if corner > 0.55 else math.sin(phase * 3) * 0.08
            speed = int(max(65, min(330, 315 - brake * 190 - abs(steer) * 45 + throttle * 20)))
            rpm = int(4200 + throttle * 7200 + speed * 8)
            gear = max(1, min(8, int(speed / 42) + 1))

            speed_mps = speed / 3.6
            distance += speed_mps * dt
            if distance >= TRACK_LENGTH_M:
                distance -= TRACK_LENGTH_M
                last_lap_ms = int((session_time - lap_start_time) * 1000)
                lap_start_time = session_time
                lap_num += 1

            current_lap_ms = int((session_time - lap_start_time) * 1000)
            invalid = (lap_num % 5 == 0 and 1300 < distance < 1600)
            ers = max(5.0, 80.0 - (distance / TRACK_LENGTH_M) * 65.0 + (lap_num % 2) * 15.0)
            fuel_delta = 0.4 - lap_num * 0.04

            packets = [
                pack_motion(session_time, frame, distance, speed, steer),
                pack_telemetry(session_time, frame, speed, throttle, brake, steer, gear, rpm),
                pack_lap(session_time, frame, lap_num, current_lap_ms, last_lap_ms, distance, invalid),
                pack_status(session_time, frame, ers, fuel_delta, lap_num),
            ]
            if frame % int(args.hz * 0.5) == 0:
                packets.append(pack_damage(session_time, frame, lap_num))

            for pkt in packets:
                sock.sendto(pkt, target)

            session_time += dt
            frame += 1
            time.sleep(dt)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")


if __name__ == "__main__":
    main()