from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5.0) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Watch Telemetry Correctness Phase 1 diagnostics"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000/api/telemetry/diagnostics",
    )
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete JSON payload each time.",
    )
    args = parser.parse_args()

    for index in range(max(1, args.count)):
        try:
            payload = fetch(args.url)
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            print(f"[{index + 1:03d}] diagnostics unavailable: {exc}")
        else:
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                state = payload.get("state", {})
                counts = state.get("counts", {})
                latency = state.get("latency", {})
                latest = latency.get("latest", {})
                print(
                    f"[{index + 1:03d}] "
                    f"status={state.get('status')} "
                    f"age={state.get('last_packet_age_s')}s "
                    f"rate={state.get('packet_rate_hz')}Hz "
                    f"accepted={counts.get('session_accepted')} "
                    f"rejected={counts.get('session_rejected')} "
                    f"dup={counts.get('duplicates')} "
                    f"ooo={counts.get('out_of_order')} "
                    f"latency={latest.get('end_to_end_ms')}ms "
                    f"stale={','.join(state.get('stale_groups', [])) or '-'}"
                )

        if index + 1 < args.count:
            time.sleep(max(0.1, args.interval))


if __name__ == "__main__":
    main()
