"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import styles from "./RaceDashboard.module.css";
import { BattleCommandCenter } from "../components/BattleCommandCenter";
import { Controls } from "../components/Controls";
import { CompactEngineerFeed } from "../components/CompactEngineerFeed";
import { MiniTelemetryPlots } from "../components/MiniTelemetryPlots";
import { CompactTyreStatus } from "../components/CompactTyreStatus";
import { fixed, msToLap } from "../lib/format";
import { ControlState, TelemetrySnapshot } from "../types/telemetry";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/live";
const STALE_OVERRIDE_MS = Number.parseFloat(
  process.env.NEXT_PUBLIC_TELEMETRY_STALE_MS || "",
);

const emptySnapshot: TelemetrySnapshot = {
  connected: false,
  packet_count: 0,
  last_packet_age_s: null,
  packet_format: null,
  game_year: null,
  session_uid: null,
  session_time: 0,
  frame: 0,
  speed_kph: 0,
  throttle: 0,
  brake: 0,
  steer: 0,
  gear: 0,
  rpm: 0,
  drs: false,
  rev_lights_percent: 0,
  lap_number: 0,
  total_laps: 0,
  current_lap_time_ms: 0,
  last_lap_time_ms: 0,
  best_lap_time_ms: null,
  lap_distance_m: 0,
  total_distance_m: 0,
  track_length_m: null,
  track_id: null,
  session_type: null,
  position: 0,
  grid_position: 0,
  grid_size: 0,
  positions_gained: 0,
  sector: 1,
  lap_invalid: false,
  warnings: 0,
  penalties_s: 0,
  pit_status: 0,
  pit_stops: 0,
  driver_status: 0,
  result_status: 0,
  delta_to_car_ahead_s: 0,
  delta_to_leader_s: 0,
  fuel_remaining_laps: 0,
  fuel_in_tank_kg: 0,
  ers_store_j: 0,
  ers_percent: 0,
  ers_deploy_mode: 0,
  drs_allowed: false,
  drs_activation_distance_m: 0,
  tyre_age_laps: 0,
  tyre_compound: "UNKNOWN",
  front_brake_bias: 0,
  traction_control: 0,
  abs_enabled: false,
  brake_temps_c: [0, 0, 0, 0],
  tyre_surface_temps_c: [0, 0, 0, 0],
  tyre_inner_temps_c: [0, 0, 0, 0],
  tyre_pressures_psi: [0, 0, 0, 0],
  tyre_wear_pct: [0, 0, 0, 0],
  tyre_damage_pct: [0, 0, 0, 0],
  wing_damage_pct: { fl: 0, fr: 0, rear: 0 },
  world_position: [0, 0, 0],
  world_velocity: [0, 0, 0],
  g_force_lateral: 0,
  g_force_longitudinal: 0,
  player_name: "YOU",
  car_ahead: null,
  car_behind: null,
  leader: null,
  classification: [],
  active_session_id: null,
  recording_enabled: false,
  completed_laps: [],
  recent_messages: [],
  race_events: [],
  history: [],
  track_points: [],
};

const emptyControls: ControlState = {
  voice_enabled: false,
  coaching_enabled: true,
  recording_enabled: false,
  active_session_id: null,
  udp_running: false,
  last_voice_error: null,
  last_udp_error: null,
  llm_enabled: false,
  live_llm_enabled: false,
  radio_enabled: false,
  radio_state: "disabled",
  radio_mode: "race",
};

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value));
}

function median(values: number[]): number {
  if (values.length === 0) return 100;
  const ordered = [...values].sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length % 2 === 0
    ? (ordered[middle - 1] + ordered[middle]) / 2
    : ordered[middle];
}

function formatPacketAge(ageMs: number): string {
  if (ageMs < 1000) return `${Math.round(ageMs)}ms`;
  if (ageMs < 60_000) return `${(ageMs / 1000).toFixed(1)}s`;
  return `${Math.floor(ageMs / 60_000)}m ${Math.round((ageMs % 60_000) / 1000)}s`;
}

function gearLabel(gear: number): string {
  if (gear === 0) return "N";
  if (gear < 0) return "R";
  return String(gear);
}

function wsLabel(status: string): string {
  if (status === "connected") return "CONNECTED";
  if (status === "connecting") return "CONNECTING";
  if (status === "error") return "ERROR";
  return "OFFLINE";
}

