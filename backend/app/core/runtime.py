from __future__ import annotations

from app.core.config import Settings
from app.coaching.radio import RaceRadioDirector
from app.coaching.rules import CoachingRuleEngine
from app.coaching.voice import VoiceEngineer
from app.f1.packets import ParsedPacket
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
        self.udp = UDPListener(settings.udp_host, settings.udp_port, self._handle_packet)

    def start(self) -> None:
        self.voice.start()
        if self.settings.enable_udp_listener:
            self.udp.start()

    def stop(self) -> None:
        self.udp.stop()
        self.voice.stop()

    def _handle_packet(self, packet: ParsedPacket) -> None:
        snapshot = self.state.apply_packet(packet)
        messages = self.coach.analyze(snapshot)
        line = self.radio.select_line(messages)
        if line:
            print(f"[RADIO] {line}")
            self.voice.speak(line)

    def set_voice_enabled(self, enabled: bool) -> None:
        self.voice.set_enabled(enabled)

    def set_coaching_enabled(self, enabled: bool) -> None:
        self.coach.set_enabled(enabled)
        if not enabled:
            self.radio.reset()

    def reset(self) -> None:
        self.state.reset()
        self.radio.reset()

    def test_voice(self) -> dict:
        spoken = self.voice.speak("Radio check. Engineer online.", force=True)
        return {
            "ok": spoken,
            "voice_enabled": self.voice.enabled,
            "message": "Radio check sent" if spoken else "Radio check failed",
            "last_voice_error": self.voice.last_error,
        }

    def health(self) -> dict:
        snap = self.state.snapshot()
        return {
            "ok": True,
            "udp_running": self.udp.running,
            "udp_host": self.settings.udp_host,
            "udp_port": self.settings.udp_port,
            "last_udp_error": self.udp.last_error,
            "connected": snap.connected,
            "packet_count": snap.packet_count,
            "last_packet_age_s": snap.last_packet_age_s,
            "voice_enabled": self.voice.enabled,
            "coaching_enabled": self.coach.enabled,
            "last_voice_error": self.voice.last_error,
        }