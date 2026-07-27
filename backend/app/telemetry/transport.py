from __future__ import annotations

import math
import os
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from time import perf_counter, time
from typing import Any, Callable


_UINT32_MODULUS = 1 << 32
_UINT32_HALF_RANGE = 1 << 31


PACKET_FIELDS: dict[str, tuple[str, ...]] = {
    "car_telemetry": (
        "speed_kph",
        "throttle",
        "brake",
        "steer",
        "gear",
        "rpm",
        "drs",
        "rev_lights_percent",
        "brake_temps_c",
        "tyre_surface_temps_c",
        "tyre_inner_temps_c",
        "tyre_pressures_psi",
    ),
    "lap_data": (
        "last_lap_time_ms",
        "current_lap_time_ms",
        "lap_distance_m",
        "total_distance_m",
        "position",
        "grid_position",
        "grid_size",
        "lap_number",
        "sector",
        "lap_invalid",
        "penalties_s",
        "warnings",
        "pit_status",
        "pit_stops",
        "driver_status",
        "result_status",
        "delta_to_car_ahead_s",
        "delta_to_leader_s",
        "classification",
        "car_ahead",
        "car_behind",
        "leader",
    ),
    "car_status": (
        "fuel_remaining_laps",
        "fuel_in_tank_kg",
        "ers_store_j",
        "ers_percent",
        "ers_deploy_mode",
        "drs_allowed",
        "drs_activation_distance_m",
        "tyre_age_laps",
        "tyre_compound",
        "front_brake_bias",
        "traction_control",
        "abs_enabled",
    ),
    "car_damage": (
        "tyre_wear_pct",
        "tyre_damage_pct",
        "wing_damage_pct",
    ),
    "motion": (
        "world_position",
        "world_velocity",
        "g_force_lateral",
        "g_force_longitudinal",
    ),
    "session": (
        "total_laps",
        "track_length_m",
        "track_id",
        "session_type",
    ),
    "participants": (
        "player_name",
        "classification",
        "car_ahead",
        "car_behind",
        "leader",
    ),
    "final_classification": (
        "position",
        "grid_size",
        "result_status",
        "pit_stops",
        "penalties_s",
        "best_lap_time_ms",
        "classification",
    ),
}


# These are transport fallbacks, not race-strategy thresholds. Once enough
# samples exist, observed packet cadence replaces them automatically.
FALLBACK_INTERVAL_S: dict[str, float] = {
    "motion": 0.10,
    "car_telemetry": 0.10,
    "lap_data": 0.10,
    "car_status": 0.50,
    "car_damage": 0.50,
    "session": 1.00,
    "participants": 5.00,
    "event": 5.00,
    "final_classification": 5.00,
}

CRITICAL_GROUPS = ("car_telemetry", "lap_data")


def _safe_float(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, probability)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def is_newer_uint32(candidate: int, previous: int) -> bool:
    """Return True when candidate is newer, including uint32 wrap-around."""
    delta = (candidate - previous) % _UINT32_MODULUS
    return 0 < delta < _UINT32_HALF_RANGE


@dataclass(slots=True)
class PacketDecision:
    accepted: bool
    reason: str
    new_session: bool
    packet_kind: str
    session_uid: int | None
    frame: int | None
    received_unix_s: float
    received_monotonic_s: float
    parsed_monotonic_s: float
    apply_started_monotonic_s: float
    parse_latency_ms: float
    queue_latency_ms: float
    finished: bool = False


