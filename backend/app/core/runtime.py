from __future__ import annotations

from app.analysis.post_race import (
    PostRaceAnalyzer,
)
from app.analysis.rag import (
    RAGReportService,
)
from app.coaching.radio import (
    RaceRadioDirector,
)
from app.coaching.rules import (
    CoachingRuleEngine,
)
from app.coaching.voice import (
    VoiceEngineer,
)
from app.core.config import Settings
from app.f1.packets import ParsedPacket
from app.recording.session_recorder import (
    SessionRecorder,
)
from app.telemetry.state import (
    LiveTelemetryState,
)
from app.udp.listener import UDPListener


class RaceEngineerRuntime:
    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings

        self.state = LiveTelemetryState(
            history_limit=(
                settings.history_limit
            )
        )

        self.coach = CoachingRuleEngine(
            self.state
        )

        self.coach.set_enabled(
            settings.enable_coaching
        )

        self.voice = VoiceEngineer(
            enabled=settings.enable_voice,
            rate=settings.voice_rate,
            volume=settings.voice_volume,
        )

        self.radio = RaceRadioDirector(
            min_gap_s=3.5
        )

        self.recorder = SessionRecorder(
            settings.data_dir,
            enabled=(
                settings.enable_recording
            ),
            sample_hz=(
                settings.recording_sample_hz
            ),
        )

        self.post_race = PostRaceAnalyzer(
            self.recorder
        )

        self.rag = RAGReportService(
            self.recorder,
            self.post_race,
            llm_enabled=(
                settings.llm_enabled
            ),
            llm_base_url=(
                settings.llm_base_url
            ),
            llm_api_key=(
                settings.llm_api_key
            ),
            llm_model=(
                settings.llm_model
            ),
            llm_timeout_s=(
                settings.llm_timeout_s
            ),
        )

        self.udp = UDPListener(
            settings.udp_host,
            settings.udp_port,
            self._handle_packet,
        )

    def start(self) -> None:
        self.voice.start()

        if self.settings.enable_udp_listener:
            self.udp.start()

    def stop(self) -> None:
        snapshot = self.state.snapshot()

        self.recorder.finalize_current(
            "application_stopped",
            snapshot,
        )

        self.udp.stop()
        self.voice.stop()

    def _handle_packet(
        self,
        packet: ParsedPacket,
    ) -> None:
        snapshot = self.state.apply_packet(
            packet
        )

        messages = self.coach.analyze(
            snapshot
        )

        line = self.radio.select_line(
            messages
        )

        if line:
            print(f"[RADIO] {line}")
            self.voice.speak(line)

        snapshot = self.state.snapshot()

        session_id = (
            self.recorder.record_snapshot(
                snapshot
            )
        )

        self.state.set_recording_state(
            session_id,
            bool(
                session_id
                and self.settings.enable_recording
            ),
        )

        if (
            packet.kind
            == "final_classification"
        ):
            self._finalize_and_report(
                "final_classification"
            )

        elif (
            packet.kind == "event"
            and packet.event
            and packet.event.get("code")
            in {"SEND", "CHQF"}
        ):
            self._finalize_and_report(
                str(
                    packet.event.get("code")
                )
            )

    def _finalize_and_report(
        self,
        reason: str,
    ) -> None:
        snapshot = self.state.snapshot()

        metadata = (
            self.recorder.finalize_current(
                reason,
                snapshot,
            )
        )

        self.state.set_recording_state(
            None,
            False,
        )

        if not metadata:
            return

        session_id = str(
            metadata["session_id"]
        )

        try:
            self.post_race.build_report(
                session_id,
                save=True,
            )
        except Exception as exc:
            print(
                "[REPORT] Could not build "
                f"automatic report: {exc}"
            )

    def set_voice_enabled(
        self,
        enabled: bool,
    ) -> None:
        self.voice.set_enabled(enabled)

    def set_coaching_enabled(
        self,
        enabled: bool,
    ) -> None:
        self.coach.set_enabled(enabled)

        if not enabled:
            self.radio.reset()

    def reset(self) -> dict:
        snapshot = self.state.snapshot()

        metadata = (
            self.recorder.finalize_current(
                "manual_reset",
                snapshot,
            )
        )

        self.state.reset()
        self.radio.reset()

        return {
            "ok": True,
            "saved_session": (
                metadata.get("session_id")
                if metadata
                else None
            ),
        }

    def test_voice(self) -> dict:
        spoken = self.voice.speak(
            "Radio check. Engineer online.",
            force=True,
        )

        return {
            "ok": spoken,
            "voice_enabled": (
                self.voice.enabled
            ),
            "message": (
                "Radio check sent"
                if spoken
                else "Radio check failed"
            ),
            "last_voice_error": (
                self.voice.last_error
            ),
        }

    def health(self) -> dict:
        snapshot = self.state.snapshot()

        return {
            "ok": True,
            "udp_running": self.udp.running,
            "udp_host": (
                self.settings.udp_host
            ),
            "udp_port": (
                self.settings.udp_port
            ),
            "last_udp_error": (
                self.udp.last_error
            ),
            "connected": snapshot.connected,
            "packet_count": (
                snapshot.packet_count
            ),
            "last_packet_age_s": (
                snapshot.last_packet_age_s
            ),
            "voice_enabled": (
                self.voice.enabled
            ),
            "coaching_enabled": (
                self.coach.enabled
            ),
            "recording_enabled": (
                self.settings.enable_recording
            ),
            "active_session_id": (
                self.recorder.active_session_id
            ),
            "last_voice_error": (
                self.voice.last_error
            ),
            "llm_enabled": (
                self.settings.llm_enabled
            ),
        }