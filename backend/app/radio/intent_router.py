from __future__ import annotations

import re
from statistics import mean
from typing import Any

from app.radio.models import IntentResult, RadioMode
from app.strategy.engine import LiveStrategicEngineer
from app.telemetry.models import LiveTelemetrySnapshot


TYRE_LABELS = ["rear-left", "rear-right", "front-left", "front-right"]


class LiveIntentRouter:
    """Fast deterministic live-race answers backed by the strategic engine."""

    def __init__(self, strategy: LiveStrategicEngineer | None = None) -> None:
        self.strategy = strategy

    def route(self, text: str, snapshot: LiveTelemetrySnapshot) -> IntentResult:
        clean = " ".join(text.casefold().strip().split())
        if not clean:
            return IntentResult(False)

        # Radio control.
        if self._matches(clean, r"\b(repeat|say that again|what did you say)\b"):
            return IntentResult(True, topic="radio", action="repeat")
        if self._matches(clean, r"\b(stop talking|be quiet|radio quiet|quiet mode|silence)\b"):
            return IntentResult(True, "Understood. Non-critical radio is quiet for now.", "radio", action="quiet")
        if self._matches(clean, r"\b(resume|talk again|radio on|resume updates)\b"):
            return IntentResult(True, "Radio updates resumed.", "radio", action="resume")
        if self._matches(clean, r"\b(minimal mode|critical only|critical messages only)\b"):
            return IntentResult(True, "Minimal mode enabled. I will only call important events.", "radio", action="mode", mode=RadioMode.MINIMAL)
        if self._matches(clean, r"\b(race mode|balanced mode)\b"):
            return IntentResult(True, "Race mode enabled.", "radio", action="mode", mode=RadioMode.RACE)
        if self._matches(clean, r"\b(coaching mode|coach mode|more coaching)\b"):
            return IntentResult(True, "Coaching mode enabled. I will add driving guidance.", "radio", action="mode", mode=RadioMode.COACHING)
        if self._matches(clean, r"\b(radio check|can you hear me|are you there)\b"):
            return IntentResult(True, "Loud and clear. Race engineer online.", "radio")

        decision = None
        if self.strategy:
            decision = self.strategy.evaluate(snapshot)
            # A direct driver question already receives the latest recommendation;
            # suppress the same recommendation from being repeated as an auto call.
            self.strategy.pop_automatic_call()

        # Full strategy and box questions. "Pit" remains accepted as a hidden
        # fallback, but all spoken output uses the racing term "box".
        if self._matches(clean, r"\b(will i lose position|where.*rejoin|rejoin position|traffic.*box|box.*traffic)\b"):
            return IntentResult(True, self._strategy().rejoin_response(decision) if self.strategy else "I do not have enough classification data to estimate the rejoin position.", "strategy", priority=104)
        if self._matches(clean, r"\b(undercut|can i undercut|overcut|can i overcut)\b"):
            return self._undercut(decision) if self.strategy else IntentResult(True, "I need live strategy data before judging the undercut.", "strategy")
        if self._matches(clean, r"\b(should i box|should we box|do i need to box|box now|box this lap|box next lap|box window|when.*box|should i pit|pit now|pit window)\b"):
            return IntentResult(True, self._strategy().box_response(decision) if self.strategy else self._fallback_box(snapshot), "strategy", priority=108)

        # Battle and nearby cars.
        if self._matches(clean, r"\b(who is ahead|who's ahead|car ahead|gap ahead|ahead of me)\b"):
            if decision:
                return IntentResult(True, self._strategy().nearby_response("ahead", decision), "gap_ahead")
            return self._gap_ahead(snapshot)
        if self._matches(clean, r"\b(who is behind|who's behind|car behind|gap behind|behind me)\b"):
            if decision:
                return IntentResult(True, self._strategy().nearby_response("behind", decision), "gap_behind")
            return self._gap_behind(snapshot)
        if self._matches(clean, r"\b(am i gaining|am i catching|are they gaining|gap trend|closing rate)\b"):
            return self._gap_trend(decision)
        if self._matches(clean, r"\b(can i attack|should i attack|attack now|overtake|push now|can i push)\b"):
            return IntentResult(True, self._strategy().attack_response(decision) if self.strategy else self._fallback_attack(snapshot), "racecraft", priority=104)
        if self._matches(clean, r"\b(defend|defence|defense|protect position|should i defend)\b"):
            return IntentResult(True, self._strategy().defend_response(decision) if self.strategy else self._fallback_defend(snapshot), "racecraft", priority=104)

        # ERS and battery planning.
        if self._matches(clean, r"\b(where.*deploy|which straight|deployment zone|best place.*deploy)\b"):
            return IntentResult(True, self._strategy().energy_response(decision) if self.strategy else self._fallback_ers(snapshot), "ers", priority=103)
        if self._matches(clean, r"\b(how much.*battery|how much.*save|minimum reserve|battery target|how much.*keep)\b"):
            return self._battery_target(decision)
        if self._matches(clean, r"\b(when.*deploy|deploy now|use overtake|overtake mode|should i deploy|harvest|save battery)\b"):
            return IntentResult(True, self._strategy().energy_response(decision) if self.strategy else self._fallback_ers(snapshot), "ers", priority=103)
        if self._matches(clean, r"\b(ers|battery|energy)\b"):
            return IntentResult(True, self._strategy().energy_response(decision) if self.strategy else self._fallback_ers(snapshot), "ers")

        # Tyres, fuel, damage and position.
        if self._matches(clean, r"\b(position|what place|where am i running)\b"):
            return self._position(snapshot)
        if self._matches(clean, r"\b(tyres?|tires?|rubber)\b") and self._matches(clean, r"\b(last|reach.*end|make.*end|finish|remaining life|life left)\b"):
            if decision:
                return IntentResult(True, self._strategy().tyre_life_response(decision), "tyres", priority=102)
            return self._tyre_life(snapshot)
        if self._matches(clean, r"\b(tyres?|tires?|rubber)\b"):
            return self._tyres(snapshot)
        if self._matches(clean, r"\b(fuel|petrol|gas)\b"):
            return self._fuel(snapshot)
        if self._matches(clean, r"\b(damage|front wing|rear wing|car condition)\b"):
            return self._damage(snapshot)

        # Coaching and race status.
        if self._matches(clean, r"\b(what.*focus|focus this lap|what should i do|what next|race plan)\b"):
            return IntentResult(True, self._strategy().focus_response(decision) if self.strategy else self._time_loss(snapshot).text, "coaching", priority=101)
        if self._matches(clean, r"\b(where.*losing|why.*slow|time loss|what am i doing wrong|driving advice)\b"):
            if decision:
                return IntentResult(True, decision.coaching.summary, "coaching")
            return self._time_loss(snapshot)
        if self._matches(clean, r"\b(lap time|best lap|last lap|current lap)\b"):
            return self._lap_time(snapshot)
        if self._matches(clean, r"\b(status|give me an update|race update|full update|strategy update)\b"):
            if decision:
                return IntentResult(True, self._strategy().summary_response(decision), "summary", priority=102)
            return self._summary(snapshot)

        return IntentResult(False)

    def _strategy(self) -> LiveStrategicEngineer:
        if self.strategy is None:
            raise RuntimeError("Strategic engineer is not configured")
        return self.strategy

    @staticmethod
    def _matches(text: str, pattern: str) -> bool:
        return re.search(pattern, text, flags=re.IGNORECASE) is not None

    @staticmethod
    def _car_name(car: dict[str, Any] | None, fallback: str) -> str:
        if not car:
            return fallback
        name = str(car.get("name") or "").strip()
        return name if name and name != "UNKNOWN" else fallback

    def _position(self, s: LiveTelemetrySnapshot) -> IntentResult:
        if s.position <= 0:
            return IntentResult(True, "Position data is not available yet.", "position")
        total = f" of {s.grid_size}" if s.grid_size > 0 else ""
        change = ""
        if s.positions_gained > 0:
            change = f" You are up {s.positions_gained} position{'s' if s.positions_gained != 1 else ''}."
        elif s.positions_gained < 0:
            lost = abs(s.positions_gained)
            change = f" You are down {lost} position{'s' if lost != 1 else ''}."
        return IntentResult(True, f"You are P{s.position}{total}.{change}".strip(), "position")

    def _gap_ahead(self, s: LiveTelemetrySnapshot) -> IntentResult:
        name = self._car_name(s.car_ahead, "the car ahead")
        gap = float(s.delta_to_car_ahead_s or 0.0)
        if gap <= 0:
            return IntentResult(True, f"No reliable gap to {name} yet.", "gap_ahead")
        drs = " You are in DRS range." if gap <= 1.0 else ""
        return IntentResult(True, f"Gap to {name} is {gap:.1f} seconds.{drs}".strip(), "gap_ahead")

    def _gap_behind(self, s: LiveTelemetrySnapshot) -> IntentResult:
        name = self._car_name(s.car_behind, "the car behind")
        gap = abs(float((s.car_behind or {}).get("delta_to_car_ahead_s") or 0.0))
        if gap <= 0:
            return IntentResult(True, f"No reliable gap to {name} yet.", "gap_behind")
        warning = " They are in DRS range." if gap <= 1.0 else ""
        return IntentResult(True, f"{name.capitalize()} is {gap:.1f} seconds behind.{warning}".strip(), "gap_behind")

    def _gap_trend(self, decision: Any) -> IntentResult:
        if not decision:
            return IntentResult(True, "I need more live gap samples before calculating the trend.", "racecraft")
        ahead = decision.car_ahead
        behind = decision.car_behind
        parts: list[str] = []
        if ahead and ahead.gap_trend_s_per_lap is not None:
            if ahead.gap_trend_s_per_lap < -0.08:
                parts.append(f"You are gaining about {abs(ahead.gap_trend_s_per_lap):.1f} seconds per lap on {ahead.name}.")
            elif ahead.gap_trend_s_per_lap > 0.08:
                parts.append(f"{ahead.name} is pulling away by about {ahead.gap_trend_s_per_lap:.1f} seconds per lap.")
            else:
                parts.append(f"The gap to {ahead.name} is stable.")
        if behind and behind.gap_trend_s_per_lap is not None:
            if behind.gap_trend_s_per_lap < -0.08:
                parts.append(f"{behind.name} is gaining about {abs(behind.gap_trend_s_per_lap):.1f} seconds per lap.")
            elif behind.gap_trend_s_per_lap > 0.08:
                parts.append(f"You are pulling away from {behind.name}.")
        return IntentResult(True, " ".join(parts) or "I need more live gap samples before calculating the trend.", "racecraft")

    def _battery_target(self, decision: Any) -> IntentResult:
        if not decision:
            return IntentResult(True, "Battery target is not available yet.", "ers")
        plan = decision.energy
        return IntentResult(
            True,
            f"Current battery {plan.battery_percent:.0f}%. Target {plan.target_percent:.0f}%, minimum reserve {plan.minimum_reserve_percent:.0f}%. {plan.summary}",
            "ers",
            priority=103,
        )

    def _undercut(self, decision: Any) -> IntentResult:
        if not decision:
            return IntentResult(True, "I need classification and battle data before judging the undercut.", "strategy")
        box = decision.box
        if box.undercut_opportunity:
            return IntentResult(True, f"Yes. {box.summary} {self._strategy().rejoin_response(decision)}", "strategy", priority=105)
        if box.overcut_opportunity:
            return IntentResult(True, f"The overcut is stronger right now. {box.summary}", "strategy", priority=104)
        return IntentResult(True, f"No strong undercut signal yet. {box.summary}", "strategy")

    def _tyres(self, s: LiveTelemetrySnapshot) -> IntentResult:
        wear = [float(value or 0.0) for value in s.tyre_wear_pct]
        temps = [float(value or 0.0) for value in s.tyre_surface_temps_c]
        if not any(wear) and not any(temps):
            return IntentResult(True, "Tyre data is not available yet.", "tyres")
        max_wear = max(wear or [0.0])
        wear_index = wear.index(max_wear) if wear else 0
        max_temp = max(temps or [0.0])
        temp_index = temps.index(max_temp) if temps else 0
        condition = "healthy"
        if max_wear >= 75:
            condition = "critical"
        elif max_wear >= 55 or max_temp >= 110:
            condition = "worn or hot"
        elif max_wear >= 35 or max_temp >= 103:
            condition = "starting to degrade"
        return IntentResult(
            True,
            f"Tyres are {condition}. Highest wear is {max_wear:.0f}% on the {TYRE_LABELS[wear_index]}; hottest is {TYRE_LABELS[temp_index]} at {max_temp:.0f} degrees.",
            "tyres",
        )

    def _tyre_life(self, s: LiveTelemetrySnapshot) -> IntentResult:
        wear = max([float(value or 0.0) for value in s.tyre_wear_pct] or [0.0])
        age = max(0, int(s.tyre_age_laps or 0))
        laps_to_go = max(0, s.total_laps - s.lap_number + 1) if s.total_laps > 0 and s.lap_number > 0 else 0
        if wear <= 0 or laps_to_go <= 0:
            return IntentResult(True, "I do not have enough tyre and race-distance data to estimate remaining life.", "tyres")
        projected = wear + (wear / max(1, age) if age > 0 else 2.0) * laps_to_go
        guidance = "Yes, they should reach the end." if projected < 90 else "No, they are unlikely to reach the end safely."
        return IntentResult(True, f"{guidance} Projected finish wear is about {min(100, projected):.0f}%.", "tyres")

    def _fuel(self, s: LiveTelemetrySnapshot) -> IntentResult:
        estimate = float(s.fuel_remaining_laps or 0.0)
        if estimate <= 0:
            return IntentResult(True, "Fuel estimate is not available yet.", "fuel")
        laps_to_go = max(0, s.total_laps - s.lap_number + 1) if s.total_laps > 0 and s.lap_number > 0 else 0
        margin = estimate - laps_to_go if laps_to_go else None
        if margin is not None and margin < -0.25:
            guidance = f" You are short by roughly {abs(margin):.1f} laps; lift and coast."
        elif margin is not None and margin > 0.75:
            guidance = f" You have roughly {margin:.1f} laps in hand."
        else:
            guidance = " Fuel is close to target." if margin is not None else ""
        return IntentResult(True, f"Fuel estimate is {estimate:.1f} laps remaining.{guidance}".strip(), "fuel")

    def _damage(self, s: LiveTelemetrySnapshot) -> IntentResult:
        fl = int(s.wing_damage_pct.get("fl", 0))
        fr = int(s.wing_damage_pct.get("fr", 0))
        rear = int(s.wing_damage_pct.get("rear", 0))
        tyre_damage = max([int(value or 0) for value in s.tyre_damage_pct] or [0])
        worst = max(fl, fr, rear, tyre_damage)
        if worst <= 0:
            return IntentResult(True, "No recorded wing or tyre damage.", "damage")
        guidance = "Box this lap." if worst >= 50 else "The car is damaged but driveable." if worst >= 20 else "Damage is minor."
        return IntentResult(True, f"Front wing {fl}% left and {fr}% right, rear wing {rear}%, maximum tyre damage {tyre_damage}%. {guidance}", "damage", priority=108 if worst >= 50 else 100)

    def _fallback_ers(self, s: LiveTelemetrySnapshot) -> str:
        level = float(s.ers_percent or 0.0)
        if level >= 65:
            return f"Battery is {level:.0f}%. Use deployment selectively on the next long straight."
        if level >= 30:
            return f"Battery is {level:.0f}%. Keep at least 25% in reserve for the next battle."
        return f"Battery is {level:.0f}%. Harvest through the next braking zones."

    def _fallback_box(self, s: LiveTelemetrySnapshot) -> str:
        wear = max([float(value or 0.0) for value in s.tyre_wear_pct] or [0.0])
        damage = max([int(value or 0) for value in s.tyre_damage_pct] or [0])
        wing = max([int(value or 0) for value in s.wing_damage_pct.values()] or [0])
        if s.pit_status > 0:
            return "You are already committed to boxing."
        if wear >= 82 or damage >= 55 or wing >= 55:
            return "Box this lap. Car or tyre condition is critical."
        return "Stay out for now. I need the full strategy engine for a rejoin and battle-aware call."

    def _fallback_attack(self, s: LiveTelemetrySnapshot) -> str:
        gap = float(s.delta_to_car_ahead_s or 0.0)
        battery = float(s.ers_percent or 0.0)
        if 0 < gap <= 1.0 and battery >= 25:
            return f"Yes. Attack now. Gap is {gap:.1f} seconds and battery is {battery:.0f}%. Deploy on the next straight."
        return f"Build the attack. Gap is {gap:.1f} seconds and battery is {battery:.0f}%."

    def _fallback_defend(self, s: LiveTelemetrySnapshot) -> str:
        gap = abs(float((s.car_behind or {}).get("delta_to_car_ahead_s") or 0.0))
        if 0 < gap <= 1.0:
            return f"Defend this lap. Gap behind is {gap:.1f} seconds. Prioritize traction and deploy on exit."
        return f"No immediate defence required. Gap behind is {gap:.1f} seconds."

    def _time_loss(self, s: LiveTelemetrySnapshot) -> IntentResult:
        history = list(s.history[-240:])
        if len(history) < 20:
            return IntentResult(True, "I need more live telemetry before diagnosing the main time loss.", "coaching")
        throttle = [float(point.get("throttle", 0.0)) for point in history]
        brake = [float(point.get("brake", 0.0)) for point in history]
        steer = [abs(float(point.get("steer", 0.0))) for point in history]
        overlap = mean(1.0 if t > 0.15 and b > 0.15 else 0.0 for t, b in zip(throttle, brake))
        throttle_changes = mean(abs(b - a) for a, b in zip(throttle, throttle[1:])) if len(throttle) > 1 else 0.0
        loaded = mean(1.0 if st > 0.5 and th > 0.75 else 0.0 for st, th in zip(steer, throttle))
        if overlap >= 0.05:
            advice = "Finish releasing the brake before committing to power."
        elif throttle_changes >= 0.12:
            advice = "Use one progressive throttle squeeze instead of repeated corrections."
        elif loaded >= 0.08:
            advice = "Open the steering before using full throttle."
        else:
            advice = "Focus on repeatable braking and maximizing corner-exit speed."
        return IntentResult(True, advice, "coaching")

    def _lap_time(self, s: LiveTelemetrySnapshot) -> IntentResult:
        def fmt(ms: int | None) -> str:
            if not ms:
                return "unavailable"
            minutes = ms // 60_000
            seconds = (ms % 60_000) / 1000
            return f"{minutes}:{seconds:06.3f}"
        return IntentResult(True, f"Current lap {fmt(s.current_lap_time_ms)}, last lap {fmt(s.last_lap_time_ms)}, best lap {fmt(s.best_lap_time_ms)}.", "lap_time")

    def _summary(self, s: LiveTelemetrySnapshot) -> IntentResult:
        position = f"P{s.position}" if s.position > 0 else "position unavailable"
        ahead = f", gap ahead {s.delta_to_car_ahead_s:.1f}" if s.delta_to_car_ahead_s > 0 else ""
        return IntentResult(True, f"{position}{ahead}. Fuel {s.fuel_remaining_laps:.1f} laps, battery {s.ers_percent:.0f}%, maximum tyre wear {max(s.tyre_wear_pct or [0]):.0f}%.", "summary")