function normaliseSnapshot(incoming: Partial<TelemetrySnapshot>): TelemetrySnapshot {
  return {
    ...emptySnapshot,
    ...incoming,
    wing_damage_pct: {
      ...emptySnapshot.wing_damage_pct,
      ...(incoming.wing_damage_pct ?? {}),
    },
    brake_temps_c: incoming.brake_temps_c ?? emptySnapshot.brake_temps_c,
    tyre_surface_temps_c:
      incoming.tyre_surface_temps_c ?? emptySnapshot.tyre_surface_temps_c,
    tyre_inner_temps_c:
      incoming.tyre_inner_temps_c ?? emptySnapshot.tyre_inner_temps_c,
    tyre_pressures_psi: incoming.tyre_pressures_psi ?? emptySnapshot.tyre_pressures_psi,
    tyre_wear_pct: incoming.tyre_wear_pct ?? emptySnapshot.tyre_wear_pct,
    tyre_damage_pct: incoming.tyre_damage_pct ?? emptySnapshot.tyre_damage_pct,
    world_position: incoming.world_position ?? emptySnapshot.world_position,
    world_velocity: incoming.world_velocity ?? emptySnapshot.world_velocity,
    classification: incoming.classification ?? emptySnapshot.classification,
    completed_laps: incoming.completed_laps ?? emptySnapshot.completed_laps,
    recent_messages: incoming.recent_messages ?? emptySnapshot.recent_messages,
    race_events: incoming.race_events ?? emptySnapshot.race_events,
    history: incoming.history ?? emptySnapshot.history,
    track_points: incoming.track_points ?? emptySnapshot.track_points,
  };
}

async function getHealth(): Promise<Partial<ControlState>> {
  const response = await fetch(`${API}/api/health`, { cache: "no-store" });
  if (!response.ok) throw new Error("Health check failed");
  return response.json();
}

