from __future__ import annotations

import unittest

from app.radio.intent_router import LiveIntentRouter
from app.telemetry.models import LiveTelemetrySnapshot


class LiveIntentRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = LiveIntentRouter()
        self.snapshot = LiveTelemetrySnapshot(
            connected=True,
            position=4,
            grid_size=20,
            grid_position=7,
            positions_gained=3,
            total_laps=20,
            lap_number=10,
            delta_to_car_ahead_s=0.8,
            car_ahead={"name": "Rival Ahead"},
            car_behind={
                "name": "Rival Behind",
                "delta_to_car_ahead_s": 1.4,
            },
            fuel_remaining_laps=11.5,
            ers_percent=68.0,
            tyre_wear_pct=[30.0, 32.0, 28.0, 29.0],
            tyre_surface_temps_c=[98, 99, 101, 100],
            tyre_damage_pct=[0, 0, 0, 0],
            wing_damage_pct={"fl": 0, "fr": 0, "rear": 0},
            history=[
                {
                    "throttle": 0.0 if i % 4 == 0 else 0.6,
                    "brake": 0.7 if i % 4 == 0 else 0.0,
                    "steer": 0.2,
                }
                for i in range(80)
            ],
        )

    def test_position(self) -> None:
        result = self.router.route("what position am I", self.snapshot)
        self.assertTrue(result.handled)
        self.assertIn("P4", result.text)

    def test_gap_ahead(self) -> None:
        result = self.router.route("what is the gap ahead", self.snapshot)
        self.assertTrue(result.handled)
        self.assertIn("0.8", result.text)
        self.assertIn("DRS", result.text)

    def test_attack(self) -> None:
        result = self.router.route("can I attack", self.snapshot)
        self.assertTrue(result.handled)
        self.assertIn("Yes", result.text)

    def test_mode(self) -> None:
        result = self.router.route("coaching mode", self.snapshot)
        self.assertTrue(result.handled)
        self.assertEqual(result.action, "mode")
        self.assertEqual(result.mode.value, "coaching")

    def test_unknown_goes_to_llm_layer(self) -> None:
        result = self.router.route("tell me a joke", self.snapshot)
        self.assertFalse(result.handled)


if __name__ == "__main__":
    unittest.main()