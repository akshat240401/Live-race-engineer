from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

MAGIC = b"LREUDP1\n"
FILE_HEADER_LEN = struct.Struct("<I")
RECORD_HEADER = struct.Struct("<QI")  # relative monotonic ns, payload length
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
class HeaderView:
    packet_format: int | None = None
    packet_id: int | None = None
    session_uid: int | None = None
    session_time: float | None = None
    frame_identifier: int | None = None
    overall_frame_identifier: int | None = None
    player_car_index: int | None = None


def parse_f1_header(payload: bytes) -> HeaderView:
    if len(payload) < F1_HEADER.size:
        return HeaderView()
    try:
        values = F1_HEADER.unpack_from(payload, 0)
    except struct.error:
        return HeaderView()
    return HeaderView(
        packet_format=int(values[0]),
        packet_id=int(values[5]),
        session_uid=int(values[6]),
        session_time=float(values[7]),
        frame_identifier=int(values[8]),
        overall_frame_identifier=int(values[9]),
        player_car_index=int(values[10]),
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("recordings") / "udp" / f"f1_session_{stamp}.lreudp"


def write_file_header(handle: BinaryIO, metadata: dict) -> None:
    encoded = json.dumps(metadata, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    handle.write(MAGIC)
    handle.write(FILE_HEADER_LEN.pack(len(encoded)))
    handle.write(encoded)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Record raw F1 UDP datagrams and optionally forward each packet unchanged "
            "to the race-engineer backend."
        )
    )
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=20777)
    parser.add_argument("--forward-host", default="127.0.0.1")
    parser.add_argument("--forward-port", type=int, default=20778)
    parser.add_argument("--no-forward", action="store_true", help="Record only; do not forward packets.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--status-interval", type=float, default=1.0)
    parser.add_argument("--flush-every", type=int, default=100)
    parser.add_argument("--max-seconds", type=float, default=0.0)
    parser.add_argument("--receive-buffer", type=int, default=4 * 1024 * 1024)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = args.output or default_output_path()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path = output.with_suffix(output.suffix + ".summary.json")

    metadata = {
        "format": "LiveRaceEngineerRawUDP",
        "format_version": 1,
        "created_utc": utc_now_iso(),
        "listen_host": args.listen_host,
        "listen_port": args.listen_port,
        "forward_enabled": not args.no_forward,
        "forward_host": None if args.no_forward else args.forward_host,
        "forward_port": None if args.no_forward else args.forward_port,
        "record_header": "<QI relative_monotonic_ns,payload_length>",
        "f1_header": "<HBBBBBQfIIBB",
    }

    packet_counts: Counter[int | str] = Counter()
    byte_count = 0
    forwarded_count = 0
    forward_errors = 0
    malformed_headers = 0
    packet_count = 0
    first_perf_ns: int | None = None
    latest_header = HeaderView()
    started_perf = time.perf_counter()
    last_status = started_perf
    last_status_packets = 0
    stopped_reason = "keyboard_interrupt"

    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, max(65536, args.receive_buffer))
        recv_sock.bind((args.listen_host, args.listen_port))
        recv_sock.settimeout(0.5)
    except OSError as exc:
        print(f"Unable to bind UDP {args.listen_host}:{args.listen_port}: {exc}", file=sys.stderr)
        print("Make sure the old simulator/backend is not already using this port.", file=sys.stderr)
        return 2

    print("Raw F1 UDP recorder started")
    print(f"Listening : {args.listen_host}:{args.listen_port}")
    if args.no_forward:
        print("Forwarding: disabled")
    else:
        print(f"Forwarding: {args.forward_host}:{args.forward_port}")
    print(f"Recording : {output}")
    print("Press Ctrl+C to stop cleanly.\n")

    try:
        with output.open("wb") as handle:
            write_file_header(handle, metadata)
            while True:
                now_perf = time.perf_counter()
                if args.max_seconds > 0 and now_perf - started_perf >= args.max_seconds:
                    stopped_reason = "max_seconds"
                    break

                try:
                    payload, source = recv_sock.recvfrom(65535)
                except socket.timeout:
                    payload = b""
                    source = None
                except OSError as exc:
                    stopped_reason = f"socket_error:{exc}"
                    break

                if payload:
                    received_ns = time.perf_counter_ns()
                    if first_perf_ns is None:
                        first_perf_ns = received_ns
                    relative_ns = received_ns - first_perf_ns
                    handle.write(RECORD_HEADER.pack(relative_ns, len(payload)))
                    handle.write(payload)

                    packet_count += 1
                    byte_count += len(payload)
                    header = parse_f1_header(payload)
                    latest_header = header
                    if header.packet_id is None:
                        packet_counts["unknown"] += 1
                        malformed_headers += 1
                    else:
                        packet_counts[header.packet_id] += 1

                    if not args.no_forward:
                        try:
                            send_sock.sendto(payload, (args.forward_host, args.forward_port))
                            forwarded_count += 1
                        except OSError:
                            forward_errors += 1

                    if args.flush_every > 0 and packet_count % args.flush_every == 0:
                        handle.flush()

                now_perf = time.perf_counter()
                if now_perf - last_status >= max(0.25, args.status_interval):
                    elapsed = max(1e-9, now_perf - started_perf)
                    interval = max(1e-9, now_perf - last_status)
                    interval_packets = packet_count - last_status_packets
                    current_pps = interval_packets / interval
                    total_pps = packet_count / elapsed
                    session_uid = latest_header.session_uid if latest_header.session_uid is not None else "-"
                    frame = latest_header.frame_identifier if latest_header.frame_identifier is not None else "-"
                    packet_name = PACKET_NAMES.get(latest_header.packet_id, str(latest_header.packet_id))
                    print(
                        f"packets={packet_count:7d}  rate={current_pps:6.1f} pps  "
                        f"avg={total_pps:6.1f} pps  latest={packet_name:<20} "
                        f"frame={frame} session={session_uid}"
                    )
                    last_status = now_perf
                    last_status_packets = packet_count

            handle.flush()
    except KeyboardInterrupt:
        stopped_reason = "keyboard_interrupt"
        print("\nStopping recorder...")
    finally:
        recv_sock.close()
        send_sock.close()

    duration_s = max(0.0, time.perf_counter() - started_perf)
    summary = {
        **metadata,
        "stopped_utc": utc_now_iso(),
        "stopped_reason": stopped_reason,
        "output": str(output),
        "duration_s": round(duration_s, 6),
        "packet_count": packet_count,
        "byte_count": byte_count,
        "average_packets_per_second": round(packet_count / duration_s, 3) if duration_s > 0 else 0.0,
        "forwarded_count": forwarded_count,
        "forward_errors": forward_errors,
        "malformed_headers": malformed_headers,
        "packet_counts": {
            PACKET_NAMES.get(key, str(key)): value
            for key, value in sorted(packet_counts.items(), key=lambda item: str(item[0]))
        },
        "latest_session_uid": latest_header.session_uid,
        "latest_frame_identifier": latest_header.frame_identifier,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\nRecording complete")
    print(f"Packets : {packet_count}")
    print(f"Duration: {duration_s:.2f} s")
    print(f"Raw file : {output}")
    print(f"Summary  : {summary_path}")
    if forward_errors:
        print(f"Warning: {forward_errors} forwarding errors occurred.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