function StatusChip({
  label,
  value,
  active,
  warning,
}: {
  label: string;
  value: string;
  active?: boolean;
  warning?: boolean;
}) {
  return (
    <div
      className={`${styles.statusChip} ${active ? styles.statusActive : ""} ${warning ? styles.statusWarning : ""}`}
    >
      <i />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Kpi({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: "good" | "warn" | "danger";
}) {
  return (
    <article className={`${styles.kpi} ${tone ? styles[tone] : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {sub ? <small>{sub}</small> : null}
    </article>
  );
}

function CompactCarStatus({ snapshot }: { snapshot: TelemetrySnapshot }) {
  const items = [
    ["DRS", snapshot.drs ? "OPEN" : snapshot.drs_allowed ? "READY" : "CLOSED"],
    ["BIAS", `${snapshot.front_brake_bias}%`],
    ["ABS", snapshot.abs_enabled ? "ON" : "OFF"],
    ["TC", String(snapshot.traction_control)],
    ["WARN", String(snapshot.warnings)],
    ["PEN", `${snapshot.penalties_s}s`],
    ["WING", `${Math.round(Math.max(snapshot.wing_damage_pct.fl, snapshot.wing_damage_pct.fr, snapshot.wing_damage_pct.rear))}%`],
    ["VALID", snapshot.lap_invalid ? "NO" : "YES"],
  ];

  return (
    <section className={styles.statusPanel}>
      <header>
        <span>Vehicle</span>
        <strong>Car status</strong>
      </header>
      <div className={styles.statusGrid}>
        {items.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function Home() {
  const [snapshot, setSnapshot] = useState<TelemetrySnapshot>(emptySnapshot);
  const [controls, setControls] = useState<ControlState>(emptyControls);
  const [wsStatus, setWsStatus] = useState("connecting");
  const [clockMs, setClockMs] = useState(() => Date.now());
  const [lastWsMessageAtMs, setLastWsMessageAtMs] = useState<number | null>(null);
  const [expectedCadenceMs, setExpectedCadenceMs] = useState(100);

  const previousMessageAtRef = useRef<number | null>(null);
  const cadenceSamplesRef = useRef<number[]>([]);

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (!active) return;
      setWsStatus("connecting");
      socket = new WebSocket(WS_URL);
      socket.onopen = () => setWsStatus("connected");
      socket.onerror = () => setWsStatus("error");
      socket.onmessage = (event) => {
        try {
          const now = Date.now();
          const previous = previousMessageAtRef.current;
          if (previous !== null) {
            const interval = now - previous;
            if (interval > 0 && interval < 10_000) {
              const samples = cadenceSamplesRef.current;
              samples.push(interval);
              if (samples.length > 31) samples.shift();
              if (samples.length >= 5) {
                setExpectedCadenceMs(median(samples));
              }
            }
          }
          previousMessageAtRef.current = now;
          setLastWsMessageAtMs(now);
          setSnapshot(normaliseSnapshot(JSON.parse(event.data) as Partial<TelemetrySnapshot>));
        } catch {
          // Keep the latest valid snapshot.
        }
      };
      socket.onclose = () => {
        if (!active) return;
        setWsStatus("offline");
        retryTimer = setTimeout(connect, 1500);
      };
    }

    connect();
    return () => {
      active = false;
      if (retryTimer) clearTimeout(retryTimer);
      if (socket) socket.close();
    };
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => setClockMs(Date.now()), 250);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    let active = true;
    async function refreshHealth() {
      try {
        const data = await getHealth();
        if (active) setControls((current) => ({ ...current, ...data }));
      } catch {
        if (active) setControls((current) => ({ ...current, udp_running: false }));
      }
    }
    refreshHealth();
    const interval = setInterval(refreshHealth, 1500);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const staleThresholdMs = useMemo(() => {
    if (Number.isFinite(STALE_OVERRIDE_MS) && STALE_OVERRIDE_MS > 0) {
      return STALE_OVERRIDE_MS;
    }
    return clamp(expectedCadenceMs * 12, 1200, 5000);
  }, [expectedCadenceMs]);

  const remotePacketAgeMs = snapshot.last_packet_age_s !== null
    && Number.isFinite(snapshot.last_packet_age_s)
    ? Math.max(0, snapshot.last_packet_age_s * 1000)
    : 0;
  const localMessageAgeMs = lastWsMessageAtMs === null
    ? 0
    : Math.max(0, clockMs - lastWsMessageAtMs);
  const displayedPacketAgeMs = Math.max(remotePacketAgeMs, localMessageAgeMs);
  const telemetrySeen = snapshot.packet_count > 0
    || snapshot.session_uid !== null
    || snapshot.connected;
  const telemetryStale = telemetrySeen
    && (wsStatus !== "connected" || displayedPacketAgeMs > staleThresholdMs);
  const udpLive = snapshot.connected && !telemetryStale;

  const trackProgress = snapshot.track_length_m && snapshot.track_length_m > 0
    ? Math.min(100, Math.max(0, (snapshot.lap_distance_m / snapshot.track_length_m) * 100))
    : 0;
  const tyreWearMax = Math.max(0, ...snapshot.tyre_wear_pct.map((value) => value || 0));

  function resetLocalSnapshot() {
    setSnapshot(emptySnapshot);
    setLastWsMessageAtMs(null);
    setExpectedCadenceMs(100);
    previousMessageAtRef.current = null;
    cadenceSamplesRef.current = [];
  }

  return (
    <main className={styles.shell}>
      {telemetryStale ? (
        <div className={styles.staleBanner} role="status" aria-live="polite">
          <i />
          <strong>TELEMETRY STALE</strong>
          <span>Last update {formatPacketAge(displayedPacketAgeMs)} ago</span>
        </div>
      ) : null}

      <header className={styles.commandBar}>
        <div className={styles.brand}>
          <div className={styles.brandLine}>
            <h1>Live Race Engineer</h1>
            <a href="/reports">Post-race reports</a>
          </div>
          <span>Battle command dashboard</span>
        </div>

        <div className={styles.statusRow} aria-label="System status">
          <StatusChip
            label="UDP"
            value={telemetryStale ? "STALE" : snapshot.connected ? "LIVE" : "WAIT"}
            active={udpLive}
            warning={telemetryStale}
          />
          <StatusChip label="WS" value={wsLabel(wsStatus)} active={wsStatus === "connected"} />
          <StatusChip label="VOICE" value={controls.voice_enabled ? "ON" : "OFF"} active={controls.voice_enabled} />
          <StatusChip label="COACH" value={controls.coaching_enabled ? "ON" : "OFF"} active={controls.coaching_enabled} />
          <StatusChip
            label="RADIO"
            value={(controls.radio_state || "OFF").toUpperCase()}
            active={controls.radio_enabled && controls.radio_state !== "error"}
          />
        </div>

        <div className={styles.controlsWrap}>
          <Controls
            voiceEnabled={controls.voice_enabled}
            coachingEnabled={controls.coaching_enabled}
            udpConnected={udpLive}
            onStateChange={(next) => setControls((current) => ({ ...current, ...next }))}
            onReset={resetLocalSnapshot}
          />
        </div>
      </header>

      <section className={`${styles.kpiStrip} ${telemetryStale ? styles.staleSurface : ""}`}>
        <article className={styles.speedKpi}>
          <span>Speed</span>
          <strong>{Math.round(snapshot.speed_kph)}</strong>
          <small>km/h</small>
          <b>{snapshot.position > 0 ? `P${snapshot.position}` : "P--"}{snapshot.grid_size > 0 ? `/${snapshot.grid_size}` : ""}</b>
        </article>
        <article className={styles.gearKpi}>
          <span>Gear</span>
          <strong>{gearLabel(snapshot.gear)}</strong>
          <small>{snapshot.rpm} rpm</small>
        </article>
        <Kpi label="Lap" value={snapshot.total_laps > 0 ? `${snapshot.lap_number || "--"}/${snapshot.total_laps}` : snapshot.lap_number || "--"} />
        <Kpi label="Current" value={msToLap(snapshot.current_lap_time_ms)} />
        <Kpi label="Best" value={msToLap(snapshot.best_lap_time_ms)} tone="good" />
        <Kpi label="Fuel" value={fixed(snapshot.fuel_remaining_laps, 2)} tone={snapshot.fuel_remaining_laps < 0 ? "danger" : undefined} />
        <Kpi label="ERS" value={`${Math.round(snapshot.ers_percent)}%`} tone={snapshot.ers_percent < 15 ? "warn" : undefined} />
        <Kpi label="Tyres" value={`${Math.round(tyreWearMax)}%`} sub={snapshot.tyre_compound} tone={tyreWearMax > 70 ? "danger" : tyreWearMax > 45 ? "warn" : undefined} />
      </section>

      <div className={`${styles.progressRow} ${telemetryStale ? styles.staleSurface : ""}`} aria-label="Lap progress">
        <div><i style={{ width: `${trackProgress}%` }} /></div>
        <span>{Math.round(snapshot.lap_distance_m)} m</span>
      </div>

      <section className={styles.mainGrid}>
        <div className={`${styles.leftStack} ${telemetryStale ? styles.staleSurface : ""}`}>
          <div className={styles.telemetryCell}>
            <MiniTelemetryPlots history={snapshot.history} lapNumber={snapshot.lap_number} />
          </div>
          <div className={styles.tyreCell}>
            <CompactTyreStatus
              temps={snapshot.tyre_surface_temps_c}
              wear={snapshot.tyre_wear_pct}
              compound={snapshot.tyre_compound}
              age={snapshot.tyre_age_laps}
            />
          </div>
        </div>

        <div className={styles.battleCell}>
          <BattleCommandCenter telemetryStale={telemetryStale} />
        </div>

        <div className={styles.rightStack}>
          <div className={styles.engineerCell}>
            <CompactEngineerFeed messages={snapshot.recent_messages} events={snapshot.race_events} />
          </div>
          <div className={telemetryStale ? styles.staleSurface : ""}>
            <CompactCarStatus snapshot={snapshot} />
          </div>
          {(controls.last_voice_error || controls.last_udp_error) ? (
            <div className={styles.errorPanel}>
              {controls.last_voice_error ? <span>VOICE · {controls.last_voice_error}</span> : null}
              {controls.last_udp_error ? <span>UDP · {controls.last_udp_error}</span> : null}
            </div>
          ) : (
            <div className={`${styles.liveSummary} ${telemetryStale ? styles.staleSummary : ""}`}>
              <div><span>SECTOR</span><strong>{snapshot.sector || "--"}</strong></div>
              <div><span>AHEAD</span><strong>{snapshot.car_ahead?.name || "--"}</strong></div>
              <div><span>BEHIND</span><strong>{snapshot.car_behind?.name || "--"}</strong></div>
              <div><span>AGE</span><strong>{snapshot.last_packet_age_s === null ? "--" : formatPacketAge(remotePacketAgeMs)}</strong></div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