class TelemetryTransportDiagnostics:
    """Packet ordering, session isolation, freshness and latency tracking.

    The class is intentionally independent from FastAPI and the F1 parser. It
    consumes the public attributes of ParsedPacket and can therefore be tested
    without sockets or the game.
    """

    def __init__(
        self,
        *,
        wall_clock: Callable[[], float] = time,
        monotonic_clock: Callable[[], float] = perf_counter,
    ) -> None:
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock

        self.connection_timeout_s = max(
            0.25,
            _safe_float(
                os.getenv("TELEMETRY_CONNECTION_TIMEOUT_S"),
                2.0,
            ),
        )
        self.stale_multiplier = max(
            2.0,
            _safe_float(
                os.getenv("TELEMETRY_FIELD_STALE_MULTIPLIER"),
                6.0,
            ),
        )
        self.stale_floor_s = max(
            0.10,
            _safe_float(
                os.getenv("TELEMETRY_FIELD_STALE_FLOOR_S"),
                0.75,
            ),
        )
        self.stale_ceiling_s = max(
            self.stale_floor_s,
            _safe_float(
                os.getenv("TELEMETRY_FIELD_STALE_CEILING_S"),
                10.0,
            ),
        )
        self.warmup_s = max(
            0.0,
            _safe_float(
                os.getenv("TELEMETRY_WARMUP_S"),
                2.0,
            ),
        )
        self.latency_window = max(
            32,
            _safe_int(
                os.getenv("TELEMETRY_LATENCY_WINDOW"),
                256,
            ),
        )
        self.cadence_window = max(
            8,
            _safe_int(
                os.getenv("TELEMETRY_CADENCE_WINDOW"),
                64,
            ),
        )

        self._retired_session_uids: deque[int] = deque(maxlen=8)
        self._cadence_by_kind: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self.cadence_window)
        )
        self._latencies: deque[dict[str, float]] = deque(
            maxlen=self.latency_window
        )
        self._accepted_arrivals: deque[float] = deque(
            maxlen=self.latency_window
        )

        self._lifetime_received = 0
        self._lifetime_accepted = 0
        self._lifetime_rejected = 0
        self._session_generation = 0
        self._current_session_uid: int | None = None
        self._inflight_accepts = 0
        self._ignored_inflight_resets = 0

        self._reset_session_tracking()

    def _reset_session_tracking(self) -> None:
        self._session_received = 0
        self._session_accepted = 0
        self._session_rejected = 0
        self._duplicate_count = 0
        self._out_of_order_count = 0
        self._stale_session_count = 0

        self._last_frame_by_kind: dict[str, int] = {}
        self._last_session_time_by_kind: dict[str, float] = {}
        self._last_arrival_by_kind: dict[str, float] = {}
        self._cadence_by_kind.clear()
        self._latencies.clear()
        self._accepted_arrivals.clear()

        self._field_updates: dict[str, dict[str, Any]] = {}
        self._group_updates: dict[str, dict[str, Any]] = {}

        self._session_started_unix_s: float | None = None
        self._session_started_monotonic_s: float | None = None
        self._last_received_unix_s: float | None = None
        self._last_received_monotonic_s: float | None = None
        self._last_accepted_unix_s: float | None = None
        self._last_accepted_received_unix_s: float | None = None
        self._last_accepted_monotonic_s: float | None = None

        self._latest_packet_kind: str | None = None
        self._latest_packet_frame: int | None = None
        self._latest_rejection_reason: str | None = None
        self._latency_ema_ms = 0.0

    def reset_all(self) -> None:
        # LiveTelemetryState may clear domain values while it is applying
        # a packet (for example, on an internal session transition). Such
        # a domain reset must never erase the ordering guard for the very
        # packet currently being processed. Manual resets still perform a
        # complete transport reset because no packet is in flight then.
        if self._inflight_accepts > 0:
            self._ignored_inflight_resets += 1
            return

        self._retired_session_uids.clear()
        self._lifetime_received = 0
        self._lifetime_accepted = 0
        self._lifetime_rejected = 0
        self._session_generation = 0
        self._current_session_uid = None
        self._reset_session_tracking()

    @property
    def accepted_packet_count(self) -> int:
        return self._session_accepted

    @property
    def current_session_uid(self) -> int | None:
        return self._current_session_uid

    def _start_session(
        self,
        session_uid: int,
        received_unix_s: float,
        received_monotonic_s: float,
    ) -> None:
        previous = self._current_session_uid
        if previous is not None and previous != session_uid:
            self._retired_session_uids.append(previous)

        self._current_session_uid = session_uid
        self._session_generation += 1
        self._reset_session_tracking()
        self._session_started_unix_s = received_unix_s
        self._session_started_monotonic_s = received_monotonic_s

    def _normalise_session_uid(self, packet: Any) -> int | None:
        value = _safe_int(
            getattr(getattr(packet, "header", None), "session_uid", 0),
            0,
        )
        return value if value > 0 else None

    def _packet_frame(self, packet: Any) -> int | None:
        header = getattr(packet, "header", None)
        if header is None:
            return None

        overall = getattr(header, "overall_frame_identifier", None)
        if overall is not None:
            return _safe_int(overall) % _UINT32_MODULUS

        frame = getattr(header, "frame_identifier", None)
        if frame is not None:
            return _safe_int(frame) % _UINT32_MODULUS
        return None

    def _reject(
        self,
        *,
        reason: str,
        packet_kind: str,
        session_uid: int | None,
        frame: int | None,
        received_unix_s: float,
        received_monotonic_s: float,
        parsed_monotonic_s: float,
        apply_started_monotonic_s: float,
        parse_latency_ms: float,
        queue_latency_ms: float,
        new_session: bool = False,
    ) -> PacketDecision:
        self._session_rejected += 1
        self._lifetime_rejected += 1
        self._latest_rejection_reason = reason

        if reason == "duplicate_frame":
            self._duplicate_count += 1
        elif reason == "out_of_order_frame":
            self._out_of_order_count += 1
        elif reason == "retired_session":
            self._stale_session_count += 1

        return PacketDecision(
            accepted=False,
            reason=reason,
            new_session=new_session,
            packet_kind=packet_kind,
            session_uid=session_uid,
            frame=frame,
            received_unix_s=received_unix_s,
            received_monotonic_s=received_monotonic_s,
            parsed_monotonic_s=parsed_monotonic_s,
            apply_started_monotonic_s=apply_started_monotonic_s,
            parse_latency_ms=parse_latency_ms,
            queue_latency_ms=queue_latency_ms,
        )

    def begin(self, packet: Any) -> PacketDecision:
        meta = getattr(packet, "meta", None)
        if not isinstance(meta, dict):
            meta = {}

        apply_started_monotonic_s = self._monotonic_clock()
        received_monotonic_s = _safe_float(
            meta.get("received_at_monotonic_s"),
            apply_started_monotonic_s,
        )
        parsed_monotonic_s = _safe_float(
            meta.get("parsed_at_monotonic_s"),
            received_monotonic_s,
        )
        received_unix_s = _safe_float(
            meta.get("received_at_unix_s"),
            self._wall_clock(),
        )
        parse_latency_ms = max(
            0.0,
            _safe_float(
                meta.get("parse_latency_ms"),
                (parsed_monotonic_s - received_monotonic_s) * 1000.0,
            ),
        )
        queue_latency_ms = max(
            0.0,
            (apply_started_monotonic_s - parsed_monotonic_s) * 1000.0,
        )

        packet_kind = str(getattr(packet, "kind", "unknown") or "unknown")
        session_uid = self._normalise_session_uid(packet)
        frame = self._packet_frame(packet)

        self._lifetime_received += 1
        self._last_received_unix_s = received_unix_s
        self._last_received_monotonic_s = received_monotonic_s

        new_session = False
        if session_uid is not None:
            if self._current_session_uid is None:
                self._start_session(
                    session_uid,
                    received_unix_s,
                    received_monotonic_s,
                )
            elif session_uid != self._current_session_uid:
                if session_uid in self._retired_session_uids:
                    self._session_received += 1
                    return self._reject(
                        reason="retired_session",
                        packet_kind=packet_kind,
                        session_uid=session_uid,
                        frame=frame,
                        received_unix_s=received_unix_s,
                        received_monotonic_s=received_monotonic_s,
                        parsed_monotonic_s=parsed_monotonic_s,
                        apply_started_monotonic_s=apply_started_monotonic_s,
                        parse_latency_ms=parse_latency_ms,
                        queue_latency_ms=queue_latency_ms,
                    )

                new_session = True
                self._start_session(
                    session_uid,
                    received_unix_s,
                    received_monotonic_s,
                )

        self._session_received += 1

        previous_frame = self._last_frame_by_kind.get(packet_kind)
        if frame is not None and previous_frame is not None:
            if frame == previous_frame:
                return self._reject(
                    reason="duplicate_frame",
                    packet_kind=packet_kind,
                    session_uid=session_uid,
                    frame=frame,
                    received_unix_s=received_unix_s,
                    received_monotonic_s=received_monotonic_s,
                    parsed_monotonic_s=parsed_monotonic_s,
                    apply_started_monotonic_s=apply_started_monotonic_s,
                    parse_latency_ms=parse_latency_ms,
                    queue_latency_ms=queue_latency_ms,
                    new_session=new_session,
                )
            if not is_newer_uint32(frame, previous_frame):
                return self._reject(
                    reason="out_of_order_frame",
                    packet_kind=packet_kind,
                    session_uid=session_uid,
                    frame=frame,
                    received_unix_s=received_unix_s,
                    received_monotonic_s=received_monotonic_s,
                    parsed_monotonic_s=parsed_monotonic_s,
                    apply_started_monotonic_s=apply_started_monotonic_s,
                    parse_latency_ms=parse_latency_ms,
                    queue_latency_ms=queue_latency_ms,
                    new_session=new_session,
                )

        header = getattr(packet, "header", None)
        session_time = _safe_float(
            getattr(header, "session_time", 0.0),
            0.0,
        )

        # A frame identifier is the primary ordering source. Session time is
        # used only when no frame is available.
        if frame is None:
            previous_session_time = self._last_session_time_by_kind.get(
                packet_kind
            )
            if (
                previous_session_time is not None
                and session_time + 1e-6 < previous_session_time
            ):
                return self._reject(
                    reason="out_of_order_session_time",
                    packet_kind=packet_kind,
                    session_uid=session_uid,
                    frame=frame,
                    received_unix_s=received_unix_s,
                    received_monotonic_s=received_monotonic_s,
                    parsed_monotonic_s=parsed_monotonic_s,
                    apply_started_monotonic_s=apply_started_monotonic_s,
                    parse_latency_ms=parse_latency_ms,
                    queue_latency_ms=queue_latency_ms,
                    new_session=new_session,
                )

        previous_arrival = self._last_arrival_by_kind.get(packet_kind)
        if previous_arrival is not None:
            cadence = received_monotonic_s - previous_arrival
            if 0.0 < cadence <= 30.0:
                self._cadence_by_kind[packet_kind].append(cadence)

        self._last_arrival_by_kind[packet_kind] = received_monotonic_s
        if frame is not None:
            self._last_frame_by_kind[packet_kind] = frame
        self._last_session_time_by_kind[packet_kind] = session_time
        self._latest_rejection_reason = None

        self._inflight_accepts += 1
        return PacketDecision(
            accepted=True,
            reason="accepted",
            new_session=new_session,
            packet_kind=packet_kind,
            session_uid=session_uid,
            frame=frame,
            received_unix_s=received_unix_s,
            received_monotonic_s=received_monotonic_s,
            parsed_monotonic_s=parsed_monotonic_s,
            apply_started_monotonic_s=apply_started_monotonic_s,
            parse_latency_ms=parse_latency_ms,
            queue_latency_ms=queue_latency_ms,
        )

    def finish(self, decision: PacketDecision) -> None:
        if not decision.accepted or decision.finished:
            return

        processed_monotonic_s = self._monotonic_clock()
        processed_unix_s = self._wall_clock()

        state_update_latency_ms = max(
            0.0,
            (
                processed_monotonic_s
                - decision.apply_started_monotonic_s
            )
            * 1000.0,
        )
        end_to_end_latency_ms = max(
            0.0,
            (
                processed_monotonic_s
                - decision.received_monotonic_s
            )
            * 1000.0,
        )

        latency = {
            "parse_ms": decision.parse_latency_ms,
            "queue_ms": decision.queue_latency_ms,
            "state_update_ms": state_update_latency_ms,
            "end_to_end_ms": end_to_end_latency_ms,
        }
        self._latencies.append(latency)
        self._latency_ema_ms = (
            end_to_end_latency_ms
            if self._session_accepted == 0
            else self._latency_ema_ms * 0.90
            + end_to_end_latency_ms * 0.10
        )

        self._session_accepted += 1
        self._lifetime_accepted += 1
        self._accepted_arrivals.append(
            decision.received_monotonic_s
        )
        self._last_accepted_unix_s = processed_unix_s
        self._last_accepted_received_unix_s = (
            decision.received_unix_s
        )
        self._last_accepted_monotonic_s = processed_monotonic_s
        self._latest_packet_kind = decision.packet_kind
        self._latest_packet_frame = decision.frame

        update = {
            "source_packet": decision.packet_kind,
            "frame": decision.frame,
            "updated_at_unix_s": processed_unix_s,
            "updated_at_monotonic_s": processed_monotonic_s,
        }
        self._group_updates[decision.packet_kind] = dict(update)
        for field_name in PACKET_FIELDS.get(
            decision.packet_kind,
            (),
        ):
            self._field_updates[field_name] = dict(update)

        decision.finished = True
        self._inflight_accepts = max(
            0,
            self._inflight_accepts - 1,
        )

    def _observed_interval_s(self, packet_kind: str) -> float:
        samples = list(self._cadence_by_kind.get(packet_kind, ()))
        if len(samples) >= 3:
            return statistics.median(samples)
        return FALLBACK_INTERVAL_S.get(packet_kind, 1.0)

    def stale_after_s(self, packet_kind: str) -> float:
        observed = self._observed_interval_s(packet_kind)
        threshold = observed * self.stale_multiplier
        return max(
            self.stale_floor_s,
            min(self.stale_ceiling_s, threshold),
        )

    def _packet_rate_hz(self, now_monotonic_s: float) -> float:
        arrivals = list(self._accepted_arrivals)
        if len(arrivals) < 2:
            return 0.0

        recent = [
            value
            for value in arrivals
            if now_monotonic_s - value <= 2.0
        ]
        values = recent if len(recent) >= 2 else arrivals
        span = values[-1] - values[0]
        if span <= 0.0:
            return 0.0
        return (len(values) - 1) / span

    def _latency_summary(self) -> dict[str, Any]:
        if not self._latencies:
            return {
                "latest": {
                    "parse_ms": 0.0,
                    "queue_ms": 0.0,
                    "state_update_ms": 0.0,
                    "end_to_end_ms": 0.0,
                },
                "end_to_end_ema_ms": 0.0,
                "end_to_end_p50_ms": 0.0,
                "end_to_end_p95_ms": 0.0,
                "end_to_end_p99_ms": 0.0,
                "end_to_end_max_ms": 0.0,
                "sample_count": 0,
            }

        latest = self._latencies[-1]
        totals = [
            item["end_to_end_ms"]
            for item in self._latencies
        ]
        return {
            "latest": {
                key: round(value, 3)
                for key, value in latest.items()
            },
            "end_to_end_ema_ms": round(
                self._latency_ema_ms,
                3,
            ),
            "end_to_end_p50_ms": round(
                _percentile(totals, 0.50),
                3,
            ),
            "end_to_end_p95_ms": round(
                _percentile(totals, 0.95),
                3,
            ),
            "end_to_end_p99_ms": round(
                _percentile(totals, 0.99),
                3,
            ),
            "end_to_end_max_ms": round(max(totals), 3),
            "sample_count": len(totals),
        }

    def snapshot(self) -> dict[str, Any]:
        now_monotonic_s = self._monotonic_clock()
        now_unix_s = self._wall_clock()

        last_packet_age_s = (
            None
            if self._last_accepted_monotonic_s is None
            else max(
                0.0,
                now_monotonic_s
                - self._last_accepted_monotonic_s,
            )
        )
        last_datagram_age_s = (
            None
            if self._last_received_monotonic_s is None
            else max(
                0.0,
                now_monotonic_s
                - self._last_received_monotonic_s,
            )
        )
        session_age_s = (
            0.0
            if self._session_started_monotonic_s is None
            else max(
                0.0,
                now_monotonic_s
                - self._session_started_monotonic_s,
            )
        )

        connected = (
            last_packet_age_s is not None
            and last_packet_age_s
            <= self.connection_timeout_s
        )

        field_freshness: dict[str, dict[str, Any]] = {}
        stale_fields: list[str] = []
        for field_name, update in self._field_updates.items():
            source = str(update["source_packet"])
            age_s = max(
                0.0,
                now_monotonic_s
                - float(update["updated_at_monotonic_s"]),
            )
            stale_after = self.stale_after_s(source)
            is_stale = age_s > stale_after
            if is_stale:
                stale_fields.append(field_name)
            field_freshness[field_name] = {
                "source_packet": source,
                "frame": update.get("frame"),
                "updated_at_unix_s": round(
                    float(update["updated_at_unix_s"]),
                    6,
                ),
                "age_s": round(age_s, 4),
                "stale_after_s": round(stale_after, 4),
                "is_stale": is_stale,
            }

        group_freshness: dict[str, dict[str, Any]] = {}
        stale_groups: list[str] = []
        for packet_kind, update in self._group_updates.items():
            age_s = max(
                0.0,
                now_monotonic_s
                - float(update["updated_at_monotonic_s"]),
            )
            stale_after = self.stale_after_s(packet_kind)
            is_stale = age_s > stale_after
            if is_stale:
                stale_groups.append(packet_kind)
            group_freshness[packet_kind] = {
                "frame": update.get("frame"),
                "updated_at_unix_s": round(
                    float(update["updated_at_unix_s"]),
                    6,
                ),
                "age_s": round(age_s, 4),
                "observed_interval_s": round(
                    self._observed_interval_s(packet_kind),
                    4,
                ),
                "stale_after_s": round(stale_after, 4),
                "is_stale": is_stale,
            }

        missing_critical_groups = [
            packet_kind
            for packet_kind in CRITICAL_GROUPS
            if packet_kind not in self._group_updates
        ]
        stale_critical_groups = [
            packet_kind
            for packet_kind in CRITICAL_GROUPS
            if packet_kind in stale_groups
        ]

        if last_packet_age_s is None:
            status = "waiting"
        elif not connected:
            status = "stale"
        elif (
            session_age_s < self.warmup_s
            and missing_critical_groups
        ):
            status = "warming_up"
        elif missing_critical_groups or stale_critical_groups:
            status = "degraded"
        else:
            status = "live"

        packet_rates_hz = {
            packet_kind: round(
                1.0 / max(
                    self._observed_interval_s(packet_kind),
                    1e-9,
                ),
                2,
            )
            for packet_kind in sorted(
                self._last_arrival_by_kind
            )
        }

        return {
            "status": status,
            "connected": connected,
            "session_uid": self._current_session_uid,
            "session_generation": self._session_generation,
            "session_started_at_unix_s": (
                round(self._session_started_unix_s, 6)
                if self._session_started_unix_s is not None
                else None
            ),
            "session_age_s": round(session_age_s, 3),
            "last_packet_age_s": (
                round(last_packet_age_s, 4)
                if last_packet_age_s is not None
                else None
            ),
            "last_datagram_age_s": (
                round(last_datagram_age_s, 4)
                if last_datagram_age_s is not None
                else None
            ),
            "latest_packet_kind": self._latest_packet_kind,
            "latest_packet_frame": self._latest_packet_frame,
            "latest_packet": {
                "kind": self._latest_packet_kind,
                "frame": self._latest_packet_frame,
                "received_at_unix_s": (
                    round(
                        self._last_accepted_received_unix_s,
                        6,
                    )
                    if self._last_accepted_received_unix_s
                    is not None
                    else None
                ),
                "processed_at_unix_s": (
                    round(self._last_accepted_unix_s, 6)
                    if self._last_accepted_unix_s
                    is not None
                    else None
                ),
            },
            "latest_rejection_reason": (
                self._latest_rejection_reason
            ),
            "counts": {
                "session_received": self._session_received,
                "session_accepted": self._session_accepted,
                "session_rejected": self._session_rejected,
                "duplicates": self._duplicate_count,
                "out_of_order": self._out_of_order_count,
                "retired_session": self._stale_session_count,
                "lifetime_received": self._lifetime_received,
                "lifetime_accepted": self._lifetime_accepted,
                "lifetime_rejected": self._lifetime_rejected,
                "ignored_inflight_resets": (
                    self._ignored_inflight_resets
                ),
            },
            "packet_rate_hz": round(
                self._packet_rate_hz(now_monotonic_s),
                2,
            ),
            "packet_rates_hz": packet_rates_hz,
            "latency": self._latency_summary(),
            "ordering": {
                "last_frame_by_kind": dict(
                    self._last_frame_by_kind
                ),
                "retired_session_uids": list(
                    self._retired_session_uids
                ),
            },
            "field_freshness": field_freshness,
            "group_freshness": group_freshness,
            "stale_fields": sorted(stale_fields),
            "stale_groups": sorted(stale_groups),
            "missing_critical_groups": missing_critical_groups,
            "stale_critical_groups": stale_critical_groups,
            "generated_at_unix_s": round(now_unix_s, 6),
        }
