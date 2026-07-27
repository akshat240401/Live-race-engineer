from __future__ import annotations

import unittest

from app.f1.packets import PacketHeader, ParsedPacket
from app.telemetry.state import LiveTelemetryState


def header(
    frame: int,
    *,
    kind_id: int = 2,
    session_uid: int = 101,
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
    last_lap_time_ms: int = 0,
    current_lap_time_ms: int = 0,
    lap_invalid: bool = False,
    position: int = 1,
    session_uid: int = 101,
) -> ParsedPacket:
    player = {
        "car_index": 0,
        "last_lap_time_ms": last_lap_time_ms,
        "current_lap_time_ms": current_lap_time_ms,
        "lap_distance_m": 100.0,
        "total_distance_m": float(lap_number * 5000),
        "position": position,
        "grid_position": 3,
        "lap_number": lap_number,
        "sector": 1,
        "lap_invalid": lap_invalid,
        "penalties_s": 0,
        "warnings": 0,
        "pit_status": 0,
        "pit_stops": 0,
        "driver_status": 1,
        "result_status": 2,
        "delta_to_car_ahead_s": 0.0,
        "delta_to_leader_s": 0.0,
    }

    return ParsedPacket(
        header=header(
            frame,
            session_uid=session_uid,
        ),
        kind="lap_data",
        player=player,
        cars=[player],
        raw_size=64,
    )


def final_classification_packet(
    frame: int,
    *,
    best_lap_time_ms: int,
    session_uid: int = 101,
) -> ParsedPacket:
    return ParsedPacket(
        header=header(
            frame,
            kind_id=8,
            session_uid=session_uid,
        ),
        kind="final_classification",
        player={},
        cars=[
            {
                "car_index": 0,
                "position": 1,
                "result_status": 2,
                "num_pit_stops": 1,
                "penalties_s": 0,
                "best_lap_time_ms": best_lap_time_ms,
            }
        ],
        raw_size=64,
    )


class LapTimingValidationTests(unittest.TestCase):
    def test_valid_completed_lap_sets_best_lap(self):
        state = LiveTelemetryState()
        state._snapshot.track_length_m = 5000

        state.apply_packet(
            lap_packet(
                10,
                lap_number=1,
                current_lap_time_ms=82_000,
            )
        )
        snapshot = state.apply_packet(
            lap_packet(
                20,
                lap_number=2,
                last_lap_time_ms=82_000,
            )
        )

        self.assertEqual(snapshot.best_lap_time_ms, 82_000)
        self.assertEqual(len(snapshot.completed_laps), 1)
        self.assertTrue(snapshot.completed_laps[0]["valid"])

    def test_impossible_completed_lap_is_not_recorded_as_best(self):
        state = LiveTelemetryState()
        state._snapshot.track_length_m = 5000

        state.apply_packet(
            lap_packet(
                10,
                lap_number=1,
                current_lap_time_ms=3_000,
            )
        )
        snapshot = state.apply_packet(
            lap_packet(
                20,
                lap_number=2,
                last_lap_time_ms=3_000,
            )
        )

        self.assertIsNone(snapshot.best_lap_time_ms)
        self.assertEqual(snapshot.completed_laps, [])

    def test_invalid_lap_is_recorded_but_not_best_lap(self):
        state = LiveTelemetryState()
        state._snapshot.track_length_m = 5000

        state.apply_packet(
            lap_packet(
                10,
                lap_number=1,
                current_lap_time_ms=80_000,
                lap_invalid=True,
            )
        )
        snapshot = state.apply_packet(
            lap_packet(
                20,
                lap_number=2,
                last_lap_time_ms=80_000,
                lap_invalid=False,
            )
        )

        self.assertIsNone(snapshot.best_lap_time_ms)
        self.assertEqual(len(snapshot.completed_laps), 1)
        self.assertFalse(snapshot.completed_laps[0]["valid"])

    def test_final_classification_rejects_impossible_best_lap(self):
        state = LiveTelemetryState()
        state._snapshot.track_length_m = 5000

        snapshot = state.apply_packet(
            final_classification_packet(
                10,
                best_lap_time_ms=1,
            )
        )
        self.assertIsNone(snapshot.best_lap_time_ms)

        snapshot = state.apply_packet(
            final_classification_packet(
                20,
                best_lap_time_ms=81_000,
            )
        )
        self.assertEqual(snapshot.best_lap_time_ms, 81_000)

    def test_lap_number_rollback_is_ignored(self):
        state = LiveTelemetryState()
        state._snapshot.track_length_m = 5000

        snapshot = state.apply_packet(
            lap_packet(
                10,
                lap_number=3,
                current_lap_time_ms=10_000,
            )
        )
        self.assertEqual(snapshot.lap_number, 3)

        snapshot = state.apply_packet(
            lap_packet(
                20,
                lap_number=2,
                current_lap_time_ms=5_000,
            )
        )
        self.assertEqual(snapshot.lap_number, 3)


if __name__ == "__main__":
    unittest.main()
