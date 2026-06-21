from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import mean
from time import time
from typing import Any

from app.strategy.models import (
    BattleState,
    BoxAction,
    BoxDecision,
    CoachingPlan,
    EnergyAction,
    EnergyPlan,
    LiveRaceDecision,
    NearbyCarAssessment,
    TyreProjection,
)


@dataclass(slots=True)
class StrategyAutomaticCall:
    text: str
    priority: int
    category: str
    key: str


class LiveStrategicEngineer:
    """Stateful deterministic race-strategy and battle coach.

    The engine only uses available telemetry. Missing rival tyre or weather data is
    treated as unknown instead of being invented. Track-specific values such as pit
    loss remain configurable estimates until a measured value is available.
    """

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._samples: deque[dict[str, float]] = deque(maxlen=600)
        self._wear_by_lap: dict[int, float] = {}
        self._latest = LiveRaceDecision.empty()
        self._pending_call: StrategyAutomaticCall | None = None
        self._last_call_signature: str | None = None
        self._last_session_uid: int | None = None
        self._last_lap_number = 0

    def reset(self) -> None:
        self._samples.clear()
        self._wear_by_lap.clear()
        self._latest = LiveRaceDecision.empty()
        self._pending_call = None
        self._last_call_signature = None
        self._last_session_uid = None
        self._last_lap_number = 0

    def latest(self) -> LiveRaceDecision:
        return self._latest

    def latest_dict(self) -> dict[str, Any]:
        return self._latest.to_dict()

    def pop_automatic_call(self) -> StrategyAutomaticCall | None:
        result = self._pending_call
        self._pending_call = None
        return result

    def evaluate(self, snapshot: Any) -> LiveRaceDecision:
        session_uid = self._int(snapshot, "session_uid")
        if session_uid and self._last_session_uid and session_uid != self._last_session_uid:
            self.reset()
        if session_uid:
            self._last_session_uid = session_uid

        previous = self._latest
        connected = bool(getattr(snapshot, "connected", False))
        if not connected:
            self._latest = LiveRaceDecision.empty()
            return self._latest

        self._record_sample(snapshot)
        tyres = self._project_tyres(snapshot)
        ahead = self._nearby(snapshot, role="ahead")
        behind = self._nearby(snapshot, role="behind")
        box = self._box_decision(snapshot, tyres, ahead, behind)
        battle_state = self._battle_state(snapshot, tyres, box, ahead, behind)
        energy = self._energy_plan(snapshot, battle_state, tyres, ahead, behind)
        coaching = self._coaching_plan(snapshot, battle_state, tyres)
        laps_remaining = self._laps_remaining(snapshot)
        quality = self._data_quality(snapshot, ahead, behind)

        reasons: list[str] = []
        reasons.extend(box.reason_codes)
        if ahead and ahead.in_drs_range:
            reasons.append("car_ahead_in_drs")
        if behind and behind.in_drs_range:
            reasons.append("car_behind_in_drs")
        if energy.action == EnergyAction.HARVEST:
            reasons.append("battery_recovery")

        decision = LiveRaceDecision(
            generated_at=time(),
            connected=True,
            battle_state=battle_state,
            position=self._positive_int(snapshot, "position"),
            lap_number=self._positive_int(snapshot, "lap_number"),
            total_laps=self._positive_int(snapshot, "total_laps"),
            laps_remaining=laps_remaining,
            car_ahead=ahead,
            car_behind=behind,
            tyres=tyres,
            box=box,
            energy=energy,
            coaching=coaching,
            data_quality=quality,
            reason_codes=list(dict.fromkeys(reasons)),
        )
        self._latest = decision
        self._pending_call = self._build_automatic_call(previous, decision)
        return decision

    def box_response(self, decision: LiveRaceDecision | None = None) -> str:
        d = decision or self._latest
        box = d.box
        prefix = {
            BoxAction.BOX_NOW: "Box this lap.",
            BoxAction.STAY_OUT: "Stay out.",
            BoxAction.CONDITIONAL: "Conditional box call.",
            BoxAction.ALREADY_BOXING: "You are already committed to boxing.",
            BoxAction.UNKNOWN: "I cannot make a grounded box call yet.",
        }[box.action]
        rejoin = ""
        if box.expected_rejoin_position:
            rejoin = f" Estimated rejoin P{box.expected_rejoin_position}."
        return f"{prefix} {box.summary}{rejoin}".strip()

    def rejoin_response(self, decision: LiveRaceDecision | None = None) -> str:
        box = (decision or self._latest).box
        if box.expected_rejoin_position is None:
            return "I do not have enough classification data to estimate the rejoin position."
        traffic = ""
        if box.traffic_cars:
            traffic = f" Likely traffic: {', '.join(box.traffic_cars[:3])}."
        loss = box.estimated_positions_lost or 0
        return (
            f"Estimated rejoin is P{box.expected_rejoin_position}, about {loss} "
            f"position{'s' if loss != 1 else ''} lost during the stop.{traffic}"
        )

    def tyre_life_response(self, decision: LiveRaceDecision | None = None) -> str:
        tyres = (decision or self._latest).tyres
        if tyres.can_finish is None:
            return "I do not have enough tyre and race-distance data to project the finish."
        projected = tyres.projected_finish_wear_pct
        projected_text = (
            f" Projected finish wear is about {projected:.0f}%." if projected is not None else ""
        )
        if tyres.can_finish:
            return f"Yes, the tyres should reach the end if temperatures stay controlled.{projected_text}"
        return f"No, the tyres are unlikely to reach the end safely at the current rate.{projected_text}"

    def attack_response(self, decision: LiveRaceDecision | None = None) -> str:
        d = decision or self._latest
        ahead = d.car_ahead
        if not ahead or ahead.gap_s is None:
            return "I do not have a reliable car-ahead gap yet."
        if d.battle_state == BattleState.ATTACKING:
            return f"Attack plan: {d.energy.summary} Gap ahead is {ahead.gap_s:.1f} seconds."
        if d.energy.action == EnergyAction.HARVEST:
            return f"Not yet. {d.energy.summary} Build the gap down with clean exits."
        return f"Build the attack. {d.energy.summary} Gap ahead is {ahead.gap_s:.1f} seconds."

    def defend_response(self, decision: LiveRaceDecision | None = None) -> str:
        d = decision or self._latest
        behind = d.car_behind
        if not behind or behind.gap_s is None:
            return "I do not have a reliable car-behind gap yet."
        if d.battle_state == BattleState.DEFENDING:
            return f"Defend this lap. {d.energy.summary} Gap behind is {behind.gap_s:.1f} seconds."
        return f"No immediate defence required. Gap behind is {behind.gap_s:.1f} seconds. {d.energy.summary}"

    def energy_response(self, decision: LiveRaceDecision | None = None) -> str:
        return (decision or self._latest).energy.summary

    def nearby_response(self, role: str, decision: LiveRaceDecision | None = None) -> str:
        d = decision or self._latest
        car = d.car_ahead if role == "ahead" else d.car_behind
        if not car or car.gap_s is None:
            return f"No reliable car-{role} information yet."
        trend = ""
        if car.gap_trend_s_per_lap is not None:
            if role == "ahead":
                trend = " You are closing." if car.gap_trend_s_per_lap < -0.08 else " The gap is opening." if car.gap_trend_s_per_lap > 0.08 else " The gap is stable."
            else:
                trend = " They are closing." if car.gap_trend_s_per_lap < -0.08 else " You are pulling away." if car.gap_trend_s_per_lap > 0.08 else " The gap is stable."
        return f"{car.name} is {car.gap_s:.1f} seconds {role}.{trend}".strip()

    def focus_response(self, decision: LiveRaceDecision | None = None) -> str:
        d = decision or self._latest
        return f"Focus this lap: {d.coaching.summary} {d.energy.summary}".strip()

    def summary_response(self, decision: LiveRaceDecision | None = None) -> str:
        d = decision or self._latest
        position = f"P{d.position}" if d.position else "position unavailable"
        return (
            f"{position}, {d.battle_state.value.replace('_', ' ')}. "
            f"{self.box_response(d)} {d.energy.summary} Focus: {d.coaching.summary}"
        )

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------

    def _record_sample(self, snapshot: Any) -> None:
        session_time = self._float(snapshot, "session_time")
        if self._samples and session_time <= self._samples[-1]["session_time"] + 0.20:
            return
        lap = self._int(snapshot, "lap_number")
        max_wear = max(self._numbers(getattr(snapshot, "tyre_wear_pct", [])) or [0.0])
        sample = {
            "session_time": session_time,
            "lap": float(lap),
            "gap_ahead": max(0.0, self._float(snapshot, "delta_to_car_ahead_s")),
            "gap_behind": self._gap_behind(snapshot) or 0.0,
            "ers": self._float(snapshot, "ers_percent"),
            "wear": max_wear,
        }
        self._samples.append(sample)
        if lap > 0 and (lap != self._last_lap_number or lap not in self._wear_by_lap):
            self._wear_by_lap[lap] = max_wear
            self._last_lap_number = lap
            while len(self._wear_by_lap) > 20:
                oldest = min(self._wear_by_lap)
                del self._wear_by_lap[oldest]

    def _nearby(self, snapshot: Any, *, role: str) -> NearbyCarAssessment | None:
        car = getattr(snapshot, "car_ahead" if role == "ahead" else "car_behind", None)
        if not car:
            return None
        name = str(car.get("name") or f"car {role}")
        gap = self._float(snapshot, "delta_to_car_ahead_s") if role == "ahead" else self._gap_behind(snapshot)
        gap = gap if gap and gap > 0 else None
        trend = self._gap_trend(role)
        player_last = self._int(snapshot, "last_lap_time_ms")
        rival_last = int(car.get("last_lap_time_ms") or 0)
        relative = None
        if player_last > 0 and rival_last > 0:
            relative = (player_last - rival_last) / 1000.0
        assessment = "stable"
        if gap is not None:
            if role == "ahead":
                if gap <= self._setting("strategy_attack_gap_s", 1.6):
                    assessment = "attack opportunity"
                elif trend is not None and trend < -0.12:
                    assessment = "closing"
                elif trend is not None and trend > 0.12:
                    assessment = "pulling away"
            else:
                if gap <= self._setting("strategy_defend_gap_s", 1.2):
                    assessment = "immediate threat"
                elif trend is not None and trend < -0.12:
                    assessment = "closing threat"
                elif trend is not None and trend > 0.12:
                    assessment = "falling back"
        return NearbyCarAssessment(
            role=role,
            name=name,
            position=int(car.get("position") or 0) or None,
            gap_s=round(gap, 3) if gap is not None else None,
            gap_trend_s_per_lap=round(trend, 3) if trend is not None else None,
            relative_last_lap_s=round(relative, 3) if relative is not None else None,
            in_drs_range=bool(gap is not None and gap <= 1.0),
            pit_status=int(car.get("pit_status") or 0),
            pit_stops=int(car.get("pit_stops") or 0),
            assessment=assessment,
        )

    def _gap_trend(self, role: str) -> float | None:
        if len(self._samples) < 4:
            return None
        key = "gap_ahead" if role == "ahead" else "gap_behind"
        recent = [sample for sample in self._samples if sample[key] > 0][-30:]
        if len(recent) < 4:
            return None
        first = recent[0]
        last = recent[-1]
        elapsed = last["session_time"] - first["session_time"]
        if elapsed < 3.0:
            return None
        lap_span = last["lap"] - first["lap"]
        if lap_span >= 0.5:
            denominator = lap_span
        else:
            denominator = elapsed / self._setting("strategy_default_lap_time_s", 90.0)
        if denominator <= 0:
            return None
        return (last[key] - first[key]) / denominator

    def _project_tyres(self, snapshot: Any) -> TyreProjection:
        wear = self._numbers(getattr(snapshot, "tyre_wear_pct", []))
        temps = self._numbers(getattr(snapshot, "tyre_surface_temps_c", []))
        max_wear = max(wear or [0.0])
        average_wear = mean(wear) if wear else 0.0
        hottest = max(temps or [0.0])
        age = max(0, self._int(snapshot, "tyre_age_laps"))
        laps_remaining = self._laps_remaining(snapshot)

        deltas: list[float] = []
        laps = sorted(self._wear_by_lap)
        for first_lap, second_lap in zip(laps, laps[1:]):
            lap_delta = second_lap - first_lap
            wear_delta = self._wear_by_lap[second_lap] - self._wear_by_lap[first_lap]
            if lap_delta > 0 and wear_delta >= 0:
                deltas.append(wear_delta / lap_delta)
        if deltas:
            wear_per_lap = mean(deltas[-5:])
            confidence = min(0.95, 0.55 + 0.08 * len(deltas[-5:]))
        elif age > 0 and max_wear > 0:
            wear_per_lap = max_wear / max(1, age)
            confidence = 0.45
        else:
            wear_per_lap = 0.0
            confidence = 0.15
        wear_per_lap = max(0.0, min(8.0, wear_per_lap))

        projected = None
        can_finish = None
        if laps_remaining is not None and max_wear > 0:
            projected = min(100.0, max_wear + wear_per_lap * laps_remaining)
            can_finish = projected < self._setting("strategy_max_finish_wear_pct", 90.0)

        status = "healthy"
        if max_wear >= self._setting("strategy_critical_wear_pct", 82.0) or hottest >= self._setting("strategy_critical_tyre_c", 115.0):
            status = "critical"
        elif max_wear >= self._setting("strategy_box_wear_pct", 68.0) or hottest >= self._setting("strategy_hot_tyre_c", 108.0):
            status = "high degradation"
        elif projected is not None and projected >= self._setting("strategy_marginal_finish_wear_pct", 78.0):
            status = "marginal to finish"
        elif max_wear >= 45.0:
            status = "worn"

        return TyreProjection(
            compound=str(getattr(snapshot, "tyre_compound", "UNKNOWN") or "UNKNOWN"),
            age_laps=age,
            max_wear_pct=round(max_wear, 1),
            average_wear_pct=round(average_wear, 1),
            hottest_temp_c=round(hottest, 1),
            wear_per_lap_pct=round(wear_per_lap, 2),
            laps_remaining=laps_remaining,
            projected_finish_wear_pct=round(projected, 1) if projected is not None else None,
            can_finish=can_finish,
            status=status,
            confidence=round(confidence, 2),
        )

    def _box_decision(
        self,
        snapshot: Any,
        tyres: TyreProjection,
        ahead: NearbyCarAssessment | None,
        behind: NearbyCarAssessment | None,
    ) -> BoxDecision:
        if self._int(snapshot, "pit_status") > 0:
            return BoxDecision(
                action=BoxAction.ALREADY_BOXING,
                confidence=0.98,
                summary="Continue the current box sequence.",
                reason_codes=["already_boxing"],
            )

        pit_loss = self._setting("strategy_default_pit_loss_s", 22.0)
        rejoin, lost, traffic = self._estimate_rejoin(snapshot, pit_loss)
        wing = max(self._numbers((getattr(snapshot, "wing_damage_pct", {}) or {}).values()) or [0.0])
        tyre_damage = max(self._numbers(getattr(snapshot, "tyre_damage_pct", [])) or [0.0])
        laps_remaining = tyres.laps_remaining
        pace_loss = self._pace_loss(snapshot)

        critical = (
            wing >= 55.0
            or tyre_damage >= 55.0
            or tyres.max_wear_pct >= self._setting("strategy_critical_wear_pct", 82.0)
            or tyres.hottest_temp_c >= self._setting("strategy_critical_tyre_c", 115.0)
        )
        if critical:
            reasons = ["critical_car_condition"]
            if wing >= 55.0:
                reasons.append("severe_wing_damage")
            if tyre_damage >= 55.0:
                reasons.append("severe_tyre_damage")
            if tyres.max_wear_pct >= self._setting("strategy_critical_wear_pct", 82.0):
                reasons.append("critical_tyre_wear")
            return BoxDecision(
                action=BoxAction.BOX_NOW,
                confidence=0.96,
                summary="Car or tyre condition has reached the intervention threshold.",
                reason_codes=reasons,
                expected_rejoin_position=rejoin,
                estimated_positions_lost=lost,
                traffic_cars=traffic,
                estimated_pit_loss_s=pit_loss,
            )

        if laps_remaining is not None and laps_remaining <= 2 and tyres.can_finish is not False:
            return BoxDecision(
                action=BoxAction.STAY_OUT,
                confidence=0.90,
                summary="Too little race distance remains for a normal stop to repay the time loss.",
                reason_codes=["late_race_track_position"],
                expected_rejoin_position=rejoin,
                estimated_positions_lost=lost,
                traffic_cars=traffic,
                estimated_pit_loss_s=pit_loss,
            )

        undercut = bool(
            ahead
            and ahead.gap_s is not None
            and ahead.gap_s <= 2.5
            and (ahead.relative_last_lap_s is None or ahead.relative_last_lap_s >= -0.15)
            and len(traffic) <= 2
            and (laps_remaining is None or laps_remaining >= 4)
        )
        overcut = bool(
            ahead
            and ahead.pit_status > 0
            and tyres.status in {"healthy", "worn"}
            and pace_loss < 0.8
        )

        finish_risk = tyres.can_finish is False
        degraded = tyres.max_wear_pct >= self._setting("strategy_box_wear_pct", 68.0) or pace_loss >= 1.2
        unsafe_traffic = len(traffic) >= 3

        if finish_risk and not unsafe_traffic:
            return BoxDecision(
                action=BoxAction.BOX_NOW,
                confidence=0.86,
                summary="The current tyre projection does not safely reach the finish and the rejoin is acceptable.",
                reason_codes=["cannot_finish_tyres", "acceptable_rejoin"],
                expected_rejoin_position=rejoin,
                estimated_positions_lost=lost,
                traffic_cars=traffic,
                estimated_pit_loss_s=pit_loss,
                undercut_opportunity=undercut,
            )

        if undercut and (degraded or tyres.max_wear_pct >= 50.0):
            return BoxDecision(
                action=BoxAction.BOX_NOW,
                confidence=0.78,
                summary="The undercut window is open and fresh tyres should repay the stop better than staying out.",
                reason_codes=["undercut_opportunity", "pace_or_wear_loss"],
                expected_rejoin_position=rejoin,
                estimated_positions_lost=lost,
                traffic_cars=traffic,
                estimated_pit_loss_s=pit_loss,
                undercut_opportunity=True,
            )

        if overcut:
            return BoxDecision(
                action=BoxAction.STAY_OUT,
                confidence=0.76,
                summary="The car ahead is boxing and your tyres remain stable. Push in clean air for the overcut.",
                reason_codes=["overcut_opportunity"],
                expected_rejoin_position=rejoin,
                estimated_positions_lost=lost,
                traffic_cars=traffic,
                estimated_pit_loss_s=pit_loss,
                overcut_opportunity=True,
            )

        if finish_risk and unsafe_traffic:
            return BoxDecision(
                action=BoxAction.CONDITIONAL,
                confidence=0.68,
                summary="Tyres are marginal, but boxing now rejoins into traffic. Manage one lap and reassess unless wear rises sharply.",
                reason_codes=["cannot_finish_tyres", "unsafe_rejoin_traffic"],
                expected_rejoin_position=rejoin,
                estimated_positions_lost=lost,
                traffic_cars=traffic,
                estimated_pit_loss_s=pit_loss,
            )

        if degraded and (behind is None or behind.gap_s is None or behind.gap_s > 1.5):
            return BoxDecision(
                action=BoxAction.CONDITIONAL,
                confidence=0.66,
                summary="The box window is opening, but the stop depends on traffic and remaining race distance.",
                reason_codes=["high_degradation", "box_window_opening"],
                expected_rejoin_position=rejoin,
                estimated_positions_lost=lost,
                traffic_cars=traffic,
                estimated_pit_loss_s=pit_loss,
                undercut_opportunity=undercut,
            )

        battle_reason = " Track position is valuable in the current battle." if behind and behind.gap_s and behind.gap_s <= 1.5 else ""
        return BoxDecision(
            action=BoxAction.STAY_OUT,
            confidence=0.72,
            summary=f"Tyre condition and pace do not justify the estimated stop loss yet.{battle_reason}".strip(),
            reason_codes=["tyres_stable", "protect_track_position" if battle_reason else "stop_not_repaid"],
            expected_rejoin_position=rejoin,
            estimated_positions_lost=lost,
            traffic_cars=traffic,
            estimated_pit_loss_s=pit_loss,
        )

    def _estimate_rejoin(self, snapshot: Any, pit_loss: float) -> tuple[int | None, int | None, list[str]]:
        position = self._positive_int(snapshot, "position")
        if position is None:
            return None, None, []
        classification = list(getattr(snapshot, "classification", []) or [])
        player_delta = max(0.0, self._float(snapshot, "delta_to_leader_s"))
        projected_delta = player_delta + pit_loss
        passed_by: list[dict[str, Any]] = []
        for row in classification:
            row_position = int(row.get("position") or 0)
            row_delta = float(row.get("delta_to_leader_s") or 0.0)
            if row_position <= position or row_delta <= player_delta:
                continue
            if row_delta <= projected_delta:
                passed_by.append(row)
        expected = position + len(passed_by)
        grid_size = self._int(snapshot, "grid_size") or len(classification)
        if grid_size > 0:
            expected = min(expected, grid_size)
        traffic: list[str] = []
        for row in classification:
            row_delta = float(row.get("delta_to_leader_s") or 0.0)
            if abs(row_delta - projected_delta) <= 3.0:
                name = str(row.get("name") or "").strip()
                if name and name.upper() != "YOU":
                    traffic.append(name)
        return expected, len(passed_by), traffic[:5]

    def _battle_state(
        self,
        snapshot: Any,
        tyres: TyreProjection,
        box: BoxDecision,
        ahead: NearbyCarAssessment | None,
        behind: NearbyCarAssessment | None,
    ) -> BattleState:
        if box.action == BoxAction.BOX_NOW and box.confidence >= 0.9:
            return BattleState.CRITICAL
        if behind and behind.gap_s is not None and behind.gap_s <= self._setting("strategy_defend_gap_s", 1.2):
            return BattleState.DEFENDING
        if ahead and ahead.gap_s is not None and ahead.gap_s <= self._setting("strategy_attack_gap_s", 1.6):
            return BattleState.ATTACKING
        if box.action == BoxAction.CONDITIONAL:
            return BattleState.PIT_WINDOW
        fuel_margin = self._fuel_margin(snapshot)
        if tyres.status in {"high degradation", "marginal to finish"} or self._float(snapshot, "ers_percent") < 25.0 or (fuel_margin is not None and fuel_margin < 0):
            return BattleState.MANAGING
        if ahead and ahead.gap_trend_s_per_lap is not None and ahead.gap_trend_s_per_lap < -0.15:
            return BattleState.ATTACKING
        if behind and behind.gap_trend_s_per_lap is not None and behind.gap_trend_s_per_lap < -0.15:
            return BattleState.DEFENDING
        return BattleState.CLEAR_AIR

    def _energy_plan(
        self,
        snapshot: Any,
        battle: BattleState,
        tyres: TyreProjection,
        ahead: NearbyCarAssessment | None,
        behind: NearbyCarAssessment | None,
    ) -> EnergyPlan:
        battery = max(0.0, min(100.0, self._float(snapshot, "ers_percent")))
        laps_remaining = self._laps_remaining(snapshot)
        zone = self._deployment_zone(snapshot)
        attack_reserve = self._setting("strategy_ers_attack_reserve_pct", 28.0)
        defence_reserve = self._setting("strategy_ers_defend_reserve_pct", 22.0)
        harvest_target = self._setting("strategy_ers_harvest_target_pct", 55.0)

        if battery <= 8.0:
            return EnergyPlan(
                EnergyAction.CRITICAL,
                battery,
                harvest_target,
                10.0,
                zone,
                f"Battery critical at {battery:.0f}%. Harvest through the next braking zones and avoid deployment.",
                0.96,
            )
        if laps_remaining is not None and laps_remaining <= 3 and battery >= 25.0:
            reserve = 10.0 if laps_remaining <= 2 else 15.0
            return EnergyPlan(
                EnergyAction.DEPLOY,
                battery,
                reserve,
                reserve,
                zone,
                f"Use battery on {zone}. Keep roughly {reserve:.0f}% for the final defence.",
                0.88,
            )
        if battle == BattleState.ATTACKING:
            if battery >= 55.0:
                return EnergyPlan(
                    EnergyAction.DEPLOY,
                    battery,
                    max(attack_reserve, battery - 28.0),
                    attack_reserve,
                    zone,
                    f"Deploy on {zone}. Stop below {attack_reserve:.0f}% and prioritize corner exit.",
                    0.90,
                )
            if battery >= 30.0:
                return EnergyPlan(
                    EnergyAction.SAVE_THEN_DEPLOY,
                    battery,
                    attack_reserve,
                    attack_reserve,
                    zone,
                    f"Save through the technical section, then deploy on {zone}. Keep {attack_reserve:.0f}% reserve.",
                    0.84,
                )
            return EnergyPlan(
                EnergyAction.HARVEST,
                battery,
                harvest_target,
                20.0,
                zone,
                f"Do not force the attack. Harvest to {harvest_target:.0f}% before a full deployment.",
                0.90,
            )
        if battle == BattleState.DEFENDING:
            if battery >= 35.0:
                return EnergyPlan(
                    EnergyAction.DEFEND,
                    battery,
                    defence_reserve,
                    defence_reserve,
                    zone,
                    f"Deploy from the exit onto {zone}. Stop below {defence_reserve:.0f}% and prioritize traction.",
                    0.90,
                )
            return EnergyPlan(
                EnergyAction.HARVEST,
                battery,
                45.0,
                15.0,
                zone,
                "Battery is low for repeated defence. Use one short deployment only, then harvest.",
                0.84,
            )
        if battery < 42.0:
            return EnergyPlan(
                EnergyAction.HARVEST,
                battery,
                harvest_target,
                20.0,
                zone,
                f"Harvest this lap and target {harvest_target:.0f}% before the next battle.",
                0.86,
            )
        if battery > 78.0 and tyres.status not in {"critical", "high degradation"}:
            return EnergyPlan(
                EnergyAction.BALANCED,
                battery,
                60.0,
                35.0,
                zone,
                f"Use a short deployment on {zone}; retain at least 35% for a battle.",
                0.76,
            )
        return EnergyPlan(
            EnergyAction.BALANCED,
            battery,
            55.0,
            30.0,
            zone,
            "Battery is on target. Keep deployment selective and preserve energy for the next battle.",
            0.74,
        )

    def _deployment_zone(self, snapshot: Any) -> str:
        history = list(getattr(snapshot, "history", []) or [])[-500:]
        track_length = self._float(snapshot, "track_length_m")
        if track_length <= 0 or len(history) < 30:
            return "the next long straight"
        bins: dict[int, list[float]] = {}
        for point in history:
            throttle = float(point.get("throttle") or 0.0)
            brake = float(point.get("brake") or 0.0)
            steer = abs(float(point.get("steer") or 0.0))
            speed = float(point.get("speed_kph") or 0.0)
            distance = float(point.get("lap_distance_m") or 0.0)
            if throttle < 0.88 or brake > 0.05 or steer > 0.18 or speed < 170 or distance < 0:
                continue
            index = int(max(0.0, min(0.999, distance / track_length)) * 20)
            bins.setdefault(index, []).append(speed)
        candidates = [(mean(values), len(values), index) for index, values in bins.items() if len(values) >= 3]
        if not candidates:
            return "the next long straight"
        _, _, best = max(candidates)
        percent = int((best + 0.5) / 20 * 100)
        return f"the long straight around {percent}% of the lap"

    def _coaching_plan(self, snapshot: Any, battle: BattleState, tyres: TyreProjection) -> CoachingPlan:
        history = list(getattr(snapshot, "history", []) or [])[-240:]
        if len(history) < 20:
            return CoachingPlan("collect_data", "Build a clean reference lap while I collect more data.", confidence=0.25)
        throttle = [float(point.get("throttle") or 0.0) for point in history]
        brake = [float(point.get("brake") or 0.0) for point in history]
        steer = [abs(float(point.get("steer") or 0.0)) for point in history]
        overlap = mean(1.0 if t > 0.15 and b > 0.15 else 0.0 for t, b in zip(throttle, brake))
        throttle_changes = mean(abs(b - a) for a, b in zip(throttle, throttle[1:])) if len(throttle) > 1 else 0.0
        loaded_throttle = mean(1.0 if s > 0.5 and t > 0.75 else 0.0 for s, t in zip(steer, throttle))

        if tyres.hottest_temp_c >= self._setting("strategy_hot_tyre_c", 108.0):
            return CoachingPlan("tyre_management", "Reduce sliding and open the steering before full throttle.", "warning", 0.90)
        if overlap >= 0.05:
            return CoachingPlan("brake_release", "Finish releasing the brake before committing to throttle.", "warning", 0.86)
        if loaded_throttle >= 0.08:
            return CoachingPlan("corner_exit", "Prioritize exit: open the steering before using full throttle.", "warning", 0.84)
        if throttle_changes >= 0.12:
            return CoachingPlan("throttle_smoothness", "Use one progressive throttle squeeze instead of repeated corrections.", "info", 0.80)
        if battle == BattleState.ATTACKING:
            return CoachingPlan("attack_exit", "Stay close through the technical section and maximize the final-corner exit.", "info", 0.78)
        if battle == BattleState.DEFENDING:
            return CoachingPlan("defence_exit", "Protect traction and make one decisive defensive placement before braking.", "warning", 0.82)
        return CoachingPlan("consistency", "Keep braking references consistent and protect corner-exit speed.", "info", 0.66)

    def _build_automatic_call(
        self,
        previous: LiveRaceDecision,
        current: LiveRaceDecision,
    ) -> StrategyAutomaticCall | None:
        if not current.connected or current.data_quality < 0.30:
            return None
        call: StrategyAutomaticCall | None = None
        if (
            bool(self._setting("strategy_auto_box_calls", True))
            and current.box.action != previous.box.action
            and current.box.action in {BoxAction.BOX_NOW, BoxAction.CONDITIONAL}
        ):
            priority = 98 if current.box.action == BoxAction.BOX_NOW else 82
            call = StrategyAutomaticCall(self.box_response(current), priority, "strategy", f"box:{current.box.action.value}")
        elif (
            bool(self._setting("strategy_auto_battle_calls", True))
            and current.battle_state != previous.battle_state
            and current.battle_state in {BattleState.ATTACKING, BattleState.DEFENDING}
        ):
            text = self.attack_response(current) if current.battle_state == BattleState.ATTACKING else self.defend_response(current)
            call = StrategyAutomaticCall(text, 82, "battle", f"battle:{current.battle_state.value}")
        elif (
            bool(self._setting("strategy_auto_ers_calls", True))
            and current.energy.action != previous.energy.action
            and current.energy.action in {EnergyAction.DEPLOY, EnergyAction.DEFEND, EnergyAction.HARVEST, EnergyAction.CRITICAL}
        ):
            priority = 94 if current.energy.action == EnergyAction.CRITICAL else 76
            call = StrategyAutomaticCall(current.energy.summary, priority, "ers", f"ers:{current.energy.action.value}")
        elif (
            bool(self._setting("strategy_auto_coaching_calls", True))
            and current.coaching.focus != previous.coaching.focus
            and current.coaching.severity == "warning"
        ):
            call = StrategyAutomaticCall(current.coaching.summary, 70, "coaching", f"coach:{current.coaching.focus}")

        if call and call.key == self._last_call_signature:
            return None
        if call:
            self._last_call_signature = call.key
        return call

    def _pace_loss(self, snapshot: Any) -> float:
        last = self._int(snapshot, "last_lap_time_ms")
        best = self._int(snapshot, "best_lap_time_ms")
        if last > 0 and best > 0 and last >= best:
            return (last - best) / 1000.0
        laps = []
        for row in list(getattr(snapshot, "completed_laps", []) or [])[:6]:
            value = int(row.get("lap_time_ms") or 0)
            valid = bool(row.get("valid", True))
            if value > 0 and valid:
                laps.append(value)
        if len(laps) >= 3:
            reference = min(laps)
            return max(0.0, (laps[0] - reference) / 1000.0)
        return 0.0

    def _fuel_margin(self, snapshot: Any) -> float | None:
        remaining = self._laps_remaining(snapshot)
        estimate = self._float(snapshot, "fuel_remaining_laps")
        if remaining is None or estimate <= 0:
            return None
        return estimate - remaining

    def _laps_remaining(self, snapshot: Any) -> int | None:
        lap = self._int(snapshot, "lap_number")
        total = self._int(snapshot, "total_laps")
        if lap <= 0 or total <= 0:
            return None
        return max(0, total - lap + 1)

    def _data_quality(
        self,
        snapshot: Any,
        ahead: NearbyCarAssessment | None,
        behind: NearbyCarAssessment | None,
    ) -> float:
        checks = [
            self._positive_int(snapshot, "position") is not None,
            self._int(snapshot, "lap_number") > 0,
            self._int(snapshot, "total_laps") > 0,
            self._float(snapshot, "ers_percent") > 0,
            any(self._numbers(getattr(snapshot, "tyre_wear_pct", []))),
            ahead is not None,
            behind is not None,
            bool(getattr(snapshot, "classification", [])),
            len(getattr(snapshot, "history", []) or []) >= 20,
        ]
        return round(sum(1 for item in checks if item) / len(checks), 2)

    def _gap_behind(self, snapshot: Any) -> float | None:
        car = getattr(snapshot, "car_behind", None)
        if not car:
            return None
        gap = abs(float(car.get("delta_to_car_ahead_s") or 0.0))
        return gap if gap > 0 else None

    def _setting(self, name: str, default: Any) -> Any:
        return getattr(self.settings, name, default)

    @staticmethod
    def _numbers(values: Any) -> list[float]:
        result: list[float] = []
        try:
            for value in values:
                number = float(value or 0.0)
                result.append(number)
        except (TypeError, ValueError):
            return []
        return result

    @staticmethod
    def _float(obj: Any, name: str) -> float:
        try:
            return float(getattr(obj, name, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _int(obj: Any, name: str) -> int:
        try:
            return int(getattr(obj, name, 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _positive_int(self, obj: Any, name: str) -> int | None:
        value = self._int(obj, name)
        return value if value > 0 else None
