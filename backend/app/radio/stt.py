from __future__ import annotations

from math import exp
from threading import Lock
from time import monotonic

from app.radio.models import TranscriptionResult


class WhisperTranscriber:
    """Lazy local speech-to-text powered by faster-whisper."""

    def __init__(
        self,
        model_size: str = "base.en",
        *,
        device: str = "auto",
        compute_type: str = "int8",
        language: str | None = "en",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language or None
        self._model = None
        self._lock = Lock()
        self.last_error: str | None = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def warmup(self) -> None:
        self._get_model()

    def transcribe(self, pcm16: bytes, sample_rate: int = 16_000) -> TranscriptionResult:
        if not pcm16:
            return TranscriptionResult(text="")
        if sample_rate != 16_000:
            raise ValueError("WhisperTranscriber expects 16 kHz mono PCM16 audio")

        try:
            import numpy as np
        except Exception as exc:
            raise RuntimeError(f"numpy is unavailable: {exc}") from exc

        started = monotonic()
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32)
        if audio.size == 0:
            return TranscriptionResult(text="")
        audio /= 32768.0

        model = self._get_model()
        try:
            segments, info = model.transcribe(
                audio,
                language=self.language,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=False,
                initial_prompt=(
                    "Formula One race engineer radio. Terms may include DRS, ERS, "
                    "tyres, pit, box, undercut, overtake, fuel, gap ahead, gap behind."
                ),
            )
            segment_list = list(segments)
            text = " ".join(segment.text.strip() for segment in segment_list).strip()

            confidence: float | None = None
            log_probs = [
                float(segment.avg_logprob)
                for segment in segment_list
                if getattr(segment, "avg_logprob", None) is not None
            ]
            if log_probs:
                confidence = max(0.0, min(1.0, exp(sum(log_probs) / len(log_probs))))

            self.last_error = None
            return TranscriptionResult(
                text=" ".join(text.split()),
                confidence=confidence,
                language=getattr(info, "language", self.language),
                duration_s=monotonic() - started,
            )
        except Exception as exc:
            self.last_error = str(exc)
            raise RuntimeError(f"Speech transcription failed: {exc}") from exc

    def _get_model(self):  # noqa: ANN201
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                )
                self.last_error = None
                return self._model
            except Exception as exc:
                self.last_error = str(exc)
                raise RuntimeError(
                    "Could not load the local Whisper model. The first run may need "
                    f"internet access to download {self.model_size!r}. Details: {exc}"
                ) from exc
