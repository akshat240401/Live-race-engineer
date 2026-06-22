from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

MAGIC = b"LREUDP1\n"
FILE_HEADER_LEN = struct.Struct("<I")
RECORD_HEADER = struct.Struct("<QI")
F1_HEADER = struct.Struct("<HBBBBBQfIIBB")


@dataclass(slots=True)
class Record:
    relative_ns: int
    payload: bytes


def read_metadata(handle: BinaryIO) -> dict:
    magic = handle.read(len(MAGIC))
    if magic != MAGIC:
        raise ValueError("Not a Live Race Engineer raw UDP recording.")
    raw_len = handle.read(FILE_HEADER_LEN.size)
    if len(raw_len) != FILE_HEADER_LEN.size:
        raise ValueError("Recording header is truncated.")
    (length,) = FILE_HEADER_LEN.unpack(raw_len)
    encoded = handle.read(length)
    if len(encoded) != length:
        raise ValueError("Recording metadata is truncated.")
    return json.loads(encoded.decode("utf-8"))


def iter_records(handle: BinaryIO) -> Iterator[Record]:
    while True:
        raw_header = handle.read(RECORD_HEADER.size)
        if not raw_header:
            return
        if len(raw_header) != RECORD_HEADER.size:
            raise ValueError("Recording ends with a truncated record header.")
        relative_ns, payload_len = RECORD_HEADER.unpack(raw_header)
        payload = handle.read(payload_len)
        if len(payload) != payload_len:
            raise ValueError("Recording ends with a truncated UDP payload.")
        yield Record(relative_ns=relative_ns, payload=payload)


def packet_brief(payload: bytes) -> tuple[int | None, int | None]:
    if len(payload) < F1_HEADER.size:
        return None, None
    values = F1_HEADER.unpack_from(payload, 0)
    return int(values[5]), int(values[8])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay a recorded F1 UDP session.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=20778)
    parser.add_argument("--speed", type=float, default=1.0, help="1=real time, 2=twice speed, 0=as fast as possible")
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--duration-seconds", type=float, default=0.0)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--status-interval", type=float, default=1.0)
    return parser


def replay_once(path: Path, host: str, port: int, speed: float, start_s: float, duration_s: float, status_interval: float) -> int:
    sent = 0
    first_selected_ns: int | None = None
    replay_started_ns: int | None = None
    last_status = time.perf_counter()
    latest_packet_id: int | None = None
    latest_frame: int | None = None

    with path.open("rb") as handle, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        metadata = read_metadata(handle)
        print(f"Recording created: {metadata.get('created_utc', '-')}")
        print(f"Replaying to     : {host}:{port}")
        print(f"Speed            : {'maximum' if speed == 0 else f'{speed:g}x'}")

        for record in iter_records(handle):
            record_s = record.relative_ns / 1_000_000_000
            if record_s < start_s:
                continue
            if duration_s > 0 and record_s > start_s + duration_s:
                break

            if first_selected_ns is None:
                first_selected_ns = record.relative_ns
                replay_started_ns = time.perf_counter_ns()

            if speed > 0 and replay_started_ns is not None and first_selected_ns is not None:
                target_elapsed_ns = int((record.relative_ns - first_selected_ns) / speed)
                while True:
                    elapsed_ns = time.perf_counter_ns() - replay_started_ns
                    remaining_ns = target_elapsed_ns - elapsed_ns
                    if remaining_ns <= 0:
                        break
                    if remaining_ns > 2_000_000:
                        time.sleep((remaining_ns - 1_000_000) / 1_000_000_000)
                    else:
                        time.sleep(0)

            sock.sendto(record.payload, (host, port))
            sent += 1
            latest_packet_id, latest_frame = packet_brief(record.payload)

            now = time.perf_counter()
            if now - last_status >= max(0.25, status_interval):
                print(f"sent={sent:7d} latest_packet_id={latest_packet_id} frame={latest_frame}")
                last_status = now

    print(f"Replay complete. Sent {sent} packets.")
    return sent


def main() -> int:
    args = build_parser().parse_args()
    path = args.input.resolve()
    if not path.exists():
        print(f"Recording not found: {path}", file=sys.stderr)
        return 2
    if args.speed < 0:
        print("--speed must be zero or greater.", file=sys.stderr)
        return 2

    try:
        while True:
            replay_once(
                path=path,
                host=args.host,
                port=args.port,
                speed=args.speed,
                start_s=max(0.0, args.start_seconds),
                duration_s=max(0.0, args.duration_seconds),
                status_interval=args.status_interval,
            )
            if not args.loop:
                break
            print("Restarting replay in one second. Press Ctrl+C to stop.")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nReplay stopped.")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Replay failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
