from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.strategy.engine import LiveStrategicEngineer
from app.strategy.models import BattleState, BoxAction, EnergyAction


class Settings(SimpleNamespace):
    strategy_default_pit_loss_s = 22.0
    strategy_default_lap_time_s = 90.0
    strategy_critical_wear_pct = 82.0
    strategy_box_wear_pct = 68.0
    strategy_marginal_finish_wear_pct = 78.0
    strategy_max_finish_wear_pct = 90.0
    strategy_hot_tyre_c = 108.0
    strategy_critical_tyre_c = 115.0
    strategy_attack_gap_s = 1.6
    strategy_defend_gap_s = 1.2
    strategy_ers_attack_reserve_pct = 28.0
    strategy_ers_defend_reserve_pct = 22.0
    strategy_ers_harvest_target_pct = 55.0
    strategy_auto_box_calls = True
    strategy_auto_battle_calls = True
    strategy_auto_ers_calls = True
    strategy_auto_coaching_calls = True


def snapshot(**overrides):
    values = {
        "connected": True,
        "session_uid": 100,
        "session_time": 120.0,
        "position": 5,
        "grid_size": 20,
        "lap_number": 10,
        "total_laps": 30,
        "last_lap_time_ms": 90000,
        "best_lap_time_ms": 89500,
        "delta_to_car_ahead_s": 0.8,
        "delta_to_leader_s": 8.0,
        "car_ahead": {
            "name": "RIVAL A",
            "position": 4,
            "last_lap_time_ms": 90400,
            "delta_to_car_ahead_s": 1.2,
            "delta_to_leader_s": 7.2,
            "pit_status": 0,
            "pit_stops": 0,
        },
        "car_behind": {
            "name": "RIVAL B",
            "position": 6,
            "last_lap_time_ms": 90200,
            "delta_to_car_ahead_s": 1.5,
            "delta_to_leader_s": 9.5,
            "pit_status": 0,
            "pit_stops": 0,
        },
        "classification": [
            {"name": "YOU", "position": 5, "delta_to_leader_s": 8.0},
            {"name": "RIVAL B", "position": 6, "delta_to_leader_s": 9.5},
            {"name": "RIVAL C", "position": 7, "delta_to_leader_s": 15.0},
            {"name": "RIVAL D", "position": 8, "delta_to_leader_s": 28.5},
        ],
        "tyre_wear_pct": [42.0, 41.0, 40.0, 40.0],
        "tyre_surface_temps_c": [98.0, 99.0, 96.0, 97.0],
        "tyre_damage_pct": [0, 0, 0, 0],
        "wing_damage_pct": {"fl": 0, "fr": 0, "rear": 0},
        "tyre_age_laps": 10,
        "tyre_compound": "MEDIUM",
        "ers_percent": 72.0,
        "fuel_remaining_laps": 22.0,
        "pit_status": 0,
        "history": [
            {
                "throttle": 0.9,
                "brake": 0.0,
                "steer": 0.1,
                "speed_kph": 250,
                "lap_distance_m": 3000,
            }
            for _ in range(40)
        ],
        "track_length_m": 5000,
        "completed_laps": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class LiveStrategicEngineerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = LiveStrategicEngineer(Settings())

    def test_attack_plan_uses_high_battery(self) -> None:
        result = self.engine.evaluate(snapshot())
        self.assertEqual(result.battle_state, BattleState.ATTACKING)
        self.assertEqual(result.energy.action, EnergyAction.DEPLOY)
        self.assertGreaterEqual(result.energy.minimum_reserve_percent, 20)

    def test_defence_plan(self) -> None:
        result = self.engine.evaluate(
            snapshot(
                delta_to_car_ahead_s=3.0,
                car_behind={
                    "name": "RIVAL B",
                    "position": 6,
                    "last_lap_time_ms": 89500,
                    "delta_to_car_ahead_s": 0.7,
                    "delta_to_leader_s": 8.7,
                    "pit_status": 0,
                    "pit_stops": 0,
                },
                ers_percent=48.0,
            )
        )
        self.assertEqual(result.battle_state, BattleState.DEFENDING)
        self.assertEqual(result.energy.action, EnergyAction.DEFEND)

    def test_critical_wear_boxes_now(self) -> None:
        result = self.engine.evaluate(
            snapshot(tyre_wear_pct=[85.0, 82.0, 80.0, 81.0])
        )
        self.assertEqual(result.box.action, BoxAction.BOX_NOW)
        self.assertGreater(result.box.confidence, 0.9)

    def test_late_race_stays_out_when_tyres_can_finish(self) -> None:
        result = self.engine.evaluate(
            snapshot(
                lap_number=29,
                total_laps=30,
                tyre_wear_pct=[45.0, 44.0, 43.0, 44.0],
                tyre_age_laps=15,
            )
        )
        self.assertEqual(result.box.action, BoxAction.STAY_OUT)

    def test_low_battery_harvests(self) -> None:
        result = self.engine.evaluate(
            snapshot(
                delta_to_car_ahead_s=4.0,
                car_behind=None,
                ers_percent=18.0,
            )
        )
        self.assertEqual(result.energy.action, EnergyAction.HARVEST)

    def test_rejoin_estimate_uses_classification(self) -> None:
        result = self.engine.evaluate(snapshot())
        self.assertIsNotNone(result.box.expected_rejoin_position)
        self.assertGreaterEqual(result.box.expected_rejoin_position or 0, 5)


if __name__ == "__main__":
    unittest.main()