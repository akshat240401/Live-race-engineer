from __future__ import annotations

import unittest

from app.f1.packets import PacketHeader, ParsedPacket
from app.telemetry.state import LiveTelemetryState


def packet(
    *,
    session_uid: int,
    frame: int,
    kind: str,
    player: dict | None = None,
    cars: list[dict] | None = None,
) -> ParsedPacket:
    return ParsedPacket(
        header=PacketHeader(
            packet_format=2025,
            game_year=25,
            game_major_version=1,
            game_minor_version=0,
            packet_version=1,
            packet_id=0,
            session_uid=session_uid,
            session_time=float(frame) / 30.0,
            frame_identifier=frame,
            overall_frame_identifier=frame,
            player_car_index=0,
            secondary_player_car_index=255,
        ),
        kind=kind,
        player=player or {},
        cars=cars or [],
        raw_size=64,
    )


class TelemetryStateOrderingTests(unittest.TestCase):
    def test_rejected_packet_does_not_overwrite_latest_state(self):
        state = LiveTelemetryState()

        first = state.apply_packet(
            packet(
                session_uid=1,
                frame=10,
                kind="car_telemetry",
                player={"speed_kph": 210},
            )
        )
        duplicate = state.apply_packet(
            packet(
                session_uid=1,
                frame=10,
                kind="car_telemetry",
                player={"speed_kph": 50},
            )
        )

        self.assertTrue(first.last_packet_accepted)
        self.assertFalse(duplicate.last_packet_accepted)
        self.assertEqual(
            duplicate.last_packet_rejection_reason,
            "duplicate_frame",
        )
        self.assertEqual(duplicate.speed_kph, 210)

    def test_new_session_clears_old_domain_values(self):
        state = LiveTelemetryState()

        state.apply_packet(
            packet(
                session_uid=1,
                frame=100,
                kind="car_telemetry",
                player={"speed_kph": 300},
            )
        )
        next_session = state.apply_packet(
            packet(
                session_uid=2,
                frame=1,
                kind="car_telemetry",
                player={"speed_kph": 90},
            )
        )

        self.assertEqual(next_session.session_uid, 2)
        self.assertEqual(next_session.session_generation, 2)
        self.assertEqual(next_session.speed_kph, 90)
        self.assertEqual(next_session.lap_number, 0)

    def test_domain_reset_preserves_packet_ordering(self):
        state = LiveTelemetryState()
        first_packet = packet(
            session_uid=1,
            frame=42,
            kind="car_telemetry",
            player={"speed_kph": 222},
        )

        first = state.apply_packet(first_packet)
        state.reset()
        duplicate = state.apply_packet(first_packet)

        self.assertTrue(first.last_packet_accepted)
        self.assertFalse(duplicate.last_packet_accepted)
        self.assertEqual(
            duplicate.last_packet_rejection_reason,
            "duplicate_frame",
        )

    def test_hard_reset_clears_packet_ordering(self):
        state = LiveTelemetryState()
        first_packet = packet(
            session_uid=1,
            frame=42,
            kind="car_telemetry",
            player={"speed_kph": 222},
        )

        state.apply_packet(first_packet)
        state.hard_reset()
        replayed = state.apply_packet(first_packet)

        self.assertTrue(replayed.last_packet_accepted)
        self.assertEqual(replayed.speed_kph, 222)

    def test_diagnostics_api_payload_is_available(self):
        state = LiveTelemetryState()
        state.apply_packet(
            packet(
                session_uid=1,
                frame=1,
                kind="car_telemetry",
                player={"speed_kph": 120},
            )
        )
        diagnostics = state.diagnostics()
        self.assertIn("latency", diagnostics)
        self.assertIn("field_freshness", diagnostics)
        self.assertEqual(
            diagnostics["counts"]["session_accepted"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
