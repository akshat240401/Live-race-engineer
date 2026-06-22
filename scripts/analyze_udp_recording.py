from __future__ import annotations

import argparse
import json
import math
import statistics
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

MAGIC = b"LREUDP1\n"
FILE_HEADER_LEN = struct.Struct("<I")
RECORD_HEADER = struct.Struct("<QI")
F1_HEADER = struct.Struct("<HBBBBBQfIIBB")

PACKET_NAMES = {
    0: "motion",
    1: "session",
    2: "lap_data",
    3: "event",
    4: "participants",
    5: "car_setups",
    6: "car_telemetry",
    7: "car_status",
    8: "final_classification",
    9: "lobby_info",
    10: "car_damage",
    11: "session_history",
    12: "tyre_sets",
    13: "motion_ex",
    14: "time_trial",
}


@dataclass(slots=True)
class Record:
    relative_ns: int
    payload: bytes


@dataclass(slots=True)
class Header:
    packet_format: int
    packet_id: int
    session_uid: int
    session_time: float
    frame_identifier: int
    overall_frame_identifier: int
    player_car_index: int


def read_metadata(handle: BinaryIO) -> dict:
    if handle.read(len(MAGIC)) != MAGIC:
        raise ValueError("Not a Live Race Engineer raw UDP recording.")
    raw_len = handle.read(FILE_HEADER_LEN.size)
    if len(raw_len) != FILE_HEADER_LEN.size:
        raise ValueError("Truncated file metadata length.")
    (length,) = FILE_HEADER_LEN.unpack(raw_len)
    encoded = handle.read(length)
    if len(encoded) != length:
        raise ValueError("Truncated file metadata.")
    return json.loads(encoded.decode("utf-8"))


def iter_records(handle: BinaryIO) -> Iterator[Record]:
    while True:
        raw_header = handle.read(RECORD_HEADER.size)
        if not raw_header:
            return
        if len(raw_header) != RECORD_HEADER.size:
            raise ValueError("Truncated record header.")
        relative_ns, payload_len = RECORD_HEADER.unpack(raw_header)
        payload = handle.read(payload_len)
        if len(payload) != payload_len:
            raise ValueError("Truncated UDP payload.")
        yield Record(relative_ns=relative_ns, payload=payload)


def parse_header(payload: bytes) -> Header | None:
    if len(payload) < F1_HEADER.size:
        return None
    values = F1_HEADER.unpack_from(payload, 0)
    return Header(
        packet_format=int(values[0]),
        packet_id=int(values[5]),
        session_uid=int(values[6]),
        session_time=float(values[7]),
        frame_identifier=int(values[8]),
        overall_frame_identifier=int(values[9]),
        player_car_index=int(values[10]),
    )


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    fraction = rank - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def rounded(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze packet rates and timing in a raw F1 UDP recording.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--json-output", type=Path, default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = args.input.resolve()
    if not path.exists():
        print(f"Recording not found: {path}", file=sys.stderr)
        return 2

    counts: Counter[int | str] = Counter()
    sizes: defaultdict[int | str, list[int]] = defaultdict(list)
    arrivals_ns: defaultdict[int | str, list[int]] = defaultdict(list)
    frames: defaultdict[int, list[int]] = defaultdict(list)
    sessions: Counter[int] = Counter()
    packet_formats: Counter[int] = Counter()
    malformed = 0
    total_bytes = 0
    first_ns: int | None = None
    last_ns: int | None = None

    try:
        with path.open("rb") as handle:
            metadata = read_metadata(handle)
            for record in iter_records(handle):
                if first_ns is None:
                    first_ns = record.relative_ns
                last_ns = record.relative_ns
                total_bytes += len(record.payload)
                header = parse_header(record.payload)
                key: int | str
                if header is None:
                    key = "unknown"
                    malformed += 1
                else:
                    key = header.packet_id
                    sessions[header.session_uid] += 1
                    packet_formats[header.packet_format] += 1
                    frames[header.packet_id].append(header.frame_identifier)
                counts[key] += 1
                sizes[key].append(len(record.payload))
                arrivals_ns[key].append(record.relative_ns)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        return 1

    duration_s = 0.0
    if first_ns is not None and last_ns is not None:
        duration_s = max(0.0, (last_ns - first_ns) / 1_000_000_000)

    packet_stats: dict[str, dict] = {}
    for key, count in sorted(counts.items(), key=lambda item: str(item[0])):
        name = PACKET_NAMES.get(key, str(key))
        times = arrivals_ns[key]
        intervals_ms = [
            (times[index] - times[index - 1]) / 1_000_000
            for index in range(1, len(times))
            if times[index] >= times[index - 1]
        ]
        frame_values = frames[key] if isinstance(key, int) else []
        duplicate_frames = 0
        backwards_frames = 0
        frame_gaps = 0
        for index in range(1, len(frame_values)):
            delta = frame_values[index] - frame_values[index - 1]
            if delta == 0:
                duplicate_frames += 1
            elif delta < 0:
                backwards_frames += 1
            elif delta > 1:
                frame_gaps += delta - 1

        packet_stats[name] = {
            "packet_id": key if isinstance(key, int) else None,
            "count": count,
            "rate_hz": rounded(count / duration_s if duration_s > 0 else 0.0),
            "size_bytes_mean": rounded(statistics.fmean(sizes[key]) if sizes[key] else None),
            "interval_ms_mean": rounded(statistics.fmean(intervals_ms) if intervals_ms else None),
            "interval_ms_p95": rounded(percentile(intervals_ms, 0.95)),
            "interval_ms_max": rounded(max(intervals_ms) if intervals_ms else None),
            "duplicate_frames": duplicate_frames,
            "backwards_frames": backwards_frames,
            "estimated_missing_frames": frame_gaps,
        }

    result = {
        "recording": str(path),
        "metadata": metadata,
        "duration_s": rounded(duration_s, 6),
        "packet_count": sum(counts.values()),
        "total_bytes": total_bytes,
        "overall_rate_hz": rounded(sum(counts.values()) / duration_s if duration_s > 0 else 0.0),
        "malformed_headers": malformed,
        "session_uids": [{"session_uid": uid, "packets": count} for uid, count in sessions.most_common()],
        "packet_formats": dict(packet_formats),
        "packet_types": packet_stats,
    }

    print(f"Recording : {path}")
    print(f"Created   : {metadata.get('created_utc', '-')}")
    print(f"Duration  : {duration_s:.2f} s")
    print(f"Packets   : {result['packet_count']}")
    print(f"Rate      : {result['overall_rate_hz']} packets/s")
    print(f"Malformed : {malformed}\n")
    print(
        f"{'Packet type':24} {'Count':>9} {'Hz':>8} {'Mean ms':>10} {'P95 ms':>10} "
        f"{'Max ms':>10} {'Dup':>6} {'Back':>6} {'Missing':>8}"
    )
    print("-" * 105)
    for name, stats in packet_stats.items():
        print(
            f"{name:24} {stats['count']:9d} {str(stats['rate_hz']):>8} "
            f"{str(stats['interval_ms_mean']):>10} {str(stats['interval_ms_p95']):>10} "
            f"{str(stats['interval_ms_max']):>10} {stats['duplicate_frames']:6d} "
            f"{stats['backwards_frames']:6d} {stats['estimated_missing_frames']:8d}"
        )

    output = args.json_output or path.with_suffix(path.suffix + ".analysis.json")
    output = output.resolve()
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nJSON analysis: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())