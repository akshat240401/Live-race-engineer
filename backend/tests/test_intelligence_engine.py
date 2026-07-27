from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from app.intelligence.engine import AdaptiveBattleIntelligence, IntelligenceConfig


@dataclass
class Car:
    name: str
    position: int
    delta_to_car_ahead_s: float
    delta_to_leader_s: float
    pit_status: int = 0
    pit_stops: int = 0
    last_lap_time_ms: int = 90_000


@dataclass
class Snapshot:
    connected: bool = True
    session_uid: int = 123
    session_time: float = 0.0
    lap_number: int = 3
    total_laps: int = 10
    last_lap_time_ms: int = 90_000
    best_lap_time_ms: int = 89_000
    track_length_m: float = 5_000.0
    speed_kph: float = 220.0
    delta_to_car_ahead_s: float = 2.0
    delta_to_leader_s: float = 10.0
    car_ahead: Car | None = None
    car_behind: Car | None = None
    completed_laps: list[dict] = field(default_factory=list)


class BattleIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = AdaptiveBattleIntelligence(
            IntelligenceConfig(
                drs_window_s=1.0,
                history_seconds=300.0,
                forecast_laps=3,
                timeline_size=12,
                state_confidence_z=1.96,
            )
        )

    def test_one_sample_is_not_presented_as_resolved_clear_air(self) -> None:
        result = self.engine.analyze(
            Snapshot(
                session_time=1.0,
                delta_to_car_ahead_s=6.0,
                car_ahead=Car("RIVAL_A", 4, 0.0, 4.0),
            )
        )

        self.assertEqual(result.state, "clear")
        self.assertFalse(result.decision_resolved)
        self.assertLessEqual(result.state_margin, 0.0)
        self.assertEqual(result.model.effective_sample_count, 1)  # type: ignore[union-attr]

    def test_learns_attack_probability_from_closing_gap(self) -> None:
        result = None
        for index in range(60):
            gap = max(0.55, 2.4 - index * 0.035)
            snapshot = Snapshot(
                session_time=index * 2.0,
                delta_to_car_ahead_s=gap,
                car_ahead=Car(
                    name="RIVAL_A",
                    position=4,
                    delta_to_car_ahead_s=0.0,
                    delta_to_leader_s=8.0,
                ),
            )
            result = self.engine.analyze(snapshot)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreater(result.probabilities.attack, result.probabilities.clear)
        self.assertEqual(result.target, "RIVAL_A")
        self.assertGreater(result.ahead.closing_probability, 0.5)  # type: ignore[union-attr]
        self.assertGreater(result.relative_pace.ahead_s_per_lap, 0.0)  # type: ignore[operator]
        self.assertTrue(result.decision_resolved)
        self.assertGreater(result.state_margin, 0.0)

    def test_learns_defence_probability_from_closing_car_behind(self) -> None:
        result = None
        for index in range(60):
            gap = max(0.35, 2.2 - index * 0.032)
            snapshot = Snapshot(
                session_time=index * 2.0,
                delta_to_car_ahead_s=8.0,
                car_ahead=Car(
                    name="RIVAL_A",
                    position=4,
                    delta_to_car_ahead_s=0.0,
                    delta_to_leader_s=4.0,
                ),
                car_behind=Car(
                    name="RIVAL_B",
                    position=6,
                    delta_to_car_ahead_s=gap,
                    delta_to_leader_s=10.0 + gap,
                ),
            )
            result = self.engine.analyze(snapshot)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreater(result.probabilities.defend, result.probabilities.clear)
        self.assertEqual(result.target, "RIVAL_B")
        self.assertGreater(result.behind.closing_probability, 0.5)  # type: ignore[union-attr]
        self.assertTrue(result.decision_resolved)

    def test_ambiguous_probabilities_remain_unresolved(self) -> None:
        result = None
        for index in range(24):
            oscillation = 0.15 if index % 2 == 0 else -0.15
            ahead_gap = 1.05 + oscillation
            behind_gap = 1.05 - oscillation
            result = self.engine.analyze(
                Snapshot(
                    session_time=index * 2.0,
                    delta_to_car_ahead_s=ahead_gap,
                    car_ahead=Car("RIVAL_A", 4, 0.0, 8.0),
                    car_behind=Car("RIVAL_B", 6, behind_gap, 10.0 + behind_gap),
                )
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.decision_resolved)
        self.assertLessEqual(result.state_margin, 0.0)

    def test_session_change_resets_observations(self) -> None:
        for index in range(10):
            self.engine.analyze(
                Snapshot(
                    session_uid=1,
                    session_time=index,
                    delta_to_car_ahead_s=2.0 - index * 0.05,
                    car_ahead=Car("A", 4, 0.0, 8.0),
                )
            )

        result = self.engine.analyze(
            Snapshot(
                session_uid=2,
                session_time=1.0,
                delta_to_car_ahead_s=4.0,
                car_ahead=Car("B", 4, 0.0, 8.0),
            )
        )
        self.assertEqual(result.model.sample_count, 1)  # type: ignore[union-attr]
        self.assertEqual(result.ahead.name, "B")  # type: ignore[union-attr]
        self.assertFalse(result.decision_resolved)


if __name__ == "__main__":
    unittest.main()