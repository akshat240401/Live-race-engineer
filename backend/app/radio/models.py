from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from time import time
from typing import Any


class RadioMode(str, Enum):
    MINIMAL = "minimal"
    RACE = "race"
    COACHING = "coaching"


class RadioState(str, Enum):
    DISABLED = "disabled"
    STARTING = "starting"
    STANDBY = "standby"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    CALIBRATING = "calibrating"
    ERROR = "error"


@dataclass(slots=True)
class TranscriptEntry:
    id: int
    timestamp: float
    speaker: str
    text: str
    source: str
    topic: str | None = None
    confidence: float | None = None
    priority: int = 50
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IntentResult:
    handled: bool
    text: str = ""
    topic: str | None = None
    priority: int = 100
    action: str | None = None
    mode: RadioMode | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    confidence: float | None = None
    language: str | None = None
    duration_s: float = 0.0


@dataclass(slots=True)
class RadioStatus:
    enabled: bool
    running: bool
    state: RadioState
    mode: RadioMode
    muted: bool
    conversation_open: bool
    awaiting_command: bool
    command_timeout_s: float
    command_time_remaining_s: float
    wake_phrases: list[str]
    input_device: str | int | None
    input_device_name: str | None
    stt_model: str
    stt_ready: bool
    llm_enabled: bool
    barge_in_enabled: bool
    ack_mode: str
    response_style: str
    noise_floor_rms: float
    calibrating: bool
    calibration_remaining_s: float
    pending_auto_messages: int
    pending_confirmation: str | None = None
    last_heard: str | None = None
    last_normalized: str | None = None
    last_response: str | None = None
    last_error: str | None = None
    last_activity_at: float | None = None
    transcript_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["mode"] = self.mode.value
        data["timestamp"] = time()
        return data
