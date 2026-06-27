"use client";

import { CSSProperties, useEffect, useMemo, useState } from "react";

import styles from "./BattleCommandCenter.module.css";
import {
  BattleIntelligence,
  ForecastPoint,
  RivalModel,
} from "../types/intelligence";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const EMPTY: BattleIntelligence = {
  generated_at: 0,
  connected: false,
  state: "observe",
  target: null,
  target_role: null,
  confidence: 0,
  decision_resolved: false,
  state_margin: 0,
  dominant_probability: 1,
  runner_up_probability: 0,
  window_laps: null,
  probabilities: {
    attack: 0,
    defend: 0,
    contested: 0,
    clear: 1,
  },
  ahead: null,
  behind: null,
  relative_pace: {
    ahead_s_per_lap: null,
    behind_s_per_lap: null,
    ahead_confidence: 0,
    behind_confidence: 0,
  },
  forecast: [],
  timeline: [],
  model: null,
};

function clamp(value: number, low = 0, high = 1): number {
  return Math.max(low, Math.min(high, value));
}

function percent(value: number): string {
  return `${Math.round(clamp(value) * 100)}%`;
}

function gap(value: number | null): string {
  return value === null ? "--" : `${value.toFixed(2)}s`;
}

function signedSeconds(value: number | null): string {
  if (value === null) return "--";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}s`;
}

function stateLabel(value: string): string {
  if (value === "attack") return "ATTACK";
  if (value === "defend") return "DEFEND";
  if (value === "contested") return "DOUBLE PRESSURE";
  if (value === "clear") return "CLEAR AIR";
  if (value === "analyzing") return "ANALYZING";
  if (value === "stale") return "TELEMETRY STALE";
  return "WAITING";
}

function stateSymbol(value: string): string {
  if (value === "attack") return "↗";
  if (value === "defend") return "↙";
  if (value === "contested") return "⇄";
  if (value === "clear") return "○";
  if (value === "analyzing") return "⋯";
  if (value === "stale") return "!";
  return "·";
}

function stateSummary(value: string, hasRival: boolean): string {
  if (value === "attack") return "Pressure building ahead";
  if (value === "defend") return "Pressure building behind";
  if (value === "contested") return "Battle active on both sides";
  if (value === "clear") return "No immediate battle pressure";
  if (value === "analyzing") return hasRival ? "Battle forming" : "Collecting rival data";
  if (value === "stale") return "Dashboard frozen to the last valid frame";
  return "Waiting for live telemetry";
}

function stateClass(value: string): string {
  if (value === "attack") return styles.attack;
  if (value === "defend") return styles.defend;
  if (value === "contested") return styles.contested;
  if (value === "clear") return styles.clear;
  if (value === "analyzing") return styles.analyzing;
  if (value === "stale") return styles.stale;
  return styles.observe;
}

function resolvedTarget(data: BattleIntelligence): RivalModel | null {
  if (data.target_role === "behind") return data.behind;
  if (data.target_role === "ahead") return data.ahead;
  if (data.state === "defend") return data.behind;
  if (data.state === "attack") return data.ahead;
  return null;
}

function highestPressureRival(data: BattleIntelligence): RivalModel | null {
  const rivals = [data.ahead, data.behind].filter((item): item is RivalModel => item !== null);
  if (rivals.length === 0) return null;
  return rivals.reduce((best, current) => (
    current.pressure_score > best.pressure_score ? current : best
  ));
}

type TrendPresentation = {
  symbol: string;
  label: string;
  tone: "good" | "bad" | "warning" | "neutral";
};

function trendPresentation(
  role: "ahead" | "behind",
  value: number | null,
): TrendPresentation {
  if (value === null || Math.abs(value) < 0.01) {
    return { symbol: "→", label: "stable", tone: "neutral" };
  }

  if (role === "ahead") {
    return value < 0
      ? { symbol: "↓", label: "you closing", tone: "good" }
      : { symbol: "↑", label: "pulling away", tone: "warning" };
  }

  return value < 0
    ? { symbol: "↓", label: "rival closing", tone: "bad" }
    : { symbol: "↑", label: "you pulling away", tone: "good" };
}

function forecastGeometry(
  points: ForecastPoint[],
  drsWindow: number,
  width = 520,
  height = 172,
) {
  const values = points
    .flatMap((point) => [
      point.ahead_high_s,
      point.behind_high_s,
      point.ahead_gap_s,
      point.behind_gap_s,
    ])
    .filter((value): value is number => value !== null && Number.isFinite(value));

  const maxGap = Math.max(1.2, ...values);
  const x = (index: number) => points.length <= 1
    ? width / 2
    : (index / (points.length - 1)) * width;
  const y = (value: number) => height - (clamp(value / maxGap) * (height - 18) + 9);

  const line = (key: "ahead_gap_s" | "behind_gap_s") => points
    .map((point, index) => {
      const value = point[key];
      if (value === null) return null;
      return `${index === 0 ? "M" : "L"}${x(index).toFixed(2)},${y(value).toFixed(2)}`;
    })
    .filter(Boolean)
    .join(" ");

  const band = (
    lowKey: "ahead_low_s" | "behind_low_s",
    highKey: "ahead_high_s" | "behind_high_s",
  ) => {
    const upper = points
      .map((point, index) => {
        const value = point[highKey];
        return value === null ? null : `${x(index).toFixed(2)},${y(value).toFixed(2)}`;
      })
      .filter(Boolean) as string[];
    const lower = points
      .map((point, index) => {
        const value = point[lowKey];
        return value === null ? null : `${x(index).toFixed(2)},${y(value).toFixed(2)}`;
      })
      .filter(Boolean)
      .reverse() as string[];
    return [...upper, ...lower].join(" ");
  };

  return {
    aheadLine: line("ahead_gap_s"),
    behindLine: line("behind_gap_s"),
    aheadBand: band("ahead_low_s", "ahead_high_s"),
    behindBand: band("behind_low_s", "behind_high_s"),
    drsY: y(drsWindow),
  };
}

function MetricRail({ value, className }: { value: number; className?: string }) {
  return (
    <div className={`${styles.metricRail} ${className || ""}`}>
      <i style={{ width: percent(value) }} />
    </div>
  );
}

function RivalCard({ role, rival }: { role: "ahead" | "behind"; rival: RivalModel | null }) {
  if (!rival) {
    return (
      <article className={styles.rivalEmpty}>
        <span>{role}</span>
        <strong>{role === "ahead" ? "NO CAR AHEAD" : "CLEAR BEHIND"}</strong>
        <i>—</i>
      </article>
    );
  }

  const trend = trendPresentation(role, rival.gap_trend_s_per_lap);
  const trendTone = trend.tone === "good"
    ? styles.goodTrend
    : trend.tone === "bad"
      ? styles.badTrend
      : trend.tone === "warning"
        ? styles.warningTrend
        : styles.neutralTrend;

  return (
    <article className={styles.rivalCard}>
      <header>
        <div>
          <span>{role}</span>
          <strong>{rival.name}</strong>
        </div>
        <b>{gap(rival.current_gap_s)}</b>
      </header>

      <div className={styles.rivalVisualRow}>
        <div className={`${styles.trendOrb} ${trendTone}`}>
          <strong>{trend.symbol}</strong>
          <span>{trend.label}</span>
        </div>
        <div className={styles.rivalData}>
          <div>
            <span>NEXT LAP</span>
            <strong>{gap(rival.predicted_gap_next_lap_s)}</strong>
          </div>
          <div>
            <span>CHANGE / LAP</span>
            <strong className={trendTone}>{signedSeconds(rival.gap_trend_s_per_lap)}</strong>
          </div>
        </div>
      </div>

      <div className={styles.rivalPressure}>
        <div>
          <span>DRS CHANCE</span>
          <strong>{percent(rival.drs_probability_next_lap)}</strong>
        </div>
        <MetricRail
          value={rival.drs_probability_next_lap}
          className={role === "behind" ? styles.redRail : styles.blueRail}
        />
        <small>MODEL {percent(rival.model_quality)}</small>
      </div>
    </article>
  );
}

export function BattleCommandCenter({ telemetryStale = false }: { telemetryStale?: boolean }) {
  const [data, setData] = useState<BattleIntelligence>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function refresh() {
      try {
        const response = await fetch(`${API}/api/intelligence/live`, {
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`${response.status} ${response.statusText}`);
        }
        const next = await response.json() as BattleIntelligence;
        if (active) {
          setData({ ...EMPTY, ...next });
          setError(null);
        }
      } catch (requestError) {
        if (active) {
          setError(requestError instanceof Error ? requestError.message : "Unavailable");
        }
      }
    }

    refresh();
    const interval = window.setInterval(refresh, 500);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const resolved = Boolean(data.decision_resolved);
  const rawDominant = data.dominant_probability
    ?? clamp(data.probabilities[data.state as keyof typeof data.probabilities] ?? 0);
  const modelQuality = clamp(data.model?.data_quality || 0);
  const battlePressureRaw = clamp(1 - data.probabilities.clear);
  const focus = resolved ? resolvedTarget(data) : highestPressureRival(data);

  const displayState = telemetryStale
    ? "stale"
    : !data.connected
      ? "observe"
      : resolved
        ? data.state
        : "analyzing";

  const dominantProbability = telemetryStale ? 0 : clamp(rawDominant);
  const battlePressure = telemetryStale ? 0 : battlePressureRaw;
  const ringValue = displayState === "analyzing"
    ? modelQuality
    : displayState === "stale" || displayState === "observe"
      ? 0
      : dominantProbability;
  const ringProgress = Math.round(clamp(ringValue) * 100);
  const ringStyle = { "--progress": ringProgress } as CSSProperties;

  const geometry = useMemo(
    () => forecastGeometry(data.forecast, data.model?.drs_window_s || 1),
    [data.forecast, data.model?.drs_window_s],
  );

  const targetMeta = telemetryStale
    ? "WAITING FOR PACKETS"
    : displayState === "analyzing"
      ? "MODEL SEPARATING STATES"
      : data.window_laps === null
        ? "MODEL LEARNING"
        : data.window_laps === 0
          ? "WINDOW NOW"
          : `WINDOW +${data.window_laps}L`;

  return (
    <section
      className={`${styles.panel} ${telemetryStale ? styles.stalePanel : ""}`}
      aria-label="Adaptive battle intelligence"
    >
      <header className={styles.header}>
        <div>
          <span>Adaptive session model</span>
          <strong>Battle command</strong>
        </div>
        <div className={styles.qualityPill} title={data.model?.method || "Collecting data"}>
          <span>MODEL</span>
          <b>{percent(modelQuality)}</b>
        </div>
      </header>

      {error ? <div className={styles.error}>INTELLIGENCE OFFLINE · {error}</div> : null}

      <div className={styles.heroGrid}>
        <article className={`${styles.stateHero} ${stateClass(displayState)}`}>
          <div className={styles.stateRing} style={ringStyle}>
            <svg viewBox="0 0 100 100" aria-hidden="true">
              <circle className={styles.ringTrack} cx="50" cy="50" r="43" />
              <circle
                className={styles.ringValue}
                cx="50"
                cy="50"
                r="43"
                pathLength="100"
                strokeDasharray={`${ringProgress} ${100 - ringProgress}`}
              />
            </svg>
            <div>
              <strong>{stateSymbol(displayState)}</strong>
              <span>{stateLabel(displayState)}</span>
            </div>
          </div>

          <div className={styles.stateCopy}>
            <span>{telemetryStale ? "LAST VALID FRAME" : focus?.name || data.target || "NO TARGET"}</span>
            <strong>{stateLabel(displayState)}</strong>
            <p>{stateSummary(displayState, Boolean(focus))}</p>
            <div className={styles.targetMeta}>
              <b>{focus ? gap(focus.current_gap_s) : "--"}</b>
              <small>{targetMeta}</small>
            </div>
          </div>
        </article>

        <article className={styles.pressureCard}>
          <div className={styles.pressureNumber}>
            <span>BATTLE PRESSURE</span>
            <strong>{percent(battlePressure)}</strong>
          </div>
          <MetricRail value={battlePressure} />
          <div className={styles.pressureMetrics}>
            <div>
              <span>DECISION</span>
              <strong>{percent(telemetryStale ? 0 : data.confidence)}</strong>
            </div>
            <div>
              <span>DOMINANT</span>
              <strong>{percent(dominantProbability)}</strong>
            </div>
            <div>
              <span>SAMPLES</span>
              <strong>{data.model?.sample_count || 0}</strong>
            </div>
          </div>
        </article>
      </div>

      <div className={styles.rivals}>
        <RivalCard role="ahead" rival={data.ahead} />
        <RivalCard role="behind" rival={data.behind} />
      </div>

      <article className={styles.forecastCard}>
        <header>
          <div>
            <span>Gap forecast</span>
            <strong>Next three laps</strong>
          </div>
          <div className={styles.forecastLegend}>
            <span><i className={styles.aheadKey} />Ahead</span>
            <span><i className={styles.behindKey} />Behind</span>
            <span>
              <i className={styles.drsKey} />
              DRS {data.model?.drs_window_s ? `${data.model.drs_window_s.toFixed(1)}s` : "--"}
            </span>
          </div>
        </header>

        <svg viewBox="0 0 520 172" preserveAspectRatio="none" role="img" aria-label="Three lap gap forecast">
          <line className={styles.drsLine} x1="0" x2="520" y1={geometry.drsY} y2={geometry.drsY} />
          {geometry.aheadBand ? <polygon className={styles.aheadBand} points={geometry.aheadBand} /> : null}
          {geometry.behindBand ? <polygon className={styles.behindBand} points={geometry.behindBand} /> : null}
          {geometry.aheadLine ? <path className={styles.aheadLine} d={geometry.aheadLine} /> : null}
          {geometry.behindLine ? <path className={styles.behindLine} d={geometry.behindLine} /> : null}
          {data.forecast.map((point, index) => {
            const x = data.forecast.length <= 1 ? 260 : (index / (data.forecast.length - 1)) * 520;
            return <line key={point.horizon_laps} className={styles.forecastTick} x1={x} x2={x} y1="0" y2="172" />;
          })}
        </svg>

        <div className={styles.forecastAxis}>
          {data.forecast.map((point) => (
            <span key={point.horizon_laps}>{point.horizon_laps === 0 ? "NOW" : `+${point.horizon_laps}L`}</span>
          ))}
        </div>
      </article>
    </section>
  );
}