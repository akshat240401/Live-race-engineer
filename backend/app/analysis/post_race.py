from __future__ import annotations

from math import sqrt
from statistics import mean, median
from typing import Any

from app.recording.session_recorder import (
    SessionRecorder,
)


def _safe_mean(
    values: list[float],
) -> float | None:
    return mean(values) if values else None


def _standard_deviation(
    values: list[float],
) -> float | None:
    if len(values) < 2:
        return None

    average = mean(values)

    return sqrt(
        sum(
            (value - average) ** 2
            for value in values
        )
        / len(values)
    )


def _rounded(
    value: float | None,
    digits: int = 3,
) -> float | None:
    if value is None:
        return None

    return round(value, digits)


class PostRaceAnalyzer:
    def __init__(
        self,
        recorder: SessionRecorder,
    ) -> None:
        self.recorder = recorder

    def build_report(
        self,
        session_id: str,
        save: bool = True,
    ) -> dict[str, Any]:
        bundle = (
            self.recorder.get_session_bundle(
                session_id
            )
        )

        metadata = bundle["metadata"]
        telemetry = bundle["telemetry"]
        laps = bundle["laps"]
        events = bundle["events"]
        messages = bundle["messages"]
        classification = bundle[
            "classification"
        ]

        valid_laps = [
            lap
            for lap in laps
            if bool(lap.get("valid", True))
            and int(
                lap.get("lap_time_ms", 0)
            )
            > 0
        ]

        lap_times_s = [
            int(lap["lap_time_ms"]) / 1000.0
            for lap in valid_laps
        ]

        best_lap_s = (
            min(lap_times_s)
            if lap_times_s
            else None
        )

        average_lap_s = _safe_mean(
            lap_times_s
        )

        median_lap_s = (
            median(lap_times_s)
            if lap_times_s
            else None
        )

        consistency_s = _standard_deviation(
            lap_times_s
        )

        start_position = int(
            metadata.get("grid_position") or 0
        )

        finish_position = int(
            metadata.get("finish_position")
            or metadata.get(
                "current_position"
            )
            or 0
        )

        positions_gained = (
            start_position - finish_position
            if (
                start_position
                and finish_position
            )
            else None
        )

        overtakes = [
            event
            for event in events
            if event.get("event_type")
            == "overtake"
        ]

        positions_lost = [
            event
            for event in events
            if event.get("event_type")
            == "position_lost"
        ]

        incidents = [
            event
            for event in events
            if event.get("event_type")
            in {
                "collision",
                "damage_increase",
                "possible_incident",
                "retirement",
            }
        ]

        penalties = [
            event
            for event in events
            if event.get("event_type")
            == "penalty"
        ]

        overlap_samples = [
            sample
            for sample in telemetry
            if (
                float(
                    sample.get(
                        "brake",
                        0.0,
                    )
                )
                >= 0.15
                and float(
                    sample.get(
                        "throttle",
                        0.0,
                    )
                )
                >= 0.15
            )
        ]

        overlap_seconds = (
            self._duration_of_samples(
                overlap_samples
            )
        )

        max_tyre_wear = 0.0
        max_tyre_temp = 0.0
        max_brake_temp = 0.0

        for sample in telemetry:
            wear = [
                float(value)
                for value in sample.get(
                    "tyre_wear_pct",
                    [],
                )
            ]

            tyre_temperatures = [
                float(value)
                for value in sample.get(
                    "tyre_surface_temps_c",
                    [],
                )
            ]

            brake_temperatures = [
                float(value)
                for value in sample.get(
                    "brake_temps_c",
                    [],
                )
            ]

            max_tyre_wear = max(
                max_tyre_wear,
                max(wear, default=0.0),
            )

            max_tyre_temp = max(
                max_tyre_temp,
                max(
                    tyre_temperatures,
                    default=0.0,
                ),
            )

            max_brake_temp = max(
                max_brake_temp,
                max(
                    brake_temperatures,
                    default=0.0,
                ),
            )

        fuel_start = (
            float(
                telemetry[0].get(
                    "fuel_in_tank_kg",
                    0.0,
                )
            )
            if telemetry
            else 0.0
        )

        fuel_end = (
            float(
                telemetry[-1].get(
                    "fuel_in_tank_kg",
                    0.0,
                )
            )
            if telemetry
            else 0.0
        )

        fuel_used_kg = max(
            0.0,
            fuel_start - fuel_end,
        )

        lap_rows: list[
            dict[str, Any]
        ] = []

        for lap in laps:
            lap_ms = int(
                lap.get(
                    "lap_time_ms",
                    0,
                )
            )

            lap_s = (
                lap_ms / 1000.0
                if lap_ms > 0
                else None
            )

            lap_rows.append({
                **lap,
                "lap_time_s": _rounded(lap_s),
                "delta_to_best_s": (
                    _rounded(
                        lap_s - best_lap_s
                    )
                    if (
                        lap_s is not None
                        and best_lap_s is not None
                    )
                    else None
                ),
            })

        pace_trend = self._pace_trend(
            lap_times_s
        )

        comparisons = (
            self._classification_comparison(
                classification,
                metadata,
            )
        )

        strengths, improvements = (
            self._recommendations(
                overlap_seconds=(
                    overlap_seconds
                ),
                max_tyre_temp=(
                    max_tyre_temp
                ),
                max_brake_temp=(
                    max_brake_temp
                ),
                consistency_s=consistency_s,
                pace_trend=pace_trend,
                incidents=len(incidents),
                positions_gained=(
                    positions_gained
                ),
                penalties=len(penalties),
            )
        )

        report = {
            "session_id": session_id,
            "generated_from": (
                "recorded telemetry"
            ),
            "summary": {
                "player_name": metadata.get(
                    "player_name",
                    "YOU",
                ),
                "track_id": metadata.get(
                    "track_id"
                ),
                "session_type": metadata.get(
                    "session_type"
                ),
                "start_position": (
                    start_position or None
                ),
                "finish_position": (
                    finish_position or None
                ),
                "positions_gained": (
                    positions_gained
                ),
                "completed_laps": len(laps),
                "valid_laps": len(valid_laps),
                "best_lap_s": _rounded(
                    best_lap_s
                ),
                "average_lap_s": _rounded(
                    average_lap_s
                ),
                "median_lap_s": _rounded(
                    median_lap_s
                ),
                "lap_consistency_s": _rounded(
                    consistency_s
                ),
                "overtakes_detected": len(
                    overtakes
                ),
                "positions_lost_detected": len(
                    positions_lost
                ),
                "incidents_detected": len(
                    incidents
                ),
                "penalties_detected": len(
                    penalties
                ),
                "brake_throttle_overlap_s": round(
                    overlap_seconds,
                    1,
                ),
                "max_tyre_wear_pct": round(
                    max_tyre_wear,
                    1,
                ),
                "max_tyre_temp_c": round(
                    max_tyre_temp,
                    1,
                ),
                "max_brake_temp_c": round(
                    max_brake_temp,
                    1,
                ),
                "fuel_used_kg": round(
                    fuel_used_kg,
                    2,
                ),
                "recorded_samples": len(
                    telemetry
                ),
                "pace_trend": pace_trend,
            },
            "strengths": strengths,
            "areas_to_improve": improvements,
            "lap_analysis": lap_rows,
            "timeline": sorted(
                events,
                key=lambda item: float(
                    item.get(
                        "session_time",
                        0.0,
                    )
                ),
            ),
            "coaching_messages": messages,
            "classification": classification,
            "comparisons": comparisons,
        }

        if save:
            self.recorder.save_report(
                session_id,
                report,
            )

        return report

    @staticmethod
    def _duration_of_samples(
        samples: list[dict[str, Any]],
    ) -> float:
        if len(samples) < 2:
            return 0.0

        ordered = sorted(
            samples,
            key=lambda item: float(
                item.get(
                    "session_time",
                    0.0,
                )
            ),
        )

        total = 0.0

        previous = float(
            ordered[0].get(
                "session_time",
                0.0,
            )
        )

        for sample in ordered[1:]:
            current = float(
                sample.get(
                    "session_time",
                    previous,
                )
            )

            delta = current - previous

            if 0 < delta <= 1.0:
                total += delta

            previous = current

        return total

    @staticmethod
    def _pace_trend(
        lap_times_s: list[float],
    ) -> str:
        if len(lap_times_s) < 4:
            return "insufficient-data"

        midpoint = len(lap_times_s) // 2

        early = mean(
            lap_times_s[:midpoint]
        )

        late = mean(
            lap_times_s[midpoint:]
        )

        delta = late - early

        if delta <= -0.35:
            return "improving"

        if delta >= 0.75:
            return "degrading"

        return "stable"

    @staticmethod
    def _classification_comparison(
        classification: list[
            dict[str, Any]
        ],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if not classification:
            return {
                "player": None,
                "ahead": None,
                "behind": None,
                "leader": None,
            }

        rows = sorted(
            classification,
            key=lambda item: int(
                item.get("position", 999)
            ),
        )

        player_name = str(
            metadata.get(
                "player_name",
                "",
            )
        ).strip().lower()

        finish_position = int(
            metadata.get("finish_position")
            or metadata.get(
                "current_position"
            )
            or 0
        )

        player = next(
            (
                row
                for row in rows
                if (
                    player_name
                    and str(
                        row.get(
                            "name",
                            "",
                        )
                    ).strip().lower()
                    == player_name
                )
            ),
            None,
        )

        if (
            player is None
            and finish_position
        ):
            player = next(
                (
                    row
                    for row in rows
                    if int(
                        row.get(
                            "position",
                            0,
                        )
                    )
                    == finish_position
                ),
                None,
            )

        if player is None:
            return {
                "player": None,
                "ahead": None,
                "behind": None,
                "leader": rows[0],
            }

        position = int(
            player.get(
                "position",
                0,
            )
        )

        ahead = next(
            (
                row
                for row in rows
                if int(
                    row.get(
                        "position",
                        0,
                    )
                )
                == position - 1
            ),
            None,
        )

        behind = next(
            (
                row
                for row in rows
                if int(
                    row.get(
                        "position",
                        0,
                    )
                )
                == position + 1
            ),
            None,
        )

        return {
            "player": player,
            "ahead": ahead,
            "behind": behind,
            "leader": rows[0],
        }

    @staticmethod
    def _recommendations(
        *,
        overlap_seconds: float,
        max_tyre_temp: float,
        max_brake_temp: float,
        consistency_s: float | None,
        pace_trend: str,
        incidents: int,
        positions_gained: int | None,
        penalties: int,
    ) -> tuple[list[str], list[str]]:
        strengths: list[str] = []
        improvements: list[str] = []

        if (
            consistency_s is not None
            and consistency_s <= 0.7
        ):
            strengths.append(
                "Lap pace was consistent "
                "across the session."
            )

        elif (
            consistency_s is not None
            and consistency_s >= 1.6
        ):
            improvements.append(
                "Reduce lap-to-lap variation "
                "by using repeatable braking "
                "and turn-in references."
            )

        if (
            positions_gained is not None
            and positions_gained > 0
        ):
            strengths.append(
                "Racecraft was productive: "
                f"{positions_gained} net "
                "position(s) gained."
            )

        elif (
            positions_gained is not None
            and positions_gained < 0
        ):
            improvements.append(
                "Review the position-loss "
                "timeline and identify whether "
                "pace, incidents, or pit timing "
                "caused the losses."
            )

        if pace_trend == "improving":
            strengths.append(
                "Pace improved during the "
                "second half of the session."
            )

        elif pace_trend == "degrading":
            improvements.append(
                "Late-session pace degraded; "
                "review tyre temperatures, "
                "wear, and fuel/ERS management."
            )

        if overlap_seconds >= 2.0:
            improvements.append(
                "Brake and throttle overlapped "
                f"for about {overlap_seconds:.1f}s. "
                "Separate the pedal phases to "
                "improve stability and tyre control."
            )
        else:
            strengths.append(
                "Brake/throttle overlap was "
                "well controlled."
            )

        if max_tyre_temp >= 106:
            improvements.append(
                "Tyre surface temperatures ran "
                "high; reduce sliding and "
                "aggressive throttle application."
            )

        if max_brake_temp >= 980:
            improvements.append(
                "Brake temperatures reached a "
                "critical range; avoid dragging "
                "the brake and open the cooling phase."
            )

        if incidents > 0:
            improvements.append(
                f"Review the {incidents} detected "
                "incident(s) and the telemetry "
                "immediately before each one."
            )

        if penalties > 0:
            improvements.append(
                "Review penalty events and "
                "track-limit usage."
            )

        if not strengths:
            strengths.append(
                "The session produced enough "
                "structured data to establish a "
                "useful performance baseline."
            )

        if not improvements:
            improvements.append(
                "Compare braking points and "
                "minimum corner speeds against "
                "the best lap."
            )

        return strengths, improvements