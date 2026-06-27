"use client";

import { useEffect, useState } from "react";

import styles from "./StrategicEngineerCard.module.css";
import { LiveRaceDecision } from "../types/telemetry";

const API =
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://localhost:8000";

const emptyDecision: LiveRaceDecision = {
  generated_at: 0,
  connected: false,
  battle_state: "unknown",
  position: null,
  lap_number: null,
  total_laps: null,
  laps_remaining: null,
  car_ahead: null,
  car_behind: null,
  tyres: {
    compound: "UNKNOWN",
    age_laps: 0,
    max_wear_pct: 0,
    average_wear_pct: 0,
    hottest_temp_c: 0,
    wear_per_lap_pct: 0,
    laps_remaining: null,
    projected_finish_wear_pct: null,
    can_finish: null,
    status: "unavailable",
    confidence: 0,
  },
  box: {
    action: "unknown",
    confidence: 0,
    summary: "Waiting for telemetry.",
    reason_codes: [],
    expected_rejoin_position: null,
    estimated_positions_lost: null,
    traffic_cars: [],
    estimated_pit_loss_s: null,
    undercut_opportunity: false,
    overcut_opportunity: false,
  },
  energy: {
    action: "unknown",
    battery_percent: 0,
    target_percent: 0,
    minimum_reserve_percent: 0,
    deployment_zone: "next long straight",
    summary: "Waiting for ERS telemetry.",
    confidence: 0,
  },
  coaching: {
    focus: "collect_data",
    summary: "Collecting driving data.",
    severity: "info",
    confidence: 0,
  },
  data_quality: 0,
  reason_codes: [],
};

function label(value: string): string {
  return value.replaceAll("_", " ").toUpperCase();
}

function gap(value: number | null): string {
  return value === null ? "--" : `${value.toFixed(1)}s`;
}

function trend(
  value: number | null,
  role: "ahead" | "behind",
): string {
  if (value === null || Math.abs(value) < 0.08) {
    return "stable";
  }
  if (role === "ahead") {
    return value < 0 ? "closing" : "opening";
  }
  return value < 0 ? "closing threat" : "pulling away";
}

function raceContext(decision: LiveRaceDecision): string {
  const position = decision.position ? `P${decision.position}` : "P--";
  const lap = decision.lap_number ?? "--";
  const total = decision.total_laps ?? "--";
  return `${position} · L${lap}/${total}`;
}

export function StrategicEngineerCard() {
  const [decision, setDecision] =
    useState<LiveRaceDecision>(emptyDecision);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function refresh() {
      try {
        const response = await fetch(
          `${API}/api/strategy/live`,
          { cache: "no-store" },
        );
        if (!response.ok) {
          throw new Error("Strategic engineer unavailable");
        }
        const payload =
          (await response.json()) as LiveRaceDecision;
        if (active) {
          setDecision(payload);
          setError(null);
        }
      } catch (reason) {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Strategic engineer unavailable",
          );
        }
      }
    }

    refresh();
    const interval = setInterval(refresh, 750);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <div>
          <span>Live decision engine</span>
          <h4>Strategic race engineer</h4>
          <small>{raceContext(decision)}</small>
        </div>
        <div
          className={`${styles.battle} ${
            styles[decision.battle_state] || ""
          }`}
        >
          {label(decision.battle_state)}
        </div>
      </div>

      {error ? (
        <p className={styles.error}>{error}</p>
      ) : null}

      <div className={styles.primaryGrid}>
        <article>
          <span>Box call</span>
          <strong>{label(decision.box.action)}</strong>
          <p title={decision.box.summary}>{decision.box.summary}</p>
        </article>
        <article>
          <span>ERS plan</span>
          <strong>{label(decision.energy.action)}</strong>
          <p title={decision.energy.summary}>{decision.energy.summary}</p>
        </article>
        <article>
          <span>Coaching</span>
          <strong>{label(decision.coaching.focus)}</strong>
          <p title={decision.coaching.summary}>{decision.coaching.summary}</p>
        </article>
      </div>

      <div className={styles.metrics}>
        <div>
          <span>Battery</span>
          <strong>{decision.energy.battery_percent.toFixed(0)}%</strong>
          <small>
            target {decision.energy.target_percent.toFixed(0)}% · reserve {decision.energy.minimum_reserve_percent.toFixed(0)}%
          </small>
        </div>
        <div>
          <span>Tyres</span>
          <strong>{decision.tyres.max_wear_pct.toFixed(0)}%</strong>
          <small>{decision.tyres.compound}</small>
        </div>
        <div>
          <span>Rejoin</span>
          <strong>
            {decision.box.expected_rejoin_position
              ? `P${decision.box.expected_rejoin_position}`
              : "--"}
          </strong>
          <small>
            {decision.box.traffic_cars.length > 0
              ? decision.box.traffic_cars.slice(0, 2).join(", ")
              : "no traffic estimate"}
          </small>
        </div>
        <div>
          <span>Confidence</span>
          <strong>{(decision.box.confidence * 100).toFixed(0)}%</strong>
          <small>data {(decision.data_quality * 100).toFixed(0)}%</small>
        </div>
      </div>

      <div className={styles.battles}>
        <div>
          <span>Ahead</span>
          <strong>{decision.car_ahead?.name || "No car data"}</strong>
          <small>
            {gap(decision.car_ahead?.gap_s ?? null)} · {trend(
              decision.car_ahead?.gap_trend_s_per_lap ?? null,
              "ahead",
            )}
          </small>
        </div>
        <div>
          <span>Behind</span>
          <strong>{decision.car_behind?.name || "No car data"}</strong>
          <small>
            {gap(decision.car_behind?.gap_s ?? null)} · {trend(
              decision.car_behind?.gap_trend_s_per_lap ?? null,
              "behind",
            )}
          </small>
        </div>
      </div>
    </section>
  );
}