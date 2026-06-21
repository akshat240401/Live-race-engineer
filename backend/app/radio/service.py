from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
from threading import Event, Lock, Thread
from time import sleep, time
from typing import Any

from app.coaching.voice import VoiceEngineer
from app.core.config import Settings
from app.radio.audio import AudioConfig, MicrophoneListener
from app.radio.feedback import RadioFeedback
from app.radio.intent_router import LiveIntentRouter
from app.radio.llm import LiveLLMResponder
from app.radio.models import (
    IntentResult,
    RadioMode,
    RadioState,
    RadioStatus,
    TranscriptEntry,
)
from app.radio.profile import DriverProfileStore
from app.radio.stt import WhisperTranscriber
from app.radio.terminology import normalize_racing_transcript, normalized_message_key
from app.strategy.engine import LiveStrategicEngineer
from app.recording.session_recorder import SessionRecorder
from app.telemetry.state import LiveTelemetryState


MODE_AUTO_PRIORITY = {
    RadioMode.MINIMAL: 88,
    RadioMode.RACE: 65,
    RadioMode.COACHING: 0,
}


@dataclass(slots=True)
class PendingAutomaticMessage:
    text: str
    priority: int
    category: str
    created_at: float
    key: str


class HandsFreeRadioService:
    """Two-way hands-free race radio with wake acknowledgement and coaching.

    The service combines local microphone capture, adaptive speech segmentation,
    racing-vocabulary normalization, deterministic telemetry tools, optional LLM
    answers, duplicate suppression, and corner-safe automatic message delivery.
    """

    def __init__(
        self,
        settings: Settings,
        state: LiveTelemetryState,
        voice: VoiceEngineer,
        recorder: SessionRecorder,
    ) -> None:
        self.settings = settings
        self.telemetry_state = state
        self.voice = voice
        self.recorder = recorder

        self.enabled = settings.radio_enabled
        self.running = False
        self._state = RadioState.DISABLED
        self._muted_auto = False
        self._conversation_until = 0.0
        self._awaiting_command_until = 0.0
        self._last_activity_at: float | None = None
        self._last_heard: str | None = None
        self._last_normalized: str | None = None
        self._last_response: str | None = None
        self._last_topic: str | None = None
        self._last_error: str | None = None
        self._entry_id = 0
        self._lock = Lock()
        self._processing_lock = Lock()
        self._audio_task_pending = Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radio-ai")
        self._transcript: deque[TranscriptEntry] = deque(
            maxlen=max(20, settings.radio_transcript_limit)
        )
        self._conversation: deque[dict[str, str]] = deque(maxlen=12)
        self._wake_phrases = [
            phrase.strip().casefold()
            for phrase in settings.radio_wake_phrases.split(",")
            if phrase.strip()
        ] or ["engineer"]

        self._pending_control: IntentResult | None = None
        self._pending_control_label: str | None = None

        self._auto_lock = Lock()
        self._pending_auto: deque[PendingAutomaticMessage] = deque()
        self._pending_auto_keys: set[str] = set()
        self._last_auto_at = 0.0
        self._last_auto_by_key: dict[str, float] = {}
        self._last_auto_by_category: dict[str, float] = {}
        self._scheduler_stop = Event()
        self._scheduler_thread: Thread | None = None
        self._last_strategy_eval_at = 0.0

        self.profile = DriverProfileStore(settings.radio_profile_path)
        try:
            fallback_mode = RadioMode(settings.radio_mode.casefold())
        except ValueError:
            fallback_mode = RadioMode.RACE
        self.mode = self.profile.mode(fallback_mode)

        self.strategy = LiveStrategicEngineer(settings)
        self.router = LiveIntentRouter(self.strategy)
        self.transcriber = WhisperTranscriber(
            settings.radio_stt_model,
            device=settings.radio_stt_device,
            compute_type=settings.radio_stt_compute_type,
            language=settings.radio_language,
        )
        self.llm = LiveLLMResponder(
            enabled=(settings.live_llm_enabled or settings.llm_enabled),
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_s=settings.llm_timeout_s,
            max_words=settings.live_llm_max_words,
        )
        self.feedback = RadioFeedback(
            settings.radio_ack_beep_frequency_hz,
            settings.radio_ack_beep_duration_ms,
            on_error=lambda message: self._set_error(message, keep_state=True),
        )
        self.microphone = self._build_microphone()
        self.log_root = Path(os.path.expandvars(settings.radio_log_dir)).expanduser().resolve()
        self.log_root.mkdir(parents=True, exist_ok=True)

        ack_mode = settings.radio_ack_mode.strip().casefold()
        self.ack_mode = ack_mode if ack_mode in {"beep", "voice", "both", "silent"} else "beep"
        response_style = settings.radio_response_style.strip().casefold()
        self.response_style = (
            response_style if response_style in {"concise", "normal", "detailed"} else "concise"
        )

    def start(self) -> None:
        self.running = True
        self._scheduler_stop.clear()
        if not self._scheduler_thread or not self._scheduler_thread.is_alive():
            self._scheduler_thread = Thread(
                target=self._dispatch_loop,
                name="radio-auto-dispatch",
                daemon=True,
            )
            self._scheduler_thread.start()
        if self.settings.radio_preload_stt:
            self._executor.submit(self._warm_stt)
        if self.enabled:
            self._start_microphone()
        else:
            self._set_state(RadioState.DISABLED)

    def stop(self) -> None:
        self.running = False
        self._scheduler_stop.set()
        self.microphone.stop()
        self._set_state(RadioState.DISABLED)
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=1.5)
        self._scheduler_thread = None
        self._executor.shutdown(wait=False, cancel_futures=True)

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        self.enabled = bool(enabled)
        if self.enabled:
            self._start_microphone()
        else:
            self.microphone.stop()
            self._awaiting_command_until = 0.0
            self._conversation_until = 0.0
            self._set_state(RadioState.DISABLED)
        return self.status()

    def set_mode(self, mode: str | RadioMode) -> dict[str, Any]:
        selected = mode if isinstance(mode, RadioMode) else RadioMode(str(mode).casefold())
        self.mode = selected
        self.profile.set_mode(selected)
        self._add_entry(
            "system",
            f"Radio mode changed to {selected.value}.",
            source="control",
            topic="radio",
        )
        return self.status()

    def open_conversation(self, *, acknowledge: bool = True) -> dict[str, Any]:
        self._awaiting_command_until = time() + self.settings.radio_command_timeout_s
        self._conversation_until = 0.0
        self._set_state(RadioState.LISTENING)
        if acknowledge:
            self._play_acknowledgement(speak=True)
        return self.status()

    def calibrate_noise(self, duration_s: float | None = None) -> dict[str, Any]:
        duration = duration_s or self.settings.radio_noise_calibration_s
        result = self.microphone.start_noise_calibration(duration)
        self._set_state(RadioState.CALIBRATING)
        self._add_entry(
            "system",
            f"Microphone noise calibration started for {float(duration):.0f} seconds.",
            source="calibration",
            topic="radio",
        )
        return {"ok": True, "calibration": result, "status": self.status()}

    def resume_updates(self) -> dict[str, Any]:
        self._muted_auto = False
        return self.status()

    def quiet_updates(self) -> dict[str, Any]:
        self._muted_auto = True
        return self.status()

    def repeat_last(self, *, speak: bool = True) -> dict[str, Any]:
        response = self._last_response or "There is no previous engineer message to repeat."
        if speak:
            self.voice.speak(response, priority=100, interrupt=True)
        self._add_entry(
            "engineer",
            response,
            source="repeat",
            topic="radio",
            priority=100,
        )
        return {"ok": True, "response": response, "status": self.status()}

    def process_text(
        self,
        text: str,
        *,
        source: str = "api",
        bypass_wake: bool = False,
        speak: bool = True,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        with self._processing_lock:
            return self._process_text_locked(
                text,
                source=source,
                bypass_wake=bypass_wake,
                speak=speak,
                confidence=confidence,
            )

    def enqueue_automatic(
        self,
        text: str,
        *,
        priority: int = 50,
        category: str | None = None,
    ) -> bool:
        clean = " ".join(str(text).split())
        if not clean:
            return False
        if self._muted_auto and priority < 95:
            return False
        if priority < MODE_AUTO_PRIORITY[self.mode]:
            return False

        category_name = (category or "coaching").strip().casefold()
        key = f"{category_name}:{normalized_message_key(clean)}"
        now = time()
        critical = self.settings.radio_critical_override and priority >= 95

        with self._auto_lock:
            if not critical and self._is_duplicate_auto_locked(key, category_name, now):
                return False

        if critical:
            return self._deliver_automatic(clean, priority, category_name, key)

        if self._should_delay_automatic(now):
            self._queue_automatic(clean, priority, category_name, key, now)
            return True

        return self._deliver_automatic(clean, priority, category_name, key)

    def transcript(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._transcript)
        if limit > 0:
            items = items[-limit:]
        return [entry.to_dict() for entry in items]

    def status(self) -> dict[str, Any]:
        self._refresh_deadlines()
        calibration = self.microphone.calibration_status()
        with self._lock:
            base_state = self._state
            last_heard = self._last_heard
            last_normalized = self._last_normalized
            last_response = self._last_response
            last_error = self._last_error or self.microphone.last_error or self.transcriber.last_error
            last_activity = self._last_activity_at
            count = len(self._transcript)

        now = time()
        awaiting_command = now < self._awaiting_command_until
        conversation_open = self._conversation_active()
        if not self.enabled:
            state = RadioState.DISABLED
        elif bool(calibration["calibrating"]):
            state = RadioState.CALIBRATING
        else:
            state = RadioState.SPEAKING if self.voice.is_speaking else base_state
        if self.enabled and self.running and state == RadioState.LISTENING and not conversation_open:
            state = RadioState.STANDBY

        with self._auto_lock:
            pending_count = len(self._pending_auto)

        return RadioStatus(
            enabled=self.enabled,
            running=self.running and self.microphone.running,
            state=state,
            mode=self.mode,
            muted=self._muted_auto,
            conversation_open=conversation_open,
            awaiting_command=awaiting_command,
            command_timeout_s=self.settings.radio_command_timeout_s,
            command_time_remaining_s=round(max(0.0, self._awaiting_command_until - now), 1),
            wake_phrases=list(self._wake_phrases),
            input_device=self.settings.radio_input_device or None,
            input_device_name=self.microphone.input_device_name,
            stt_model=self.settings.radio_stt_model,
            stt_ready=self.transcriber.ready,
            llm_enabled=self.llm.enabled,
            barge_in_enabled=self.settings.radio_barge_in_enabled,
            ack_mode=self.ack_mode,
            response_style=self.response_style,
            noise_floor_rms=float(calibration["noise_floor_rms"]),
            calibrating=bool(calibration["calibrating"]),
            calibration_remaining_s=float(calibration["remaining_s"]),
            pending_auto_messages=pending_count,
            pending_confirmation=self._pending_control_label,
            last_heard=last_heard,
            last_normalized=last_normalized,
            last_response=last_response,
            last_error=last_error,
            last_activity_at=last_activity,
            transcript_count=count,
        ).to_dict()

    def decision(self, *, recompute: bool = False) -> dict[str, Any]:
        if recompute or not self.strategy.latest().connected:
            self.strategy.evaluate(self.telemetry_state.snapshot())
        return self.strategy.latest_dict()

    def list_input_devices(self) -> list[dict[str, object]]:
        return MicrophoneListener.list_input_devices()

    def reset_conversation(self) -> None:
        self._conversation_until = 0.0
        self._awaiting_command_until = 0.0
        self._conversation.clear()
        self._pending_control = None
        self._pending_control_label = None
        if self.enabled:
            self._set_state(RadioState.STANDBY)

    def _build_microphone(self) -> MicrophoneListener:
        config = AudioConfig(
            sample_rate=self.settings.radio_sample_rate,
            frame_ms=self.settings.radio_frame_ms,
            vad_aggressiveness=self.settings.radio_vad_aggressiveness,
            end_silence_ms=self.settings.radio_end_silence_ms,
            command_end_silence_ms=self.settings.radio_command_end_silence_ms,
            min_speech_ms=self.settings.radio_min_speech_ms,
            max_utterance_s=self.settings.radio_max_utterance_s,
            pre_roll_ms=self.settings.radio_pre_roll_ms,
            input_device=self.settings.radio_input_device or None,
            energy_gate_enabled=self.settings.radio_energy_gate_enabled,
            energy_multiplier=self.settings.radio_energy_multiplier,
            energy_floor_rms=self.settings.radio_energy_floor_rms,
        )
        return MicrophoneListener(
            config,
            self._on_utterance,
            suppress_audio=self._suppress_audio,
            conversation_active=self._conversation_active,
        )

    def _start_microphone(self) -> None:
        if self.microphone.running:
            self._set_state(RadioState.STANDBY)
            return
        self._set_state(RadioState.STARTING)
        try:
            self.microphone.start()
            self._clear_error()
            self._set_state(RadioState.STANDBY)
        except Exception as exc:
            self._set_error(str(exc))

    def _warm_stt(self) -> None:
        try:
            self.transcriber.warmup()
        except Exception as exc:
            self._set_error(str(exc), keep_state=True)

    def _on_utterance(self, pcm16: bytes) -> None:
        if not self.enabled or not self.running or self.microphone.calibrating:
            return
        if self._processing_lock.locked() or self._audio_task_pending.is_set():
            return
        self._audio_task_pending.set()
        self._executor.submit(self._run_audio_task, pcm16)

    def _run_audio_task(self, pcm16: bytes) -> None:
        try:
            self._process_audio(pcm16)
        finally:
            self._audio_task_pending.clear()

    def _process_audio(self, pcm16: bytes) -> None:
        with self._processing_lock:
            self._set_state(RadioState.TRANSCRIBING)
            try:
                result = self.transcriber.transcribe(
                    pcm16,
                    sample_rate=self.settings.radio_sample_rate,
                )
            except Exception as exc:
                self._set_error(str(exc))
                return

            if not result.text:
                self._set_idle_state()
                return
            if (
                result.confidence is not None
                and result.confidence < self.settings.radio_min_confidence
            ):
                self._set_error(
                    f"Low speech confidence ({result.confidence:.2f}); command ignored.",
                    keep_state=True,
                )
                self._set_idle_state()
                return

            self._process_text_locked(
                result.text,
                source="microphone",
                bypass_wake=False,
                speak=True,
                confidence=result.confidence,
            )

    def _process_text_locked(
        self,
        text: str,
        *,
        source: str,
        bypass_wake: bool,
        speak: bool,
        confidence: float | None,
    ) -> dict[str, Any]:
        heard = " ".join(str(text).strip().split())
        if not heard:
            self._set_idle_state()
            return {"ok": False, "ignored": True, "reason": "empty transcript"}

        normalized = normalize_racing_transcript(heard)
        if self.voice.is_speaking and self.settings.radio_barge_in_enabled:
            if self._looks_like_echo(normalized):
                self._set_idle_state()
                return {"ok": False, "ignored": True, "reason": "probable speaker echo"}
            self.voice.interrupt()

        conversation_open = self._conversation_active()
        wake_detected, command = self._extract_wake_command(normalized)
        if bypass_wake:
            wake_detected = True
            command = normalized
        elif conversation_open:
            command = normalized

        if not wake_detected and not conversation_open:
            self._set_idle_state()
            return {"ok": False, "ignored": True, "reason": "wake phrase not detected"}

        self._last_heard = heard
        self._last_normalized = normalized
        self._last_activity_at = time()
        self._clear_error()

        if not command:
            self._add_entry(
                "driver",
                heard,
                source=source,
                topic="wake",
                confidence=confidence,
                priority=100,
                metadata={"normalized": normalized},
            )
            self._awaiting_command_until = time() + self.settings.radio_command_timeout_s
            self._conversation_until = 0.0
            self._set_state(RadioState.LISTENING)
            response = self._play_acknowledgement(speak=speak)
            return {
                "ok": True,
                "heard": heard,
                "command": "",
                "response": response,
                "ack_mode": self.ack_mode,
                "status": self.status(),
            }

        self._awaiting_command_until = 0.0
        self._conversation_until = time() + self.settings.radio_followup_window_s
        self._set_state(RadioState.THINKING)
        self._add_entry(
            "driver",
            command,
            source=source,
            topic=None,
            confidence=confidence,
            priority=100,
            metadata={"raw_transcript": heard, "normalized": normalized},
        )

        confirmation = self._handle_pending_confirmation(command)
        if confirmation is not None:
            return self._finalize_driver_response(
                command,
                confirmation,
                topic="radio",
                priority=100,
                speak=speak,
                heard=heard,
                confidence=confidence,
            )

        recalled = self._recall_previous(command)
        if recalled is not None:
            return self._finalize_driver_response(
                command,
                recalled,
                topic="history",
                priority=100,
                speak=speak,
                heard=heard,
                confidence=confidence,
            )

        snapshot = self.telemetry_state.snapshot()
        routed_command = self._contextualize_command(command)
        result = self.router.route(routed_command, snapshot)

        if (
            result.handled
            and result.action == "quiet"
            and self.settings.radio_confirm_control_actions
        ):
            self._pending_control = result
            self._pending_control_label = "radio silence"
            return self._finalize_driver_response(
                command,
                "Confirm radio silence.",
                topic="radio",
                priority=100,
                speak=speak,
                heard=heard,
                confidence=confidence,
            )

        response = self._apply_intent_action(result)
        topic = result.topic
        priority = result.priority

        if not result.handled:
            response = self.llm.answer(
                command,
                snapshot,
                list(self._conversation),
                self.profile.context(),
            )
            topic = "llm"
            priority = 100
            if not response:
                response = (
                    "I do not have a grounded answer yet. Ask about position, gaps, "
                    "tyres, fuel, battery, damage, box timing, attack, deployment, or driving loss."
                )
                topic = "fallback"
                if self.llm.last_error:
                    self._set_error(
                        f"Live LLM unavailable: {self.llm.last_error}",
                        keep_state=True,
                    )

        return self._finalize_driver_response(
            command,
            response,
            topic=topic,
            priority=priority,
            speak=speak,
            heard=heard,
            confidence=confidence,
        )

    def _finalize_driver_response(
        self,
        command: str,
        response: str,
        *,
        topic: str | None,
        priority: int,
        speak: bool,
        heard: str,
        confidence: float | None,
    ) -> dict[str, Any]:
        formatted = self._format_response(response, priority=priority)
        self.profile.record_question(topic)
        if topic and topic not in {"radio", "wake", "history", "fallback"}:
            self._last_topic = topic
        self._conversation.append({"role": "driver", "content": command})
        self._conversation.append({"role": "engineer", "content": formatted})
        self._last_response = formatted
        self._last_activity_at = time()
        self._conversation_until = time() + self.settings.radio_followup_window_s
        self._add_entry(
            "engineer",
            formatted,
            source="live-radio",
            topic=topic,
            priority=priority,
        )
        if speak and formatted:
            self.voice.speak(formatted, priority=priority, interrupt=True)
        self._set_state(RadioState.LISTENING)
        return {
            "ok": True,
            "heard": heard,
            "command": command,
            "response": formatted,
            "topic": topic,
            "confidence": confidence,
            "status": self.status(),
        }

    def _play_acknowledgement(self, *, speak: bool) -> str:
        response = self.settings.radio_ack_text.strip() or "Listening."
        if self.ack_mode in {"beep", "both"}:
            self.feedback.beep()
        if speak and self.ack_mode in {"voice", "both"}:
            self.voice.speak(response, priority=105, interrupt=True)
        display = response if self.ack_mode != "silent" else "Listening window opened."
        self._add_entry(
            "engineer",
            display,
            source="wake",
            topic="wake",
            priority=100,
            metadata={"ack_mode": self.ack_mode},
        )
        return display

    def _handle_pending_confirmation(self, command: str) -> str | None:
        pending = self._pending_control
        if pending is None:
            return None
        normalized = command.casefold().strip(" .!?")
        if normalized in {"confirm", "confirmed", "yes", "do it", "copy"}:
            self._pending_control = None
            label = self._pending_control_label or "action"
            self._pending_control_label = None
            response = self._apply_intent_action(pending)
            return response or f"Confirmed {label}."
        if normalized in {"cancel", "negative", "no", "never mind", "nevermind"}:
            self._pending_control = None
            self._pending_control_label = None
            return "Cancelled."
        return f"Say confirm or cancel for {self._pending_control_label or 'that action'}."

    def _recall_previous(self, command: str) -> str | None:
        lowered = command.casefold()
        if not (
            "what did you say" in lowered
            or "repeat what you said" in lowered
            or lowered.startswith("repeat about")
        ):
            return None
        topic_words = [
            word
            for word in re.findall(r"[a-z0-9]+", lowered)
            if word not in {
                "what", "did", "you", "say", "repeat", "about", "the", "last", "message"
            }
        ]
        with self._lock:
            entries = list(self._transcript)
        for entry in reversed(entries):
            if entry.speaker != "engineer" or entry.source == "wake":
                continue
            haystack = f"{entry.topic or ''} {entry.text}".casefold()
            if not topic_words or any(word in haystack for word in topic_words):
                return entry.text
        return "I do not have a matching recent engineer message."

    def _contextualize_command(self, command: str) -> str:
        """Attach the last topic to short pronoun-heavy follow-up questions."""
        if not self._last_topic:
            return command
        lowered = command.casefold()
        explicit_terms = re.search(
            r"\b(position|gap|car|tyres?|tires?|fuel|battery|ers|damage|wing|pit|box|attack|defend|lap|sector)\b",
            lowered,
        )
        if explicit_terms:
            return command
        followup = re.search(
            r"\b(it|they|them|that|those|can i|should i|what next|reach the end|make the end)\b",
            lowered,
        )
        if not followup and len(command.split()) > 6:
            return command
        topic_hint = {
            "tyres": "tyres",
            "fuel": "fuel",
            "ers": "battery ERS",
            "damage": "damage",
            "strategy": "box strategy",
            "racecraft": "attack racecraft",
            "gap_ahead": "gap ahead",
            "gap_behind": "gap behind",
            "position": "position",
            "coaching": "driving advice",
        }.get(self._last_topic, self._last_topic.replace("_", " "))
        return f"{topic_hint} {command}"

    def _apply_intent_action(self, result: IntentResult) -> str:
        if not result.handled:
            return ""
        if result.action == "repeat":
            return self._last_response or "There is no previous engineer message to repeat."
        if result.action == "quiet":
            self._muted_auto = True
        elif result.action == "resume":
            self._muted_auto = False
        elif result.action == "mode" and result.mode is not None:
            self.mode = result.mode
            self.profile.set_mode(result.mode)
        return result.text

    def _extract_wake_command(self, text: str) -> tuple[bool, str]:
        normalized = text.casefold()
        for phrase in sorted(self._wake_phrases, key=len, reverse=True):
            match = re.search(rf"\b{re.escape(phrase)}\b", normalized)
            if not match:
                continue
            command = text[match.end() :].strip(" ,.!?:;-\t")
            return True, command
        return False, text

    def _format_response(self, text: str, *, priority: int) -> str:
        clean = " ".join(str(text or "").split())
        if not clean or self.response_style == "detailed":
            return clean

        limit = max(8, int(self.settings.radio_max_response_words))
        if self.response_style == "normal":
            limit = max(limit, 42)
        elif priority >= 105:
            limit = max(limit, 30)

        words = clean.split()
        if len(words) <= limit:
            return clean

        if self.response_style == "concise":
            sentences = re.split(r"(?<=[.!?])\s+", clean)
            candidate = sentences[0]
            if len(candidate.split()) < 8 and len(sentences) > 1:
                candidate = f"{candidate} {sentences[1]}"
            if len(candidate.split()) <= limit:
                return candidate

        trimmed = " ".join(words[:limit]).rstrip(" ,;:-")
        return f"{trimmed}."

    def _looks_like_echo(self, heard: str) -> bool:
        spoken = self.voice.current_text or self._last_response
        if not spoken:
            return False
        a = re.sub(r"[^a-z0-9 ]+", "", heard.casefold())
        b = re.sub(r"[^a-z0-9 ]+", "", spoken.casefold())
        if not a or not b:
            return False
        return SequenceMatcher(None, a, b).ratio() >= self.settings.radio_echo_similarity

    def _suppress_audio(self) -> bool:
        return self.voice.is_speaking and not self.settings.radio_barge_in_enabled

    def _conversation_active(self) -> bool:
        now = time()
        return now < self._awaiting_command_until or now < self._conversation_until

    def _refresh_deadlines(self) -> None:
        now = time()
        expired = False
        if self._awaiting_command_until and now >= self._awaiting_command_until:
            self._awaiting_command_until = 0.0
            expired = True
        if self._conversation_until and now >= self._conversation_until:
            self._conversation_until = 0.0
            self._pending_control = None
            self._pending_control_label = None
            expired = True
        if expired and self.enabled and not self.voice.is_speaking:
            self._set_state(RadioState.STANDBY)

    def _should_delay_automatic(self, now: float) -> bool:
        if self._conversation_active() or self.voice.is_speaking:
            return True
        if now - self._last_auto_at < self.settings.radio_min_auto_message_interval_s:
            return True
        if self.settings.radio_corner_safe_delivery:
            return not self._safe_for_message()
        return False

    def _safe_for_message(self) -> bool:
        snapshot = self.telemetry_state.snapshot()
        if not snapshot.connected:
            return True
        brake = float(snapshot.brake or 0.0)
        steer = abs(float(snapshot.steer or 0.0))
        lateral_g = abs(float(snapshot.g_force_lateral or 0.0))
        longitudinal_g = abs(float(snapshot.g_force_longitudinal or 0.0))
        return brake < 0.18 and steer < 0.28 and lateral_g < 0.85 and longitudinal_g < 1.1

    def _is_duplicate_auto_locked(self, key: str, category: str, now: float) -> bool:
        if key in self._pending_auto_keys:
            return True
        last_key = self._last_auto_by_key.get(key, 0.0)
        if now - last_key < self.settings.radio_duplicate_cooldown_s:
            return True
        last_category = self._last_auto_by_category.get(category, 0.0)
        return now - last_category < self.settings.radio_category_cooldown_s

    def _queue_automatic(
        self,
        text: str,
        priority: int,
        category: str,
        key: str,
        now: float,
    ) -> None:
        with self._auto_lock:
            if key in self._pending_auto_keys:
                return
            while len(self._pending_auto) >= 12:
                removed = self._pending_auto.popleft()
                self._pending_auto_keys.discard(removed.key)
            self._pending_auto.append(
                PendingAutomaticMessage(text, priority, category, now, key)
            )
            self._pending_auto_keys.add(key)

    def _deliver_automatic(
        self,
        text: str,
        priority: int,
        category: str,
        key: str,
    ) -> bool:
        now = time()
        formatted = self._format_response(text, priority=priority)
        self.profile.record_coaching_category(category)
        self._last_response = formatted
        self._last_activity_at = now
        with self._auto_lock:
            self._last_auto_at = now
            self._last_auto_by_key[key] = now
            self._last_auto_by_category[category] = now
            self._pending_auto_keys.discard(key)
        self._add_entry(
            "engineer",
            formatted,
            source="automatic",
            topic=category,
            priority=priority,
        )
        return self.voice.speak(
            formatted,
            priority=priority,
            interrupt=priority >= 95,
        )

    def _dispatch_loop(self) -> None:
        while not self._scheduler_stop.is_set():
            self._refresh_deadlines()
            pending: PendingAutomaticMessage | None = None
            now = time()
            if (
                self.enabled
                and self.settings.strategy_enabled
                and now - self._last_strategy_eval_at
                >= self.settings.strategy_evaluation_interval_s
            ):
                self._last_strategy_eval_at = now
                try:
                    self.strategy.evaluate(self.telemetry_state.snapshot())
                    call = self.strategy.pop_automatic_call()
                    if call and self.settings.strategy_auto_calls:
                        self.enqueue_automatic(
                            call.text,
                            priority=call.priority,
                            category=call.category,
                        )
                except Exception as exc:
                    self._set_error(
                        f"Strategic engineer evaluation failed: {exc}",
                        keep_state=True,
                    )
            with self._auto_lock:
                while self._pending_auto:
                    candidate = self._pending_auto[0]
                    if now - candidate.created_at > self.settings.radio_pending_message_max_wait_s:
                        expired = self._pending_auto.popleft()
                        self._pending_auto_keys.discard(expired.key)
                        continue
                    pending = candidate
                    break
            if pending and not self._should_delay_automatic(now):
                with self._auto_lock:
                    if self._pending_auto and self._pending_auto[0].key == pending.key:
                        self._pending_auto.popleft()
                self._deliver_automatic(
                    pending.text,
                    pending.priority,
                    pending.category,
                    pending.key,
                )
            sleep(0.2)

    def _add_entry(
        self,
        speaker: str,
        text: str,
        *,
        source: str,
        topic: str | None,
        confidence: float | None = None,
        priority: int = 50,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptEntry:
        clean = " ".join(str(text).split())
        with self._lock:
            self._entry_id += 1
            entry = TranscriptEntry(
                id=self._entry_id,
                timestamp=time(),
                speaker=speaker,
                text=clean,
                source=source,
                topic=topic,
                confidence=confidence,
                priority=priority,
                metadata=metadata or {},
            )
            self._transcript.append(entry)
        self._append_log(entry)
        return entry

    def _append_log(self, entry: TranscriptEntry) -> None:
        active_session = self.recorder.active_session_id
        if active_session:
            path = self.recorder.root / active_session / "radio.jsonl"
        else:
            path = self.log_root / "radio.jsonl"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            self._set_error(f"Could not save radio transcript: {exc}", keep_state=True)

    def _set_state(self, state: RadioState) -> None:
        with self._lock:
            self._state = state

    def _set_idle_state(self) -> None:
        if not self.enabled:
            self._set_state(RadioState.DISABLED)
        elif self.microphone.calibrating:
            self._set_state(RadioState.CALIBRATING)
        elif self._conversation_active():
            self._set_state(RadioState.LISTENING)
        else:
            self._set_state(RadioState.STANDBY)

    def _set_error(self, message: str, *, keep_state: bool = False) -> None:
        with self._lock:
            self._last_error = message
            if not keep_state:
                self._state = RadioState.ERROR

    def _clear_error(self) -> None:
        with self._lock:
            self._last_error = None
