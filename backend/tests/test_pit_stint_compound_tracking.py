from __future__ import annotations

import unittest

from app.f1.packets import PacketHeader, ParsedPacket
from app.telemetry.state import LiveTelemetryState


def header(
    frame: int,
    *,
    kind_id: int,
    session_uid: int = 303,
) -> PacketHeader:
    return PacketHeader(
        packet_format=2025,
        game_year=25,
        game_major_version=1,
        game_minor_version=0,
        packet_version=1,
        packet_id=kind_id,
        session_uid=session_uid,
        session_time=frame / 30.0,
        frame_identifier=frame,
        overall_frame_identifier=frame,
        player_car_index=0,
        secondary_player_car_index=255,
    )


def lap_packet(
    frame: int,
    *,
    lap_number: int,
    pit_status: int = 0,
    pit_stops: int = 0,
) -> ParsedPacket:
    player = {
        "car_index": 0,
        "last_lap_time_ms": 0,
        "current_lap_time_ms": 10_000,
        "lap_distance_m": 100.0,
        "total_distance_m": lap_number * 5000.0,
        "position": 1,
        "grid_position": 1,
        "lap_number": lap_number,
        "sector": 1,
        "lap_invalid": False,
        "penalties_s": 0,
        "warnings": 0,
        "pit_status": pit_status,
        "pit_stops": pit_stops,
        "driver_status": 1,
        "result_status": 2,
        "delta_to_car_ahead_s": 0.0,
        "delta_to_leader_s": 0.0,
    }

    return ParsedPacket(
        header=header(frame, kind_id=2),
        kind="lap_data",
        player=player,
        cars=[player],
        raw_size=64,
    )


def status_packet(
    frame: int,
    *,
    visual_tyre_compound: int,
    tyre_age_laps: int,
    fuel_remaining_laps: float = 5.0,
    ers_store_j: float = 2_000_000.0,
) -> ParsedPacket:
    player = {
        "fuel_remaining_laps": fuel_remaining_laps,
        "fuel_in_tank_kg": 12.0,
        "ers_store_j": ers_store_j,
        "ers_deploy_mode": 1,
        "drs_allowed": False,
        "drs_activation_distance_m": 0,
        "tyre_age_laps": tyre_age_laps,
        "visual_tyre_compound": visual_tyre_compound,
        "front_brake_bias": 58,
        "traction_control": 1,
        "anti_lock_brakes": True,
    }

    return ParsedPacket(
        header=header(frame, kind_id=7),
        kind="car_status",
        player=player,
        cars=[player],
        raw_size=64,
    )


def final_classification_packet(
    frame: int,
    *,
    pit_stops: int,
) -> ParsedPacket:
    return ParsedPacket(
        header=header(frame, kind_id=8),
        kind="final_classification",
        player={},
        cars=[
            {
                "car_index": 0,
                "position": 1,
                "result_status": 2,
                "num_pit_stops": pit_stops,
                "penalties_s": 0,
                "best_lap_time_ms": 90_000,
            }
        ],
        raw_size=64,
    )


class PitStintCompoundTests(unittest.TestCase):
    def test_compound_change_starts_new_stint(self):
        state = LiveTelemetryState()

        state.apply_packet(lap_packet(10, lap_number=1))
        first = state.apply_packet(
            status_packet(
                20,
                visual_tyre_compound=16,
                tyre_age_laps=2,
            )
        )
        first_compound = first.tyre_compound

        state.apply_packet(lap_packet(30, lap_number=3))
        second = state.apply_packet(
            status_packet(
                40,
                visual_tyre_compound=17,
                tyre_age_laps=0,
            )
        )

        self.assertNotEqual(second.tyre_compound, first_compound)
        self.assertEqual(second.previous_tyre_compound, first_compound)
        self.assertEqual(second.stint_number, 2)
        self.assertEqual(second.current_stint_compound, second.tyre_compound)
        self.assertEqual(second.current_stint_start_lap, 3)
        self.assertEqual(second.stint_lap, 0)

    def test_tyre_age_updates_stint_lap_without_new_stint(self):
        state = LiveTelemetryState()

        state.apply_packet(lap_packet(10, lap_number=1))
        first = state.apply_packet(
            status_packet(
                20,
                visual_tyre_compound=16,
                tyre_age_laps=1,
            )
        )
        second = state.apply_packet(
            status_packet(
                30,
                visual_tyre_compound=16,
                tyre_age_laps=4,
            )
        )

        self.assertEqual(second.stint_number, first.stint_number)
        self.assertEqual(second.stint_lap, 3)

    def test_pit_lane_entry_and_exit_are_tracked(self):
        state = LiveTelemetryState()

        start = state.apply_packet(
            lap_packet(
                10,
                lap_number=4,
                pit_status=0,
                pit_stops=0,
            )
        )
        self.assertFalse(start.in_pit_lane)

        entry = state.apply_packet(
            lap_packet(
                20,
                lap_number=4,
                pit_status=1,
                pit_stops=0,
            )
        )
        self.assertTrue(entry.in_pit_lane)
        self.assertEqual(entry.pit_entry_lap, 4)

        exit_snapshot = state.apply_packet(
            lap_packet(
                30,
                lap_number=4,
                pit_status=0,
                pit_stops=1,
            )
        )
        self.assertFalse(exit_snapshot.in_pit_lane)
        self.assertEqual(exit_snapshot.pit_exit_lap, 4)
        self.assertEqual(exit_snapshot.pit_stops, 1)

    def test_pit_stop_count_never_rolls_back(self):
        state = LiveTelemetryState()

        first = state.apply_packet(
            lap_packet(
                10,
                lap_number=4,
                pit_status=0,
                pit_stops=2,
            )
        )
        self.assertEqual(first.pit_stops, 2)

        second = state.apply_packet(
            lap_packet(
                20,
                lap_number=4,
                pit_status=0,
                pit_stops=1,
            )
        )
        self.assertEqual(second.pit_stops, 2)

    def test_final_classification_does_not_reduce_pit_stops(self):
        state = LiveTelemetryState()

        state.apply_packet(
            lap_packet(
                10,
                lap_number=4,
                pit_status=0,
                pit_stops=2,
            )
        )
        snapshot = state.apply_packet(
            final_classification_packet(
                20,
                pit_stops=1,
            )
        )

        self.assertEqual(snapshot.pit_stops, 2)

    def test_same_compound_tyre_age_reset_starts_new_stint(self):
        state = LiveTelemetryState()

        state.apply_packet(lap_packet(10, lap_number=2))
        first = state.apply_packet(
            status_packet(
                20,
                visual_tyre_compound=16,
                tyre_age_laps=1,
            )
        )
        self.assertEqual(first.stint_number, 1)

        state.apply_packet(
            lap_packet(
                30,
                lap_number=2,
                pit_status=1,
                pit_stops=0,
            )
        )
        state.apply_packet(
            lap_packet(
                40,
                lap_number=3,
                pit_status=0,
                pit_stops=1,
            )
        )
        second = state.apply_packet(
            status_packet(
                50,
                visual_tyre_compound=16,
                tyre_age_laps=0,
            )
        )

        self.assertEqual(second.tyre_compound, first.tyre_compound)
        self.assertEqual(second.previous_tyre_compound, first.tyre_compound)
        self.assertEqual(second.stint_number, 2)
        self.assertEqual(second.current_stint_compound, second.tyre_compound)
        self.assertEqual(second.current_stint_start_lap, 3)
        self.assertEqual(second.stint_lap, 0)



if __name__ == "__main__":
    unittest.main()
