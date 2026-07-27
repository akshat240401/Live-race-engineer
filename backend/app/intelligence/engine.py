from __future__ import annotations

import math
import os
import statistics
from collections import deque
from dataclasses import dataclass, field
from time import time
from typing import Any, Iterable

from .models import (
    BattleIntelligence,
    BattleProbabilities,
    DecisionEvent,
    ForecastPoint,
    ModelMeta,
    RelativePace,
    RivalModel,
)


_EPSILON = 1e-9


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _safe_float(value: Any, default: float = 0.0) -> float:
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


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _median_absolute_deviation(values: list[float]) -> float:
    if not values:
        return 0.0
    centre = statistics.median(values)
    return statistics.median(abs(value - centre) for value in values)


@dataclass(slots=True)
class IntelligenceConfig:
    # DRS eligibility is an F1 game rule, not a strategy threshold.
    drs_window_s: float = 1.0
    history_seconds: float = 180.0
    forecast_laps: int = 3
    timeline_size: int = 12
    state_confidence_z: float = 1.96

    @classmethod
    def from_environment(cls) -> "IntelligenceConfig":
        return cls(
            drs_window_s=_safe_float(
                os.getenv("INTELLIGENCE_DRS_WINDOW_S"), 1.0
            ),
            history_seconds=max(
                30.0,
                _safe_float(os.getenv("INTELLIGENCE_HISTORY_SECONDS"), 180.0),
            ),
            forecast_laps=max(
                1,
                _safe_int(os.getenv("INTELLIGENCE_FORECAST_LAPS"), 3),
            ),
            timeline_size=max(
                4,
                _safe_int(os.getenv("INTELLIGENCE_TIMELINE_SIZE"), 12),
            ),
            state_confidence_z=max(
                0.5,
                _safe_float(os.getenv("INTELLIGENCE_STATE_CONFIDENCE_Z"), 1.96),
            ),
        )


@dataclass(slots=True)
class GapObservation:
    session_time: float
    gap_s: float
    lap_number: int
    position: int | None
    pit_status: int
    pit_stops: int
    last_lap_s: float | None


@dataclass(slots=True)
class RegressionResult:
    current_gap_s: float
    slope_s_per_second: float
    slope_standard_error: float
    residual_standard_error: float
    r_squared: float
    span_s: float
    sample_count: int
    model_quality: float

    def forecast(self, seconds_ahead: float) -> tuple[float, float]:
        mean = self.current_gap_s + self.slope_s_per_second * seconds_ahead
        variance = (
            self.residual_standard_error**2
            + (self.slope_standard_error * seconds_ahead) ** 2
        )
        return mean, math.sqrt(max(variance, _EPSILON))

    def closing_probability(self) -> float:
        if self.slope_standard_error <= _EPSILON:
            if self.slope_s_per_second < 0:
                return 1.0
            if self.slope_s_per_second > 0:
                return 0.0
            return 0.5
        return _normal_cdf(
            (0.0 - self.slope_s_per_second) / self.slope_standard_error
        )


@dataclass(slots=True)
class RivalHistory:
    name: str = ""
    observations: deque[GapObservation] = field(default_factory=deque)
    trend_samples_s_per_lap: deque[float] = field(default_factory=lambda: deque(maxlen=250))
    model_quality_samples: deque[float] = field(default_factory=lambda: deque(maxlen=250))

    def reset(self, name: str) -> None:
        self.name = name
        self.observations.clear()
        self.trend_samples_s_per_lap.clear()
        self.model_quality_samples.clear()


