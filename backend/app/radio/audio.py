from __future__ import annotations

from array import array
from collections import deque
from dataclasses import dataclass
from math import sqrt
from queue import Empty, Full, Queue
from statistics import median
from threading import Event, Lock, Thread
from time import monotonic
from typing import Callable


@dataclass(slots=True)
class AudioConfig:
    sample_rate: int = 16_000
    frame_ms: int = 30
    vad_aggressiveness: int = 2
    end_silence_ms: int = 700
    command_end_silence_ms: int = 1050
    min_speech_ms: int = 250
    max_utterance_s: float = 15.0
    pre_roll_ms: int = 300
    input_device: str | int | None = None
    energy_gate_enabled: bool = True
    energy_multiplier: float = 1.8
    energy_floor_rms: int = 90


class MicrophoneListener:
    """Capture microphone audio and emit complete PCM16 speech utterances.

    The listener uses WebRTC VAD plus an optional calibrated energy gate. It
    applies a shorter end-of-speech delay while waiting for the wake phrase and
    a longer delay while the command/follow-up window is open.
    """

    def __init__(
        self,
        config: AudioConfig,
        on_utterance: Callable[[bytes], None],
        *,
        suppress_audio: Callable[[], bool] | None = None,
        conversation_active: Callable[[], bool] | None = None,
    ) -> None:
        self.config = config
        self.on_utterance = on_utterance
        self.suppress_audio = suppress_audio or (lambda: False)
        self.conversation_active = conversation_active or (lambda: False)

        self._stop = Event()
        self._queue: Queue[bytes] = Queue(maxsize=256)
        self._thread: Thread | None = None
        self._stream = None
        self._resolved_device: int | None = None
        self._resolved_device_name: str | None = None
        self.last_error: str | None = None
        self.running = False

        self._calibration_lock = Lock()
        self._calibration_until = 0.0
        self._calibration_samples: list[float] = []
        self._noise_floor_rms = float(max(1, config.energy_floor_rms))
        self._calibration_started_at: float | None = None
        self._calibration_finished_at: float | None = None

    @property
    def input_device_name(self) -> str | None:
        return self._resolved_device_name

    @property
    def noise_floor_rms(self) -> float:
        with self._calibration_lock:
            return round(self._noise_floor_rms, 1)

    @property
    def calibrating(self) -> bool:
        with self._calibration_lock:
            return monotonic() < self._calibration_until

    def calibration_status(self) -> dict[str, object]:
        with self._calibration_lock:
            remaining = max(0.0, self._calibration_until - monotonic())
            return {
                "calibrating": remaining > 0,
                "remaining_s": round(remaining, 1),
                "noise_floor_rms": round(self._noise_floor_rms, 1),
                "samples": len(self._calibration_samples),
                "started_at": self._calibration_started_at,
                "finished_at": self._calibration_finished_at,
            }

    def start_noise_calibration(self, duration_s: float = 5.0) -> dict[str, object]:
        if not self.running:
            raise RuntimeError("Microphone must be running before calibration")
        duration = max(2.0, min(15.0, float(duration_s)))
        with self._calibration_lock:
            self._calibration_samples = []
            self._calibration_started_at = monotonic()
            self._calibration_finished_at = None
            self._calibration_until = monotonic() + duration
        return self.calibration_status()

    def start(self) -> None:
        if self.running:
            return

        try:
            import sounddevice as sd
            import webrtcvad
        except Exception as exc:  # pragma: no cover - depends on local install
            self.last_error = (
                "Radio audio dependencies are unavailable. Install "
                f"sounddevice and webrtcvad-wheels. Details: {exc}"
            )
            raise RuntimeError(self.last_error) from exc

        self._resolved_device = self._resolve_device(sd, self.config.input_device)
        if self._resolved_device is not None:
            info = sd.query_devices(self._resolved_device, "input")
            self._resolved_device_name = str(info.get("name", self._resolved_device))
        else:
            try:
                info = sd.query_devices(kind="input")
                self._resolved_device_name = str(info.get("name", "default input"))
            except Exception:
                self._resolved_device_name = "default input"

        frame_samples = int(self.config.sample_rate * self.config.frame_ms / 1000)
        self._stop.clear()
        self._thread = Thread(
            target=self._worker,
            args=(webrtcvad.Vad(self.config.vad_aggressiveness),),
            name="hands-free-radio-audio",
            daemon=True,
        )
        self._thread.start()

        try:
            self._stream = sd.RawInputStream(
                samplerate=self.config.sample_rate,
                blocksize=frame_samples,
                device=self._resolved_device,
                channels=1,
                dtype="int16",
                callback=self._audio_callback,
            )
            self._stream.start()
            self.running = True
            self.last_error = None
        except Exception as exc:  # pragma: no cover - depends on local hardware
            self._stop.set()
            self.last_error = f"Could not open microphone: {exc}"
            raise RuntimeError(self.last_error) from exc

    def stop(self) -> None:
        self.running = False
        self._stop.set()
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        self._drain_queue()

    def _audio_callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        del frames, time_info
        if status:
            self.last_error = str(status)
        try:
            self._queue.put_nowait(bytes(indata))
        except Full:
            # Dropping a frame is preferable to blocking the audio callback.
            pass

    def _worker(self, vad) -> None:  # noqa: ANN001
        frame_ms = self.config.frame_ms
        pre_roll_frames = max(1, self.config.pre_roll_ms // frame_ms)
        min_speech_frames = max(1, self.config.min_speech_ms // frame_ms)
        max_frames = max(1, int(self.config.max_utterance_s * 1000 / frame_ms))

        pre_roll: deque[bytes] = deque(maxlen=pre_roll_frames)
        utterance: list[bytes] = []
        speech_frames = 0
        silence_frames = 0
        in_utterance = False
        current_end_silence_frames = max(1, self.config.end_silence_ms // frame_ms)

        while not self._stop.is_set():
            try:
                frame = self._queue.get(timeout=0.2)
            except Empty:
                self._finish_calibration_if_needed()
                continue

            rms = self._rms(frame)
            if self._collect_calibration_sample(rms):
                pre_roll.clear()
                utterance.clear()
                speech_frames = 0
                silence_frames = 0
                in_utterance = False
                continue

            if self.suppress_audio():
                pre_roll.clear()
                utterance.clear()
                speech_frames = 0
                silence_frames = 0
                in_utterance = False
                continue

            try:
                vad_speech = bool(vad.is_speech(frame, self.config.sample_rate))
            except Exception as exc:
                self.last_error = f"VAD error: {exc}"
                continue

            is_speech = vad_speech and self._passes_energy_gate(rms)
            if not vad_speech:
                self._adapt_noise_floor(rms)

            if not in_utterance:
                pre_roll.append(frame)
                if not is_speech:
                    continue
                in_utterance = True
                utterance = list(pre_roll)
                speech_frames = 1
                silence_frames = 0
                timeout_ms = (
                    self.config.command_end_silence_ms
                    if self.conversation_active()
                    else self.config.end_silence_ms
                )
                current_end_silence_frames = max(1, int(timeout_ms) // frame_ms)
                continue

            utterance.append(frame)
            if is_speech:
                speech_frames += 1
                silence_frames = 0
            else:
                silence_frames += 1

            timed_out = len(utterance) >= max_frames
            speech_ended = silence_frames >= current_end_silence_frames

            if not (timed_out or speech_ended):
                continue

            if speech_frames >= min_speech_frames:
                payload = b"".join(utterance)
                try:
                    self.on_utterance(payload)
                except Exception as exc:
                    self.last_error = f"Utterance callback failed: {exc}"

            pre_roll.clear()
            utterance.clear()
            speech_frames = 0
            silence_frames = 0
            in_utterance = False

    def _passes_energy_gate(self, rms: float) -> bool:
        if not self.config.energy_gate_enabled:
            return True
        threshold = max(
            float(self.config.energy_floor_rms),
            self.noise_floor_rms * max(1.0, self.config.energy_multiplier),
        )
        return rms >= threshold

    def _adapt_noise_floor(self, rms: float) -> None:
        if rms <= 0:
            return
        with self._calibration_lock:
            # Slow adaptation avoids a sudden engine-noise burst raising the gate.
            target = min(rms, self._noise_floor_rms * 2.5)
            self._noise_floor_rms = (self._noise_floor_rms * 0.995) + (target * 0.005)

    def _collect_calibration_sample(self, rms: float) -> bool:
        with self._calibration_lock:
            active = monotonic() < self._calibration_until
            if active:
                self._calibration_samples.append(rms)
                return True
        self._finish_calibration_if_needed()
        return False

    def _finish_calibration_if_needed(self) -> None:
        with self._calibration_lock:
            if self._calibration_until <= 0 or monotonic() < self._calibration_until:
                return
            samples = self._calibration_samples
            self._calibration_until = 0.0
            if samples:
                ordered = sorted(samples)
                upper_quartile = ordered[min(len(ordered) - 1, int(len(ordered) * 0.75))]
                self._noise_floor_rms = max(
                    float(self.config.energy_floor_rms),
                    median(samples),
                    upper_quartile * 0.85,
                )
            self._calibration_finished_at = monotonic()

    @staticmethod
    def _rms(frame: bytes) -> float:
        samples = array("h")
        samples.frombytes(frame)
        if not samples:
            return 0.0
        total = sum(int(sample) * int(sample) for sample in samples)
        return sqrt(total / len(samples))

    @staticmethod
    def list_input_devices() -> list[dict[str, object]]:
        try:
            import sounddevice as sd
        except Exception as exc:
            raise RuntimeError(f"sounddevice is unavailable: {exc}") from exc

        devices: list[dict[str, object]] = []
        for index, info in enumerate(sd.query_devices()):
            if int(info.get("max_input_channels", 0)) <= 0:
                continue
            devices.append(
                {
                    "index": index,
                    "name": str(info.get("name", index)),
                    "max_input_channels": int(info.get("max_input_channels", 0)),
                    "default_samplerate": float(info.get("default_samplerate", 0.0)),
                }
            )
        return devices

    @staticmethod
    def _resolve_device(sd, setting: str | int | None) -> int | None:  # noqa: ANN001
        if setting is None or setting == "":
            return None
        if isinstance(setting, int):
            return setting
        text = str(setting).strip()
        if not text:
            return None
        if text.lstrip("-").isdigit():
            return int(text)

        candidates = []
        for index, info in enumerate(sd.query_devices()):
            if int(info.get("max_input_channels", 0)) <= 0:
                continue
            name = str(info.get("name", ""))
            if text.casefold() in name.casefold():
                candidates.append((index, name))

        if not candidates:
            raise RuntimeError(f"No input device matched {text!r}")
        return candidates[0][0]

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                return
