from __future__ import annotations

from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
os.chdir(BACKEND)
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.radio.stt import WhisperTranscriber  # noqa: E402


def main() -> int:
    settings = get_settings()
    print(f"Preparing faster-whisper model: {settings.radio_stt_model}")
    print(
        "Device/compute type: "
        f"{settings.radio_stt_device}/{settings.radio_stt_compute_type}"
    )
    transcriber = WhisperTranscriber(
        settings.radio_stt_model,
        device=settings.radio_stt_device,
        compute_type=settings.radio_stt_compute_type,
        language=settings.radio_language,
    )
    try:
        transcriber.warmup()
    except Exception as exc:
        print(f"Model preparation failed: {exc}")
        return 1
    print("Speech model is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
