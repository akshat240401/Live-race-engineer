from __future__ import annotations

from threading import Thread
from typing import Callable


class RadioFeedback:
    """Small non-blocking acknowledgement feedback helper.

    On Windows, ``winsound.Beep`` plays on the current default output device.
    Other platforms fall back to a terminal bell. A failure never stops the
    radio from opening its listening window.
    """

    def __init__(
        self,
        frequency_hz: int = 920,
        duration_ms: int = 95,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.frequency_hz = max(37, min(32767, int(frequency_hz)))
        self.duration_ms = max(30, min(1000, int(duration_ms)))
        self.on_error = on_error

    def beep(self) -> None:
        Thread(target=self._play, name="radio-ack-beep", daemon=True).start()

    def _play(self) -> None:
        try:
            import winsound

            winsound.Beep(self.frequency_hz, self.duration_ms)
        except Exception as exc:
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            if self.on_error is not None:
                self.on_error(f"Acknowledgement beep unavailable: {exc}")
