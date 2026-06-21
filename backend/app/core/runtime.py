from __future__ import annotations

from typing import Any

from app.analysis.post_race import PostRaceAnalyzer
from app.analysis.rag import RAGReportService
from app.coaching.radio import RaceRadioDirector
from app.coaching.rules import CoachingRuleEngine
from app.coaching.voice import VoiceEngineer
from app.core.config import Settings
from app.f1.packets import ParsedPacket
from app.radio.service import HandsFreeRadioService
from app.recording.session_recorder import SessionRecorder
from app.telemetry.models import EngineerMessage
from app.telemetry.state import LiveTelemetryState
from app.udp.listener import UDPListener


class RaceEngineerRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.state = LiveTelemetryState(history_limit=settings.history_limit)

        self.coach = CoachingRuleEngine(self.state)
        self.coach.set_enabled(settings.enable_coaching)

        self.voice = VoiceEngineer(
            enabled=settings.enable_voice,
            rate=settings.voice_rate,
            volume=settings.voice_volume,
        )
        self.radio = RaceRadioDirector(min_gap_s=3.5)

        self.recorder = SessionRecorder(
            settings.data_dir,
            enabled=settings.enable_recording,
            sample_hz=settings.recording_sample_hz,
        )
        self.post_race = PostRaceAnalyzer(self.recorder)
        self.rag = RAGReportService(
            self.recorder,
            self.post_race,
            llm_enabled=settings.llm_enabled,
            llm_base_url=settings.llm_base_url,
            llm_api_key=settings.llm_api_key,
            llm_model=settings.llm_model,
            llm_timeout_s=settings.llm_timeout_s,
        )

        self.live_radio = HandsFreeRadioService(
            settings,
            self.state,
            self.voice,
            self.recorder,
        )

        self.udp = UDPListener(
            settings.udp_host,
            settings.udp_port,
            self._handle_packet,
        )

    def start(self) -> None:
        self.voice.start()
        self.live_radio.start()
        if self.settings.enable_udp_listener:
            self.udp.start()

    def stop(self) -> None:
        snapshot = self.state.snapshot()
        self.recorder.finalize_current("application_stopped", snapshot)
        self.live_radio.stop()
        self.udp.stop()
        self.voice.stop()

    def _handle_packet(self, packet: ParsedPacket) -> None:
        snapshot = self.state.apply_packet(packet)
        messages = list(self.coach.analyze(snapshot))
        line = self.radio.select_line(messages)

        if line:
            top = self._highest_priority_message(messages)
            priority = self._message_priority(top) if top else 50
            category = top.category if top else "coaching"
            print(f"[RADIO] {line}")
            self.live_radio.enqueue_automatic(
                line,
                priority=priority,
                category=category,
            )

        snapshot = self.state.snapshot()
        session_id = self.recorder.record_snapshot(snapshot)
        self.state.set_recording_state(
            session_id,
            bool(session_id and self.settings.enable_recording),
        )

        if packet.kind == "final_classification":
            self._finalize_and_report("final_classification")
        elif (
            packet.kind == "event"
            and packet.event
            and packet.event.get("code") in {"SEND", "CHQF"}
        ):
            self._finalize_and_report(str(packet.event.get("code")))

    def _finalize_and_report(self, reason: str) -> None:
        snapshot = self.state.snapshot()
        metadata = self.recorder.finalize_current(reason, snapshot)
        self.state.set_recording_state(None, False)
        if not metadata:
            return
        session_id = str(metadata["session_id"])
        try:
            self.post_race.build_report(session_id, save=True)
        except Exception as exc:
            print(f"[REPORT] Could not build automatic report: {exc}")

    def set_voice_enabled(self, enabled: bool) -> None:
        self.voice.set_enabled(enabled)

    def set_coaching_enabled(self, enabled: bool) -> None:
        self.coach.set_enabled(enabled)
        if not enabled:
            self.radio.reset()

    def reset(self) -> dict[str, Any]:
        snapshot = self.state.snapshot()
        metadata = self.recorder.finalize_current("manual_reset", snapshot)
        self.state.reset()
        self.radio.reset()
        self.live_radio.reset_conversation()
        return {
            "ok": True,
            "saved_session": metadata.get("session_id") if metadata else None,
        }

    def test_voice(self) -> dict[str, Any]:
        spoken = self.voice.speak(
            "Radio check. Engineer online.",
            force=True,
            priority=100,
            interrupt=True,
        )
        return {
            "ok": spoken,
            "voice_enabled": self.voice.enabled,
            "message": "Radio check sent" if spoken else "Radio check failed",
            "last_voice_error": self.voice.last_error,
        }

    def health(self) -> dict[str, Any]:
        snapshot = self.state.snapshot()
        radio_status = self.live_radio.status()
        return {
            "ok": True,
            "udp_running": self.udp.running,
            "udp_host": self.settings.udp_host,
            "udp_port": self.settings.udp_port,
            "last_udp_error": self.udp.last_error,
            "connected": snapshot.connected,
            "packet_count": snapshot.packet_count,
            "last_packet_age_s": snapshot.last_packet_age_s,
            "voice_enabled": self.voice.enabled,
            "coaching_enabled": self.coach.enabled,
            "recording_enabled": self.settings.enable_recording,
            "active_session_id": self.recorder.active_session_id,
            "last_voice_error": self.voice.last_error,
            "llm_enabled": self.settings.llm_enabled,
            "live_llm_enabled": self.live_radio.llm.enabled,
            "radio_enabled": radio_status["enabled"],
            "radio_state": radio_status["state"],
            "radio_mode": radio_status["mode"],
            "radio": radio_status,
        }

    @staticmethod
    def _message_priority(message: EngineerMessage | None) -> int:
        if message is None:
            return 50
        evidence_priority = message.evidence.get("priority")
        if isinstance(evidence_priority, int):
            return evidence_priority
        return {
            "danger": 95,
            "warning": 80,
            "success": 70,
            "info": 50,
        }.get(message.severity, 50)

    def _highest_priority_message(
        self,
        messages: list[EngineerMessage],
    ) -> EngineerMessage | None:
        if not messages:
            return None
        return max(messages, key=self._message_priority)