class AdaptiveBattleIntelligence:
    """Session-trained battle analysis.

    The engine does not use canned attack/defence percentages or fixed strategy
    phrases. It learns gap direction, uncertainty, persistence and forecast
    distributions from the active session. The only domain constant used in the
    battle probability is the configured DRS eligibility window.
    """

    def __init__(self, config: IntelligenceConfig | None = None) -> None:
        self.config = config or IntelligenceConfig.from_environment()
        self._session_uid: int | None = None
        self._ahead = RivalHistory()
        self._behind = RivalHistory()
        self._lap_time_samples: deque[float] = deque(maxlen=40)
        self._timeline: deque[DecisionEvent] = deque(maxlen=self.config.timeline_size)
        self._last_signature: tuple[str, str | None, str | None] | None = None

    def reset(self) -> None:
        self._session_uid = None
        self._ahead.reset("")
        self._behind.reset("")
        self._lap_time_samples.clear()
        self._timeline.clear()
        self._last_signature = None

    def analyze(self, snapshot: Any) -> BattleIntelligence:
        now = time()
        connected = bool(_field(snapshot, "connected", False))
        session_uid = self._normalise_session_uid(_field(snapshot, "session_uid"))
        self._handle_session_change(session_uid)

        session_time = _safe_float(_field(snapshot, "session_time", 0.0))
        lap_number = self._positive_int(_field(snapshot, "lap_number"))
        lap_time_s = self._update_lap_time_estimate(snapshot)

        ahead_car = _field(snapshot, "car_ahead")
        behind_car = _field(snapshot, "car_behind")

        ahead_name = self._car_name(ahead_car)
        behind_name = self._car_name(behind_car)

        ahead_gap = self._ahead_gap(snapshot, ahead_car)
        behind_gap = self._behind_gap(snapshot, behind_car)

        self._ingest(
            self._ahead,
            ahead_name,
            ahead_gap,
            session_time,
            lap_number,
            ahead_car,
        )
        self._ingest(
            self._behind,
            behind_name,
            behind_gap,
            session_time,
            lap_number,
            behind_car,
        )

        ahead_fit = self._fit(self._ahead, lap_time_s)
        behind_fit = self._fit(self._behind, lap_time_s)

        ahead_model = self._rival_model(
            role="ahead",
            car=ahead_car,
            history=self._ahead,
            fit=ahead_fit,
            lap_time_s=lap_time_s,
        )
        behind_model = self._rival_model(
            role="behind",
            car=behind_car,
            history=self._behind,
            fit=behind_fit,
            lap_time_s=lap_time_s,
        )

        probabilities = self._battle_probabilities(ahead_model, behind_model)
        probability_map = probabilities.to_dict()
        state = max(probability_map, key=probability_map.get)
        target_role, target = self._target(state, ahead_model, behind_model)
        confidence = self._decision_confidence(
            state, probabilities, ahead_model, behind_model
        )
        window_laps = self._window_laps(
            state, ahead_fit, behind_fit, lap_time_s
        )

        forecasts = self._forecast_points(
            ahead_fit=ahead_fit,
            behind_fit=behind_fit,
            lap_time_s=lap_time_s,
        )

        data_quality = self._data_quality(ahead_model, behind_model, connected)
        sample_count = len(self._ahead.observations) + len(self._behind.observations)
        (
            decision_resolved,
            state_margin,
            dominant_probability,
            runner_up_probability,
            effective_sample_count,
        ) = self._state_resolution(
            probabilities=probabilities,
            sample_count=sample_count,
            data_quality=data_quality,
            connected=connected,
        )

        self._update_timeline(
            now=now,
            session_time=session_time,
            lap_number=lap_number,
            state=state,
            target=target,
            target_role=target_role,
            confidence=confidence,
        )

        return BattleIntelligence(
            generated_at=now,
            connected=connected,
            state=state if connected else "observe",
            target=target,
            target_role=target_role,
            confidence=round(confidence, 4),
            decision_resolved=decision_resolved,
            state_margin=round(state_margin, 4),
            dominant_probability=round(dominant_probability, 4),
            runner_up_probability=round(runner_up_probability, 4),
            window_laps=window_laps,
            probabilities=probabilities,
            ahead=ahead_model,
            behind=behind_model,
            relative_pace=RelativePace(
                ahead_s_per_lap=self._relative_pace(ahead_fit, lap_time_s),
                behind_s_per_lap=self._relative_pace(behind_fit, lap_time_s),
                ahead_confidence=round(ahead_fit.model_quality, 4) if ahead_fit else 0.0,
                behind_confidence=round(behind_fit.model_quality, 4) if behind_fit else 0.0,
            ),
            forecast=forecasts,
            timeline=list(self._timeline),
            model=ModelMeta(
                name="adaptive-battle-model-v1",
                method="robust session regression + probabilistic race-state inference",
                session_uid=session_uid,
                sample_count=sample_count,
                effective_sample_count=effective_sample_count,
                lap_time_estimate_s=round(lap_time_s, 3) if lap_time_s else None,
                data_quality=round(data_quality, 4),
                drs_window_s=self.config.drs_window_s,
                state_confidence_z=self.config.state_confidence_z,
            ),
        )

    def _normalise_session_uid(self, value: Any) -> int | None:
        uid = _safe_int(value, 0)
        return uid if uid > 0 else None

    def _handle_session_change(self, session_uid: int | None) -> None:
        if session_uid is None:
            return
        if self._session_uid is None:
            self._session_uid = session_uid
            return
        if session_uid != self._session_uid:
            self.reset()
            self._session_uid = session_uid

    def _positive_int(self, value: Any) -> int | None:
        number = _safe_int(value, 0)
        return number if number > 0 else None

    def _car_name(self, car: Any) -> str:
        name = str(_field(car, "name", "") or "").strip()
        return name or "UNKNOWN"

    def _update_lap_time_estimate(self, snapshot: Any) -> float | None:
        candidates = [
            _safe_float(_field(snapshot, "last_lap_time_ms")) / 1000.0,
            _safe_float(_field(snapshot, "best_lap_time_ms")) / 1000.0,
        ]

        for lap in list(_field(snapshot, "completed_laps", []) or []):
            for key in ("lap_time_s", "lap_time_ms", "time_s", "time_ms"):
                value = _field(lap, key)
                if value is None:
                    continue
                parsed = _safe_float(value)
                if key.endswith("_ms"):
                    parsed /= 1000.0
                candidates.append(parsed)
                break

        for value in candidates:
            # Reject only impossible timing values; this is data validation, not
            # a strategy threshold.
            if 20.0 <= value <= 600.0:
                if not self._lap_time_samples or abs(value - self._lap_time_samples[-1]) > 1e-6:
                    self._lap_time_samples.append(value)

        if self._lap_time_samples:
            return statistics.median(self._lap_time_samples)

        track_length = _safe_float(_field(snapshot, "track_length_m"))
        speed_kph = _safe_float(_field(snapshot, "speed_kph"))
        if track_length > 0 and speed_kph > 0:
            return track_length / (speed_kph / 3.6)
        return None

    def _ahead_gap(self, snapshot: Any, ahead_car: Any) -> float | None:
        direct = _safe_float(_field(snapshot, "delta_to_car_ahead_s"), -1.0)
        if direct >= 0:
            return direct

        player_to_leader = _safe_float(_field(snapshot, "delta_to_leader_s"), -1.0)
        ahead_to_leader = _safe_float(_field(ahead_car, "delta_to_leader_s"), -1.0)
        if player_to_leader >= 0 and ahead_to_leader >= 0:
            return max(0.0, player_to_leader - ahead_to_leader)
        return None

    def _behind_gap(self, snapshot: Any, behind_car: Any) -> float | None:
        behind_direct = _safe_float(_field(behind_car, "delta_to_car_ahead_s"), -1.0)
        if behind_direct >= 0:
            return behind_direct

        player_to_leader = _safe_float(_field(snapshot, "delta_to_leader_s"), -1.0)
        behind_to_leader = _safe_float(_field(behind_car, "delta_to_leader_s"), -1.0)
        if player_to_leader >= 0 and behind_to_leader >= 0:
            return max(0.0, behind_to_leader - player_to_leader)
        return None

    def _ingest(
        self,
        history: RivalHistory,
        name: str,
        gap_s: float | None,
        session_time: float,
        lap_number: int | None,
        car: Any,
    ) -> None:
        if name != history.name:
            history.reset(name)

        if gap_s is None or not math.isfinite(gap_s) or gap_s < 0:
            return

        if history.observations and session_time <= history.observations[-1].session_time:
            return

        last_lap_ms = _safe_float(_field(car, "last_lap_time_ms"))
        last_lap_s = last_lap_ms / 1000.0 if last_lap_ms > 0 else None

        history.observations.append(
            GapObservation(
                session_time=session_time,
                gap_s=gap_s,
                lap_number=lap_number or 0,
                position=self._positive_int(_field(car, "position")),
                pit_status=_safe_int(_field(car, "pit_status"), 0),
                pit_stops=_safe_int(_field(car, "pit_stops"), 0),
                last_lap_s=last_lap_s,
            )
        )

        lower_bound = session_time - self.config.history_seconds
        while history.observations and history.observations[0].session_time < lower_bound:
            history.observations.popleft()

    def _fit(self, history: RivalHistory, lap_time_s: float | None) -> RegressionResult | None:
        observations = list(history.observations)
        if not observations:
            return None

        if len(observations) == 1:
            gap = observations[-1].gap_s
            return RegressionResult(
                current_gap_s=gap,
                slope_s_per_second=0.0,
                slope_standard_error=max(gap * 0.1, 0.05),
                residual_standard_error=max(gap * 0.1, 0.05),
                r_squared=0.0,
                span_s=0.0,
                sample_count=1,
                model_quality=0.0,
            )

        times = [item.session_time for item in observations]
        gaps = [item.gap_s for item in observations]

        # Robust, session-derived outlier filtering using median absolute
        # deviation. No race-action threshold is encoded here.
        median_gap = statistics.median(gaps)
        mad = _median_absolute_deviation(gaps)
        if mad > _EPSILON:
            robust_scale = 1.4826 * mad
            retained = [
                item
                for item in observations
                if abs(item.gap_s - median_gap) / robust_scale <= 4.5
            ]
            if len(retained) >= 3:
                observations = retained
                times = [item.session_time for item in observations]
                gaps = [item.gap_s for item in observations]

        origin = times[0]
        x = [value - origin for value in times]
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(gaps)
        sxx = sum((value - x_mean) ** 2 for value in x)

        if sxx <= _EPSILON:
            slope = 0.0
            intercept = y_mean
        else:
            slope = sum(
                (x_value - x_mean) * (y_value - y_mean)
                for x_value, y_value in zip(x, gaps)
            ) / sxx
            intercept = y_mean - slope * x_mean

        fitted = [intercept + slope * value for value in x]
        residuals = [actual - predicted for actual, predicted in zip(gaps, fitted)]
        residual_sum = sum(value**2 for value in residuals)
        total_sum = sum((value - y_mean) ** 2 for value in gaps)
        degrees = max(1, len(gaps) - 2)
        residual_se = math.sqrt(residual_sum / degrees)
        slope_se = math.sqrt((residual_sum / degrees) / max(sxx, _EPSILON))
        r_squared = 1.0 - residual_sum / total_sum if total_sum > _EPSILON else 0.0
        r_squared = _clamp(r_squared)
        span = max(0.0, times[-1] - times[0])

        coverage = _clamp(span / lap_time_s) if lap_time_s and lap_time_s > 0 else 0.0
        continuity = _clamp(len(observations) / max(2.0, span * 1.5)) if span > 0 else 0.0
        certainty = 1.0 / (1.0 + residual_se)
        quality = _clamp((coverage + continuity + r_squared + certainty) / 4.0)

        result = RegressionResult(
            current_gap_s=gaps[-1],
            slope_s_per_second=slope,
            slope_standard_error=slope_se,
            residual_standard_error=max(residual_se, 0.01),
            r_squared=r_squared,
            span_s=span,
            sample_count=len(observations),
            model_quality=quality,
        )

        if lap_time_s:
            history.trend_samples_s_per_lap.append(slope * lap_time_s)
        history.model_quality_samples.append(quality)
        return result

    def _rival_model(
        self,
        role: str,
        car: Any,
        history: RivalHistory,
        fit: RegressionResult | None,
        lap_time_s: float | None,
    ) -> RivalModel | None:
        if car is None or fit is None:
            return None

        seconds = lap_time_s or 0.0
        predicted, sigma = fit.forecast(seconds)
        p_drs = self._probability_below(predicted, sigma, self.config.drs_window_s)
        p_closing = fit.closing_probability()
        trend = fit.slope_s_per_second * seconds if seconds else None

        gaps = [item.gap_s for item in history.observations]
        spread = statistics.pstdev(gaps) if len(gaps) > 1 else max(fit.current_gap_s, 1.0)
        consistency = 1.0 - _clamp(fit.residual_standard_error / max(spread, _EPSILON))
        pressure = math.sqrt(max(0.0, p_drs * p_closing))

        return RivalModel(
            role=role,
            name=history.name or self._car_name(car),
            position=self._positive_int(_field(car, "position")),
            current_gap_s=round(fit.current_gap_s, 3),
            predicted_gap_next_lap_s=round(max(0.0, predicted), 3),
            gap_trend_s_per_lap=round(trend, 3) if trend is not None else None,
            closing_probability=round(p_closing, 4),
            drs_probability_next_lap=round(p_drs, 4),
            pressure_score=round(pressure, 4),
            consistency_score=round(_clamp(consistency), 4),
            predictability_score=round(fit.r_squared, 4),
            sample_count=fit.sample_count,
            model_quality=round(fit.model_quality, 4),
            pit_status=_safe_int(_field(car, "pit_status"), 0),
            pit_stops=_safe_int(_field(car, "pit_stops"), 0),
        )

    def _battle_probabilities(
        self,
        ahead: RivalModel | None,
        behind: RivalModel | None,
    ) -> BattleProbabilities:
        attack_likelihood = (
            math.sqrt(
                ahead.drs_probability_next_lap * ahead.closing_probability
            )
            * ahead.model_quality
            if ahead
            else 0.0
        )
        defend_likelihood = (
            math.sqrt(
                behind.drs_probability_next_lap * behind.closing_probability
            )
            * behind.model_quality
            if behind
            else 0.0
        )

        raw = {
            "attack": attack_likelihood * (1.0 - defend_likelihood),
            "defend": defend_likelihood * (1.0 - attack_likelihood),
            "contested": attack_likelihood * defend_likelihood,
            "clear": (1.0 - attack_likelihood) * (1.0 - defend_likelihood),
        }
        total = sum(raw.values()) or 1.0
        return BattleProbabilities(
            attack=round(raw["attack"] / total, 4),
            defend=round(raw["defend"] / total, 4),
            contested=round(raw["contested"] / total, 4),
            clear=round(raw["clear"] / total, 4),
        )


    def _wilson_interval(self, probability: float, sample_count: int) -> tuple[float, float]:
        n = max(1, sample_count)
        p = _clamp(probability)
        z = self.config.state_confidence_z
        z2 = z * z
        denominator = 1.0 + z2 / n
        centre = (p + z2 / (2.0 * n)) / denominator
        half_width = (
            z
            * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))
            / denominator
        )
        return _clamp(centre - half_width), _clamp(centre + half_width)

    def _state_resolution(
        self,
        probabilities: BattleProbabilities,
        sample_count: int,
        data_quality: float,
        connected: bool,
    ) -> tuple[bool, float, float, float, int]:
        ordered = sorted(probabilities.to_dict().values(), reverse=True)
        dominant = ordered[0] if ordered else 0.0
        runner_up = ordered[1] if len(ordered) > 1 else 0.0

        # Convert model quality into an effective sample size. This prevents an
        # apparently decisive one-sample estimate from being presented as a
        # resolved race state while still allowing clean, persistent evidence
        # to become authoritative naturally.
        effective_samples = max(1, int(round(max(1, sample_count) * _clamp(data_quality))))
        dominant_low, _ = self._wilson_interval(dominant, effective_samples)
        _, runner_high = self._wilson_interval(runner_up, effective_samples)
        margin = dominant_low - runner_high
        resolved = bool(connected and margin > 0.0)
        return resolved, margin, dominant, runner_up, effective_samples

    def _target(
        self,
        state: str,
        ahead: RivalModel | None,
        behind: RivalModel | None,
    ) -> tuple[str | None, str | None]:
        if state == "attack" and ahead:
            return "ahead", ahead.name
        if state == "defend" and behind:
            return "behind", behind.name
        if state == "contested":
            candidates = [item for item in (ahead, behind) if item]
            if candidates:
                target = max(candidates, key=lambda item: item.pressure_score)
                return target.role, target.name
        return None, None

    def _decision_confidence(
        self,
        state: str,
        probabilities: BattleProbabilities,
        ahead: RivalModel | None,
        behind: RivalModel | None,
    ) -> float:
        probability = probabilities.to_dict()[state]
        qualities = [item.model_quality for item in (ahead, behind) if item]
        quality = statistics.mean(qualities) if qualities else 0.0
        return _clamp(probability * quality)

    def _window_laps(
        self,
        state: str,
        ahead_fit: RegressionResult | None,
        behind_fit: RegressionResult | None,
        lap_time_s: float | None,
    ) -> int | None:
        fit = ahead_fit if state == "attack" else behind_fit if state == "defend" else None
        if fit is None or lap_time_s is None:
            return None

        probabilities = []
        for horizon in range(self.config.forecast_laps + 1):
            mean, sigma = fit.forecast(lap_time_s * horizon)
            probabilities.append(
                (horizon, self._probability_below(mean, sigma, self.config.drs_window_s))
            )
        return max(probabilities, key=lambda item: item[1])[0]

    def _forecast_points(
        self,
        ahead_fit: RegressionResult | None,
        behind_fit: RegressionResult | None,
        lap_time_s: float | None,
    ) -> list[ForecastPoint]:
        points: list[ForecastPoint] = []
        if lap_time_s is None:
            lap_time_s = 0.0

        for horizon in range(self.config.forecast_laps + 1):
            seconds = lap_time_s * horizon
            ahead = self._forecast_payload(ahead_fit, seconds)
            behind = self._forecast_payload(behind_fit, seconds)
            points.append(
                ForecastPoint(
                    horizon_laps=horizon,
                    ahead_gap_s=ahead[0],
                    ahead_low_s=ahead[1],
                    ahead_high_s=ahead[2],
                    ahead_drs_probability=ahead[3],
                    behind_gap_s=behind[0],
                    behind_low_s=behind[1],
                    behind_high_s=behind[2],
                    behind_drs_probability=behind[3],
                )
            )
        return points

    def _forecast_payload(
        self, fit: RegressionResult | None, seconds: float
    ) -> tuple[float | None, float | None, float | None, float | None]:
        if fit is None:
            return None, None, None, None
        mean, sigma = fit.forecast(seconds)
        low = max(0.0, mean - 1.96 * sigma)
        high = max(0.0, mean + 1.96 * sigma)
        probability = self._probability_below(mean, sigma, self.config.drs_window_s)
        return (
            round(max(0.0, mean), 3),
            round(low, 3),
            round(high, 3),
            round(probability, 4),
        )

    def _probability_below(self, mean: float, sigma: float, threshold: float) -> float:
        if sigma <= _EPSILON:
            return 1.0 if mean <= threshold else 0.0
        return _clamp(_normal_cdf((threshold - mean) / sigma))

    def _relative_pace(
        self, fit: RegressionResult | None, lap_time_s: float | None
    ) -> float | None:
        if fit is None or lap_time_s is None:
            return None
        # Positive means the player is gaining on this rival.
        return round(-fit.slope_s_per_second * lap_time_s, 3)

    def _data_quality(
        self,
        ahead: RivalModel | None,
        behind: RivalModel | None,
        connected: bool,
    ) -> float:
        if not connected:
            return 0.0
        qualities = [item.model_quality for item in (ahead, behind) if item]
        return statistics.mean(qualities) if qualities else 0.0

    def _update_timeline(
        self,
        now: float,
        session_time: float,
        lap_number: int | None,
        state: str,
        target: str | None,
        target_role: str | None,
        confidence: float,
    ) -> None:
        signature = (state, target, target_role)
        if signature == self._last_signature:
            return
        self._last_signature = signature
        self._timeline.append(
            DecisionEvent(
                timestamp=now,
                session_time=session_time,
                lap_number=lap_number,
                state=state,
                target=target,
                confidence=round(confidence, 4),
            )
        )
