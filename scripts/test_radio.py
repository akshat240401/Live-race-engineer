from __future__ import annotations

import argparse
import json
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict | None = None,
) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exercise the Live Race Engineer hands-free radio API."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--speak", action="store_true")
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Run a five-second microphone noise calibration before tests.",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    questions = [
        "Engineer, radio check",
        "Engineer, what position am I?",
        "Engineer, what is the gap ahead?",
        "Engineer, how are my tyres?",
        "Engineer, how is the fuel?",
        "Engineer, how is the battery?",
        "Engineer, can I attack?",
        "Engineer, where am I losing time?",
    ]

    try:
        status = request_json(f"{base}/api/radio/status")
        print("STATUS")
        print(json.dumps(status, indent=2))

        if args.calibrate:
            query = urlencode({"duration_s": 5})
            result = request_json(
                f"{base}/api/radio/calibrate?{query}",
                method="POST",
            )
            print("\nCALIBRATION STARTED")
            print(json.dumps(result, indent=2))
            print("Stay quiet for five seconds...")
            sleep(5.5)
            print(json.dumps(request_json(f"{base}/api/radio/status"), indent=2))

        print("\nWAKE ACKNOWLEDGEMENT")
        wake = request_json(
            f"{base}/api/radio/test",
            method="POST",
            body={"text": "Engineer", "speak": args.speak},
        )
        print(json.dumps(wake, indent=2))

        for question in questions:
            result = request_json(
                f"{base}/api/radio/test",
                method="POST",
                body={"text": question, "speak": args.speak},
            )
            print(f"\nDRIVER: {question}")
            print(f"ENGINEER: {result.get('response')}")
            print(f"TOPIC: {result.get('topic')}")

        transcript = request_json(f"{base}/api/radio/transcript?limit=30")
        print("\nTRANSCRIPT")
        print(json.dumps(transcript, indent=2))
        return 0
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"Radio API test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
