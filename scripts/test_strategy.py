from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE = "http://localhost:8000"


def get_json(path: str, method: str = "GET") -> dict:
    request = Request(f"{BASE}{path}", method=method)
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    try:
        decision = get_json("/api/strategy/recompute", method="POST")
        print("LIVE STRATEGY")
        print(json.dumps(decision, indent=2))

        questions = [
            "Engineer, should I box?",
            "Engineer, will I lose position if I box?",
            "Engineer, can I undercut the car ahead?",
            "Engineer, can I attack?",
            "Engineer, should I defend?",
            "Engineer, when should I deploy?",
            "Engineer, how much battery should I keep?",
            "Engineer, what should I focus on this lap?",
        ]
        for question in questions:
            payload = json.dumps({"text": question, "speak": False}).encode("utf-8")
            request = Request(
                f"{BASE}/api/radio/test",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
            print(f"\nDRIVER: {question}")
            print(f"ENGINEER: {result.get('response')}")
        return 0
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"Strategy API test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
