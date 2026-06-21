from __future__ import annotations

from itertools import count
from queue import Empty, Full, PriorityQueue
from threading import Event, RLock, Thread
from typing import Optional


class VoiceEngineer:
    """Priority-aware local text-to-speech worker.

    The public API remains compatible with the existing project while adding:
    priority ordering, speaking-state visibility, queue clearing, and best-effort
    interruption for critical calls and driver barge-in.
    """

    def __init__(
        self,
        enabled: bool = False,
        rate: int = 185,
        volume: float = 0.85,
    ) -> None:
        self.enabled = enabled
        self.rate = rate
        self.volume = volume
        self._queue: PriorityQueue[tuple[int, int, str, bool]] = PriorityQueue(maxsize=30)
        self._sequence = count()
        self._stop = Event()
        self._speaking = Event()
        self._thread: Optional[Thread] = None
        self._engine = None
        self._engine_lock = RLock()
        self._current_text: str | None = None
        self.last_error: str | None = None

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    @property
    def current_text(self) -> str | None:
        return self._current_text

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(
            target=self._run,
            name="voice-engineer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.interrupt()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.interrupt()
            self._drain_queue()

    def speak(
        self,
        text: str,
        *,
        force: bool = False,
        priority: int = 50,
        interrupt: bool = False,
    ) -> bool:
        clean = " ".join(text.strip().split())
        if not clean:
            return False
        if not force and not self.enabled:
            return False
        if interrupt:
            self.interrupt()
        try:
            self._queue.put_nowait((-int(priority), next(self._sequence), clean, force))
            return True
        except Full:
            self.last_error = "Voice queue is full"
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def interrupt(self) -> None:
        """Best-effort interruption of the active pyttsx3 utterance."""
        with self._engine_lock:
            engine = self._engine
            if engine and engine is not False:
                try:
                    engine.stop()
                except Exception as exc:
                    self.last_error = str(exc)

    def clear_queue(self) -> None:
        self._drain_queue()

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                return

    def _init_engine(self):  # noqa: ANN201
        with self._engine_lock:
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
                _, _, text, force = self._queue.get(timeout=0.2)
            except Empty:
                continue

            if not force and not self.enabled:
                continue

            engine = self._init_engine()
            if not engine:
                continue

            self._current_text = text
            self._speaking.set()
            try:
                # Do not hold the engine lock while speaking. This allows a
                # driver question or critical call to invoke ``interrupt()``.
                engine.say(text)
                engine.runAndWait()
                self.last_error = None
            except Exception as exc:
                self.last_error = str(exc)
                with self._engine_lock:
                    self._engine = None
            finally:
                self._current_text = None
                self._speaking.clear()
