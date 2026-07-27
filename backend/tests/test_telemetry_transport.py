from __future__ import annotations

import unittest

from app.f1.packets import PacketHeader, ParsedPacket
from app.telemetry.transport import (
    TelemetryTransportDiagnostics,
    is_newer_uint32,
)


class FakeClock:
    def __init__(self) -> None:
        self.wall = 1_700_000_000.0
        self.mono = 100.0

    def wall_time(self) -> float:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: float) -> None:
        self.wall += seconds
        self.mono += seconds


def packet(
    *,
    session_uid: int,
    frame: int,
    kind: str,
    session_time: float = 0.0,
    clock: FakeClock,
) -> ParsedPacket:
    header = PacketHeader(
        packet_format=2025,
        game_year=25,
        game_major_version=1,
        game_minor_version=0,
        packet_version=1,
        packet_id=0,
        session_uid=session_uid,
        session_time=session_time,
        frame_identifier=frame,
        overall_frame_identifier=frame,
        player_car_index=0,
        secondary_player_car_index=255,
    )
    return ParsedPacket(
        header=header,
        kind=kind,
        player={},
        raw_size=64,
        meta={
            "received_at_unix_s": clock.wall_time(),
            "received_at_monotonic_s": clock.monotonic(),
            "parsed_at_monotonic_s": clock.monotonic(),
            "parse_latency_ms": 0.0,
        },
    )


class TelemetryTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.transport = TelemetryTransportDiagnostics(
            wall_clock=self.clock.wall_time,
            monotonic_clock=self.clock.monotonic,
        )

    def apply(self, value: ParsedPacket):
        decision = self.transport.begin(value)
        if decision.accepted:
            self.clock.advance(0.001)
            self.transport.finish(decision)
        return decision

    def test_same_frame_is_allowed_for_different_packet_kinds(self):
        telemetry = self.apply(
            packet(
                session_uid=10,
                frame=50,
                kind="car_telemetry",
                clock=self.clock,
            )
        )
        lap = self.apply(
            packet(
                session_uid=10,
                frame=50,
                kind="lap_data",
                clock=self.clock,
            )
        )
        self.assertTrue(telemetry.accepted)
        self.assertTrue(lap.accepted)
        self.assertEqual(
            self.transport.snapshot()["counts"]["session_accepted"],
            2,
        )

    def test_duplicate_and_older_frames_are_rejected(self):
        self.assertTrue(
            self.apply(
                packet(
                    session_uid=10,
                    frame=100,
                    kind="lap_data",
                    clock=self.clock,
                )
            ).accepted
        )

        duplicate = self.apply(
            packet(
                session_uid=10,
                frame=100,
                kind="lap_data",
                clock=self.clock,
            )
        )
        older = self.apply(
            packet(
                session_uid=10,
                frame=99,
                kind="lap_data",
                clock=self.clock,
            )
        )

        self.assertFalse(duplicate.accepted)
        self.assertEqual(duplicate.reason, "duplicate_frame")
        self.assertFalse(older.accepted)
        self.assertEqual(older.reason, "out_of_order_frame")

        counts = self.transport.snapshot()["counts"]
        self.assertEqual(counts["duplicates"], 1)
        self.assertEqual(counts["out_of_order"], 1)

    def test_reset_during_packet_application_preserves_ordering(self):
        first_packet = packet(
            session_uid=10,
            frame=77,
            kind="car_telemetry",
            clock=self.clock,
        )

        decision = self.transport.begin(first_packet)
        self.assertTrue(decision.accepted)

        # Simulates an internal LiveTelemetryState reset while the accepted
        # packet is still being applied.
        self.transport.reset_all()
        self.clock.advance(0.001)
        self.transport.finish(decision)

        duplicate = self.transport.begin(
            packet(
                session_uid=10,
                frame=77,
                kind="car_telemetry",
                clock=self.clock,
            )
        )

        self.assertFalse(duplicate.accepted)
        self.assertEqual(duplicate.reason, "duplicate_frame")
        diagnostics = self.transport.snapshot()
        self.assertEqual(
            diagnostics["counts"]["ignored_inflight_resets"],
            1,
        )

    def test_uint32_wrap_is_treated_as_forward_progress(self):
        self.assertTrue(is_newer_uint32(1, 0xFFFFFFFE))
        self.assertFalse(is_newer_uint32(0xFFFFFFFE, 1))

        first = self.apply(
            packet(
                session_uid=10,
                frame=0xFFFFFFFE,
                kind="motion",
                clock=self.clock,
            )
        )
        wrapped = self.apply(
            packet(
                session_uid=10,
                frame=1,
                kind="motion",
                clock=self.clock,
            )
        )
        self.assertTrue(first.accepted)
        self.assertTrue(wrapped.accepted)

    def test_new_session_resets_ordering_and_rejects_retired_session(self):
        first = self.apply(
            packet(
                session_uid=10,
                frame=500,
                kind="lap_data",
                clock=self.clock,
            )
        )
        second_session = self.apply(
            packet(
                session_uid=20,
                frame=2,
                kind="lap_data",
                clock=self.clock,
            )
        )
        late_old_packet = self.apply(
            packet(
                session_uid=10,
                frame=501,
                kind="lap_data",
                clock=self.clock,
            )
        )

        self.assertTrue(first.accepted)
        self.assertTrue(second_session.accepted)
        self.assertTrue(second_session.new_session)
        self.assertFalse(late_old_packet.accepted)
        self.assertEqual(
            late_old_packet.reason,
            "retired_session",
        )

        diagnostics = self.transport.snapshot()
        self.assertEqual(diagnostics["session_uid"], 20)
        self.assertEqual(diagnostics["session_generation"], 2)
        self.assertEqual(
            diagnostics["counts"]["retired_session"],
            1,
        )

    def test_freshness_and_latency_are_reported(self):
        decision = self.apply(
            packet(
                session_uid=10,
                frame=1,
                kind="car_telemetry",
                clock=self.clock,
            )
        )
        self.assertTrue(decision.accepted)

        diagnostics = self.transport.snapshot()
        self.assertIn(
            "speed_kph",
            diagnostics["field_freshness"],
        )
        self.assertGreaterEqual(
            diagnostics["latency"]["sample_count"],
            1,
        )
        self.assertEqual(
            diagnostics["status"],
            "warming_up",
        )

        self.apply(
            packet(
                session_uid=10,
                frame=1,
                kind="lap_data",
                clock=self.clock,
            )
        )
        self.assertEqual(
            self.transport.snapshot()["status"],
            "live",
        )

        self.clock.advance(20.0)
        stale = self.transport.snapshot()
        self.assertEqual(stale["status"], "stale")
        self.assertFalse(stale["connected"])


if __name__ == "__main__":
    unittest.main()
