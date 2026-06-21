from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
import unittest

from app.core.config import Settings
from app.radio.service import HandsFreeRadioService
from app.telemetry.models import LiveTelemetrySnapshot


class FakeState:
    def __init__(self) -> None:
        self.snapshot_value = LiveTelemetrySnapshot(
            connected=True,
            position=6,
            grid_size=20,
            total_laps=18,
            lap_number=7,
            positions_gained=2,
            delta_to_car_ahead_s=0.9,
            car_ahead={"name": "Car Ahead"},
            fuel_remaining_laps=13.0,
            ers_percent=75.0,
            tyre_wear_pct=[20.0, 21.0, 19.0, 20.0],
            tyre_surface_temps_c=[98, 99, 100, 100],
            tyre_age_laps=7,
            brake=0.0,
            steer=0.0,
            g_force_lateral=0.0,
            g_force_longitudinal=0.0,
        )

    def snapshot(self) -> LiveTelemetrySnapshot:
        return self.snapshot_value


class FakeRecorder:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.active_session_id = None


class FakeVoice:
    def __init__(self) -> None:
        self.enabled = True
        self.is_speaking = False
        self.current_text = None
        self.spoken: list[str] = []

    def speak(self, text: str, **kwargs) -> bool:  # noqa: ANN003
        del kwargs
        self.spoken.append(text)
        return True

    def interrupt(self) -> None:
        self.is_speaking = False


class HandsFreeRadioServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        settings = Settings(
            radio_enabled=True,
            radio_preload_stt=False,
            radio_ack_mode="silent",
            radio_command_timeout_s=0.05,
            radio_followup_window_s=2,
            radio_profile_path=str(root / "profile.json"),
            radio_log_dir=str(root / "logs"),
            live_llm_enabled=False,
            llm_enabled=False,
        )
        self.voice = FakeVoice()
        self.service = HandsFreeRadioService(
            settings,
            FakeState(),  # type: ignore[arg-type]
            self.voice,  # type: ignore[arg-type]
            FakeRecorder(root / "sessions"),  # type: ignore[arg-type]
        )

    def tearDown(self) -> None:
        self.service.stop()
        self.temp.cleanup()

    def test_wake_only_opens_command_window(self) -> None:
        result = self.service.process_text("Engineer", speak=False)
        self.assertTrue(result["ok"])
        self.assertTrue(self.service.status()["awaiting_command"])

    def test_wake_phrase_and_followup(self) -> None:
        first = self.service.process_text(
            "Engineer, what is the gap ahead?",
            speak=False,
        )
        self.assertTrue(first["ok"])
        self.assertIn("0.9", first["response"])

        followup = self.service.process_text(
            "Can I attack?",
            speak=False,
        )
        self.assertTrue(followup["ok"])
        self.assertIn("attack", followup["response"].casefold())

    def test_contextual_tyre_followup(self) -> None:
        first = self.service.process_text("Engineer, how are my tyres?", speak=False)
        self.assertTrue(first["ok"])
        followup = self.service.process_text("Can they reach the end?", speak=False)
        self.assertTrue(followup["ok"])
        self.assertIn("reach the end", followup["response"].casefold())

    def test_terminology_normalizes_wake_phrase(self) -> None:
        result = self.service.process_text(
            "Engine near what position am I",
            speak=False,
        )
        self.assertTrue(result["ok"])
        self.assertIn("P6", result["response"])

    def test_command_window_expires(self) -> None:
        self.service.process_text("Engineer", speak=False)
        sleep(0.08)
        status = self.service.status()
        self.assertFalse(status["awaiting_command"])
        self.assertEqual(status["state"], "standby")

    def test_quiet_voice_command_requires_confirmation(self) -> None:
        prompt = self.service.process_text("Engineer, stop talking", speak=False)
        self.assertIn("Confirm", prompt["response"])
        self.assertFalse(self.service.status()["muted"])

        confirmed = self.service.process_text("confirm", speak=False)
        self.assertTrue(confirmed["ok"])
        self.assertTrue(self.service.status()["muted"])

    def test_ignores_non_wake_speech_outside_conversation(self) -> None:
        self.service.reset_conversation()
        result = self.service.process_text(
            "this is unrelated background speech",
            speak=False,
        )
        self.assertFalse(result["ok"])
        self.assertTrue(result["ignored"])

    def test_mode_voice_command(self) -> None:
        result = self.service.process_text(
            "Engineer, coaching mode",
            speak=False,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(self.service.mode.value, "coaching")


if __name__ == "__main__":
    unittest.main()
