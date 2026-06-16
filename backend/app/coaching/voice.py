from __future__ import annotations

from queue import Queue, Empty
from threading import Thread, Event
from typing import Optional


class VoiceEngineer:
    def __init__(self, enabled: bool = False, rate: int = 185, volume: float = 0.85) -> None:
        self.enabled = enabled
        self.rate = rate
        self.volume = volume
        self._queue: Queue[str] = Queue(maxsize=10)
        self._stop = Event()
        self._thread: Optional[Thread] = None
        self._engine = None
        self.last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="voice-engineer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self._drain_queue()

    def speak(self, text: str, *, force: bool = False) -> bool:
        text = " ".join(text.strip().split())
        if not text:
            return False
        if not force and not self.enabled:
            return False

        try:
            self._queue.put_nowait(text)
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                return

    def _init_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            self._engine.setProperty("volume", self.volume)
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
            self._engine = False
        return self._engine

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                text = self._queue.get(timeout=0.2)
            except Empty:
                continue

            engine = self._init_engine()
            if not engine:
                continue

            try:
                engine.say(text)
                engine.runAndWait()
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                # Reset the engine so the next line gets a fresh init.
                self._engine = None