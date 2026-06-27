"use client";

import { useMemo } from "react";

import styles from "./MiniTelemetryPlots.module.css";
import { HistoryPoint } from "../types/telemetry";

type SignalDefinition = {
  key: "speed_kph" | "throttle" | "brake";
  label: string;
  unit: string;
  fixedRange?: [number, number];
  formatter: (value: number) => string;
  className: string;
};

const SIGNALS: SignalDefinition[] = [
  {
    key: "speed_kph",
    label: "Speed",
    unit: "km/h",
    formatter: (value) => Math.round(value).toString(),
    className: styles.speed,
  },
  {
    key: "throttle",
    label: "Throttle",
    unit: "%",
    fixedRange: [0, 1],
    formatter: (value) => Math.round(value * 100).toString(),
    className: styles.throttle,
  },
  {
    key: "brake",
    label: "Brake",
    unit: "%",
    fixedRange: [0, 1],
    formatter: (value) => Math.round(value * 100).toString(),
    className: styles.brake,
  },
];

function downsample(points: HistoryPoint[], limit = 240): HistoryPoint[] {
  if (points.length <= limit) {
    return points;
  }

  const step = points.length / limit;
  const sampled: HistoryPoint[] = [];
  for (let index = 0; index < limit; index += 1) {
    sampled.push(points[Math.floor(index * step)]);
  }
  return sampled;
}

function valueOf(point: HistoryPoint, key: SignalDefinition["key"]): number {
  const value = point[key];
  return Number.isFinite(value) ? value : 0;
}

function rangeFor(
  current: HistoryPoint[],
  reference: HistoryPoint[],
  signal: SignalDefinition,
): [number, number] {
  if (signal.fixedRange) {
    return signal.fixedRange;
  }

  const values = [...current, ...reference].map((point) => valueOf(point, signal.key));
  if (values.length === 0) {
    return [0, 1];
  }

  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const spread = Math.max(1, maximum - minimum);
  return [Math.max(0, minimum - spread * 0.08), maximum + spread * 0.08];
}

function pathFor(
  points: HistoryPoint[],
  signal: SignalDefinition,
  width: number,
  height: number,
  yRange: [number, number],
  distanceRange: [number, number],
): string {
  if (points.length < 2) {
    return "";
  }

  const [minimumY, maximumY] = yRange;
  const [minimumX, maximumX] = distanceRange;
  const xSpan = Math.max(1, maximumX - minimumX);
  const ySpan = Math.max(0.0001, maximumY - minimumY);

  return points
    .map((point, index) => {
      const distance = Number.isFinite(point.lap_distance_m)
        ? point.lap_distance_m
        : index;
      const x = ((distance - minimumX) / xSpan) * width;
      const normalized = (valueOf(point, signal.key) - minimumY) / ySpan;
      const y = height - Math.max(0, Math.min(1, normalized)) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function splitLaps(history: HistoryPoint[], lapNumber: number) {
  const valid = history.filter(
    (point) => Number.isFinite(point.lap_distance_m) && point.lap_distance_m >= 0,
  );

  const detectedLap = lapNumber > 0
    ? lapNumber
    : valid.reduce((maximum, point) => Math.max(maximum, point.lap_number || 0), 0);

  const current = downsample(valid.filter((point) => point.lap_number === detectedLap));
  const reference = downsample(
    valid.filter((point) => point.lap_number === detectedLap - 1),
  );

  if (current.length >= 2) {
    return { current, reference };
  }

  return {
    current: downsample(valid.slice(-240)),
    reference: [] as HistoryPoint[],
  };
}

export function MiniTelemetryPlots({
  history,
  lapNumber,
}: {
  history: HistoryPoint[];
  lapNumber: number;
}) {
  const series = useMemo(() => splitLaps(history, lapNumber), [history, lapNumber]);

  const allPoints = [...series.current, ...series.reference];
  const distances = allPoints.map((point) => point.lap_distance_m);
  const distanceRange: [number, number] = distances.length
    ? [Math.min(...distances), Math.max(...distances)]
    : [0, 1];

  const latest = series.current.length > 0 ? series.current[series.current.length - 1] : undefined;
  const width = 640;
  const height = 56;

  return (
    <section className={styles.panel} aria-label="Current lap telemetry traces">
      <header className={styles.header}>
        <div>
          <span>Current lap traces</span>
          <strong>Telemetry</strong>
        </div>
        <div className={styles.legend}>
          <span><i className={styles.currentKey} />Current</span>
          <span><i className={styles.referenceKey} />Previous</span>
        </div>
      </header>

      <div className={styles.stack}>
        {SIGNALS.map((signal) => {
          const yRange = rangeFor(series.current, series.reference, signal);
          const currentPath = pathFor(
            series.current,
            signal,
            width,
            height,
            yRange,
            distanceRange,
          );
          const referencePath = pathFor(
            series.reference,
            signal,
            width,
            height,
            yRange,
            distanceRange,
          );
          const value = latest ? valueOf(latest, signal.key) : 0;

          return (
            <article className={`${styles.plot} ${signal.className}`} key={signal.key}>
              <div className={styles.plotLabel}>
                <span>{signal.label}</span>
                <strong>{signal.formatter(value)}</strong>
                <small>{signal.unit}</small>
              </div>

              <svg
                className={styles.svg}
                viewBox={`0 0 ${width} ${height}`}
                preserveAspectRatio="none"
                role="img"
                aria-label={`${signal.label} trace`}
              >
                <line className={styles.midline} x1="0" y1={height / 2} x2={width} y2={height / 2} />
                {referencePath ? (
                  <path className={styles.referenceLine} d={referencePath} />
                ) : null}
                {currentPath ? (
                  <path className={styles.currentLine} d={currentPath} />
                ) : null}
              </svg>
            </article>
          );
        })}
      </div>
    </section>
  );
}