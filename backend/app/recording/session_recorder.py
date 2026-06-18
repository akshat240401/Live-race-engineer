from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock
from time import time
from typing import Any

from app.telemetry.models import LiveTelemetrySnapshot


def _json_dump(
    path: Path,
    value: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)


def _append_jsonl(
    path: Path,
    value: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )


def _read_json(
    path: Path,
    default: Any,
) -> Any:
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
    ):
        return default


@dataclass
class ActiveRecording:
    session_id: str
    session_uid: int
    directory: Path
    started_at: float
    started_at_iso: str

    last_telemetry_session_time: float = -1.0
    last_message_id: int = 0
    last_event_id: int = 0
    last_lap_count: int = 0
    telemetry_samples: int = 0


class SessionRecorder:
    def __init__(
        self,
        data_dir: str | Path,
        enabled: bool = True,
        sample_hz: float = 5.0,
    ) -> None:
        self.root = (
            Path(data_dir)
            .expanduser()
            .resolve()
        )

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.enabled = enabled

        self.sample_interval_s = (
            1.0 / max(0.5, sample_hz)
        )

        self._lock = Lock()
        self._active: ActiveRecording | None = None
        self._closed_uids: set[int] = set()

    @property
    def active_session_id(
        self,
    ) -> str | None:
        with self._lock:
            if self._active:
                return self._active.session_id
            return None

    def record_snapshot(
        self,
        snapshot: LiveTelemetrySnapshot,
    ) -> str | None:
        if (
            not self.enabled
            or not snapshot.session_uid
        ):
            return None

        with self._lock:
            session_uid = int(
                snapshot.session_uid
            )

            if (
                self._active is None
                and session_uid
                in self._closed_uids
            ):
                return None

            if (
                self._active is None
                or (
                    self._active.session_uid
                    != session_uid
                )
            ):
                if self._active is not None:
                    self._finalize_locked(
                        "session_changed",
                        snapshot=None,
                    )

                self._start_locked(snapshot)

            active = self._active

            if active is None:
                return None

            self._write_incremental_locked(
                active,
                snapshot,
            )

            return active.session_id

    def finalize_current(
        self,
        reason: str,
        snapshot: (
            LiveTelemetrySnapshot | None
        ) = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            return self._finalize_locked(
                reason,
                snapshot,
            )

    def list_sessions(
        self,
    ) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []

        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue

            metadata = _read_json(
                directory / "session.json",
                {},
            )

            if not metadata:
                continue

            report = _read_json(
                directory / "report.json",
                None,
            )

            sessions.append({
                "session_id": directory.name,
                "started_at": metadata.get(
                    "started_at"
                ),
                "ended_at": metadata.get(
                    "ended_at"
                ),
                "status": metadata.get(
                    "status",
                    "recording",
                ),
                "track_id": metadata.get(
                    "track_id"
                ),
                "session_type": metadata.get(
                    "session_type"
                ),
                "total_laps": metadata.get(
                    "total_laps",
                    0,
                ),
                "finish_position": metadata.get(
                    "finish_position"
                ),
                "recorded_samples": metadata.get(
                    "recorded_samples",
                    0,
                ),
                "has_report": report is not None,
            })

        sessions.sort(
            key=lambda item: str(
                item.get("started_at") or ""
            ),
            reverse=True,
        )

        return sessions

    def session_directory(
        self,
        session_id: str,
    ) -> Path:
        safe = Path(session_id).name

        directory = (
            self.root / safe
        ).resolve()

        if self.root not in directory.parents:
            raise ValueError(
                "Invalid session id"
            )

        if (
            not directory.exists()
            or not directory.is_dir()
        ):
            raise FileNotFoundError(
                f"Session {session_id!r} "
                "was not found"
            )

        return directory

    def get_session_bundle(
        self,
        session_id: str,
        telemetry_limit: int = 0,
    ) -> dict[str, Any]:
        directory = self.session_directory(
            session_id
        )

        return {
            "metadata": _read_json(
                directory / "session.json",
                {},
            ),
            "laps": _read_json(
                directory / "laps.json",
                [],
            ),
            "classification": _read_json(
                directory
                / "classification.json",
                [],
            ),
            "events": self._read_jsonl(
                directory / "events.jsonl",
                0,
            ),
            "messages": self._read_jsonl(
                directory / "messages.jsonl",
                0,
            ),
            "telemetry": self._read_jsonl(
                directory / "telemetry.jsonl",
                telemetry_limit,
            ),
            "report": _read_json(
                directory / "report.json",
                None,
            ),
            "ai_report": _read_json(
                directory / "ai_report.json",
                None,
            ),
        }

    def get_telemetry(
        self,
        session_id: str,
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        directory = self.session_directory(
            session_id
        )

        return self._read_jsonl(
            directory / "telemetry.jsonl",
            limit,
        )

    def save_report(
        self,
        session_id: str,
        report: dict[str, Any],
        ai: bool = False,
    ) -> None:
        directory = self.session_directory(
            session_id
        )

        filename = (
            "ai_report.json"
            if ai
            else "report.json"
        )

        _json_dump(
            directory / filename,
            report,
        )

    def _start_locked(
        self,
        snapshot: LiveTelemetrySnapshot,
    ) -> None:
        now_timestamp = time()

        date = datetime.fromtimestamp(
            now_timestamp,
            tz=timezone.utc,
        )

        session_id = (
            f"{date.strftime('%Y%m%d_%H%M%S')}_"
            f"{snapshot.session_uid}"
        )

        directory = self.root / session_id
        suffix = 1

        while directory.exists():
            directory = self.root / (
                f"{session_id}_{suffix}"
            )
            suffix += 1

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        active = ActiveRecording(
            session_id=directory.name,
            session_uid=int(
                snapshot.session_uid
            ),
            directory=directory,
            started_at=now_timestamp,
            started_at_iso=date.isoformat(),
        )

        self._active = active

        _json_dump(
            directory / "session.json",
            {
                "session_id": (
                    active.session_id
                ),
                "session_uid": (
                    active.session_uid
                ),
                "started_at": (
                    active.started_at_iso
                ),
                "ended_at": None,
                "status": "recording",
                "packet_format": (
                    snapshot.packet_format
                ),
                "game_year": (
                    snapshot.game_year
                ),
                "track_id": snapshot.track_id,
                "session_type": (
                    snapshot.session_type
                ),
                "track_length_m": (
                    snapshot.track_length_m
                ),
                "total_laps": (
                    snapshot.total_laps
                ),
                "player_name": (
                    snapshot.player_name
                ),
                "grid_position": (
                    snapshot.grid_position
                ),
                "finish_position": None,
                "recorded_samples": 0,
            },
        )

    def _write_incremental_locked(
        self,
        active: ActiveRecording,
        snapshot: LiveTelemetrySnapshot,
    ) -> None:
        should_sample = (
            active.last_telemetry_session_time < 0
            or (
                snapshot.session_time
                < active.last_telemetry_session_time
            )
            or (
                snapshot.session_time
                - active.last_telemetry_session_time
                >= self.sample_interval_s
            )
        )

        if should_sample:
            _append_jsonl(
                active.directory
                / "telemetry.jsonl",
                self._compact_snapshot(
                    snapshot
                ),
            )

            active.last_telemetry_session_time = (
                snapshot.session_time
            )
            active.telemetry_samples += 1

        messages = sorted(
            snapshot.recent_messages,
            key=lambda item: int(
                item.get("id", 0)
            ),
        )

        for message in messages:
            message_id = int(
                message.get("id", 0)
            )

            if message_id > active.last_message_id:
                _append_jsonl(
                    active.directory
                    / "messages.jsonl",
                    message,
                )
                active.last_message_id = (
                    message_id
                )

        events = sorted(
            snapshot.race_events,
            key=lambda item: int(
                item.get("id", 0)
            ),
        )

        for event in events:
            event_id = int(
                event.get("id", 0)
            )

            if event_id > active.last_event_id:
                _append_jsonl(
                    active.directory
                    / "events.jsonl",
                    event,
                )
                active.last_event_id = event_id

        if (
            len(snapshot.completed_laps)
            != active.last_lap_count
        ):
            _json_dump(
                active.directory
                / "laps.json",
                list(
                    reversed(
                        snapshot.completed_laps
                    )
                ),
            )

            active.last_lap_count = len(
                snapshot.completed_laps
            )

        if snapshot.classification:
            _json_dump(
                active.directory
                / "classification.json",
                snapshot.classification,
            )

        metadata_path = (
            active.directory
            / "session.json"
        )

        metadata = _read_json(
            metadata_path,
            {},
        )

        metadata.update({
            "track_id": snapshot.track_id,
            "session_type": (
                snapshot.session_type
            ),
            "track_length_m": (
                snapshot.track_length_m
            ),
            "total_laps": snapshot.total_laps,
            "player_name": (
                snapshot.player_name
            ),
            "grid_position": (
                snapshot.grid_position
            ),
            "current_position": (
                snapshot.position
            ),
            "recorded_samples": (
                active.telemetry_samples
            ),
        })

        _json_dump(
            metadata_path,
            metadata,
        )

    def _finalize_locked(
        self,
        reason: str,
        snapshot: (
            LiveTelemetrySnapshot | None
        ),
    ) -> dict[str, Any] | None:
        active = self._active

        if active is None:
            return None

        if snapshot is not None:
            self._write_incremental_locked(
                active,
                snapshot,
            )

            if snapshot.classification:
                _json_dump(
                    active.directory
                    / "classification.json",
                    snapshot.classification,
                )

            _json_dump(
                active.directory / "laps.json",
                list(
                    reversed(
                        snapshot.completed_laps
                    )
                ),
            )

        ended_at = datetime.now(
            tz=timezone.utc
        ).isoformat()

        metadata_path = (
            active.directory
            / "session.json"
        )

        metadata = _read_json(
            metadata_path,
            {},
        )

        metadata.update({
            "ended_at": ended_at,
            "status": "complete",
            "end_reason": reason,
            "recorded_samples": (
                active.telemetry_samples
            ),
            "finish_position": (
                snapshot.position
                if snapshot
                else metadata.get(
                    "current_position"
                )
            ),
            "positions_gained": (
                snapshot.positions_gained
                if snapshot
                else None
            ),
        })

        _json_dump(
            metadata_path,
            metadata,
        )

        self._closed_uids.add(
            active.session_uid
        )

        self._active = None

        return metadata

    @staticmethod
    def _compact_snapshot(
        snapshot: LiveTelemetrySnapshot,
    ) -> dict[str, Any]:
        return {
            "timestamp": time(),
            "session_time": (
                snapshot.session_time
            ),
            "lap_number": (
                snapshot.lap_number
            ),
            "sector": snapshot.sector,
            "position": snapshot.position,
            "grid_size": snapshot.grid_size,
            "lap_distance_m": (
                snapshot.lap_distance_m
            ),
            "total_distance_m": (
                snapshot.total_distance_m
            ),
            "current_lap_time_ms": (
                snapshot.current_lap_time_ms
            ),
            "speed_kph": snapshot.speed_kph,
            "throttle": snapshot.throttle,
            "brake": snapshot.brake,
            "steer": snapshot.steer,
            "gear": snapshot.gear,
            "rpm": snapshot.rpm,
            "drs": snapshot.drs,
            "fuel_remaining_laps": (
                snapshot.fuel_remaining_laps
            ),
            "fuel_in_tank_kg": (
                snapshot.fuel_in_tank_kg
            ),
            "ers_percent": (
                snapshot.ers_percent
            ),
            "tyre_compound": (
                snapshot.tyre_compound
            ),
            "tyre_age_laps": (
                snapshot.tyre_age_laps
            ),
            "tyre_wear_pct": (
                snapshot.tyre_wear_pct
            ),
            "tyre_surface_temps_c": (
                snapshot.tyre_surface_temps_c
            ),
            "brake_temps_c": (
                snapshot.brake_temps_c
            ),
            "wing_damage_pct": (
                snapshot.wing_damage_pct
            ),
            "world_position": (
                snapshot.world_position
            ),
            "g_force_lateral": (
                snapshot.g_force_lateral
            ),
            "g_force_longitudinal": (
                snapshot.g_force_longitudinal
            ),
            "lap_invalid": (
                snapshot.lap_invalid
            ),
            "penalties_s": (
                snapshot.penalties_s
            ),
            "pit_status": (
                snapshot.pit_status
            ),
            "pit_stops": snapshot.pit_stops,
            "delta_to_car_ahead_s": (
                snapshot.delta_to_car_ahead_s
            ),
            "delta_to_leader_s": (
                snapshot.delta_to_leader_s
            ),
        }

    @staticmethod
    def _read_jsonl(
        path: Path,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not path.exists():
            return []

        rows: list[dict[str, Any]] = []

        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            for line in handle:
                line = line.strip()

                if not line:
                    continue

                try:
                    rows.append(
                        json.loads(line)
                    )
                except json.JSONDecodeError:
                    continue

        if limit > 0:
            return rows[-limit:]

        return rows